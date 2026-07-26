#!/usr/bin/env python3
"""cc-adapter http.server 入口. 纯标准库, 无第三方依赖.

路由:
  GET  /health
  POST /v1/chat/completions   (openclaw/hermes/opencode 用的 ChatCompletions)
  POST /v1/embeddings         (透传, 不做 fallback — 仅 opclaw4103 memorySearch 用)

R844: embeddings 的 _post_upstream 调用对齐新签名 (header_timeout/idle_timeout 分离).
"""
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from .config import (
    LISTEN_HOST, LISTEN_PORT, PROXY_TIMEOUT, ADAPTER_API_KEY, AUTH_ENABLED,
    PRIMARY_URL, FALLBACK_URL, PRIMARY_MODEL, FALLBACK_MODEL, ADAPTER_NAME,
    ADAPTER_ROLE, FALLBACK_ENABLED, NV_GW_API_KEY, FALLBACK_TIMEOUT_S,
    FALLBACK_HEADER_TIMEOUT, UPSTREAM_IDLE_TIMEOUT,
    PROMPT_TOKEN_LIMIT,
)
from .logger import _log
from .forwarder import forward_non_stream, forward_stream, _post_upstream, _read_body, _prompt_too_large


class AdapterHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass  # 静默默认 access log

    def _check_auth(self):
        if not AUTH_ENABLED:
            return True
        if self.path == "/health" or self.command == "OPTIONS":
            return True
        auth = self.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
        else:
            token = self.headers.get("x-api-key", "")
        return token == ADAPTER_API_KEY

    def _send_json(self, status, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            self._send_json(200, {
                "status": "ok", "proxy": ADAPTER_NAME, "role": ADAPTER_ROLE,
                "listen": f"{LISTEN_HOST}:{LISTEN_PORT}",
                "primary_url": PRIMARY_URL, "fallback_url": FALLBACK_URL,
                "primary_model": PRIMARY_MODEL, "fallback_model": FALLBACK_MODEL,
                "fallback_enabled": FALLBACK_ENABLED,
            })
            return
        self._send_json(404, {"error": {"message": "not found", "type": "not_found"}})

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.end_headers()

    def do_POST(self):
        if not self._check_auth():
            self._send_json(401, {"error": {"message": "unauthorized", "type": "auth_error"}})
            return

        if self.path == "/v1/chat/completions":
            self._handle_chat()
        elif self.path == "/v1/embeddings":
            self._handle_embeddings()
        else:
            self._send_json(404, {"error": {"message": "not found", "type": "not_found"}})

    def _read_body_json(self):
        length = int(self.headers.get("Content-Length", 0))
        try:
            raw = self.rfile.read(length) if length else b"{}"
            return json.loads(raw.decode("utf-8"))
        except Exception as e:
            return None

    def _handle_chat(self):
        oai_body = self._read_body_json()
        if oai_body is None:
            self._send_json(400, {"error": {"message": "invalid json", "type": "invalid_request"}})
            return

        request_model = oai_body.get("model", PRIMARY_MODEL)
        is_stream = oai_body.get("stream", False)
        tools = len(oai_body.get("tools", [])) if isinstance(oai_body.get("tools"), list) else 0
        _log("REQ", f"model={request_model} stream={is_stream} tools={tools}",
             stream=is_stream, model=request_model)

        # R766: prompt 超限预检 (避免 openclaw Context overflow 后 retry 累积 142s 超时)
        too_large, est_tokens = _prompt_too_large(oai_body)
        if too_large:
            _log("PROMPT-TOO-LARGE",
                 f"est_tokens={est_tokens} > limit, 直接 400 不转发 (避免 retry 累积超时)",
                 est_tokens=est_tokens)
            self._send_json(400, {
                "error": {
                    "message": f"This model's maximum context length is {PROMPT_TOKEN_LIMIT} tokens. "
                               f"However, your messages resulted in {est_tokens} tokens. "
                               f"Please reduce context (e.g. /reset or /new).",
                    "type": "invalid_request_error",
                    "code": "context_length_exceeded",
                    "est_tokens": est_tokens,
                    "limit": PROMPT_TOKEN_LIMIT,
                }
            })
            return

        if is_stream:
            self._handle_stream(oai_body, request_model)
        else:
            result, status = forward_non_stream(oai_body, request_model)
            self._send_json(status, result)

    def _handle_stream(self, oai_body, request_model):
        # SSE 流式响应: HTTP/1.1 下用 Connection: close 让客户端能感知流结束
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.close_connection = True
        self.end_headers()

        done_sent = False

        def write_sse(event_name, payload):
            nonlocal done_sent
            if payload is None and event_name == "done":
                if done_sent:
                    return
                done_sent = True
                self.wfile.write(b"data: [DONE]\n\n")
            elif isinstance(payload, dict):
                line = f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                self.wfile.write(line.encode("utf-8"))
            try:
                self.wfile.flush()
            except Exception:
                pass

        try:
            for event_name, payload in forward_stream(oai_body, request_model):
                write_sse(event_name, payload)
        except (BrokenPipeError, ConnectionResetError):
            _log("STREAM-CLIENT-ERR", "客户端断开流")
        except Exception as e:
            _log("STREAM-ERR", f"stream handler error: {type(e).__name__}: {e}")
        finally:
            try:
                # 兜底: forward_stream 异常退出没发 done 时补一个
                if not done_sent:
                    write_sse("done", None)
            except Exception:
                pass

    def _handle_embeddings(self):
        # 透传到 primary, 不做 fallback (embeddings 无流式, 失败就失败)
        # R844: _post_upstream 新签名 — header_timeout/idle_timeout 分离
        oai_body = self._read_body_json()
        if oai_body is None:
            self._send_json(400, {"error": {"message": "invalid json", "type": "invalid_request"}})
            return
        try:
            resp, conn = _post_upstream(PRIMARY_URL, PRIMARY_MODEL, NV_GW_API_KEY,
                                        oai_body, False,
                                        FALLBACK_HEADER_TIMEOUT, UPSTREAM_IDLE_TIMEOUT)
        except Exception as e:
            _log("EMBED-UPSTREAM-ERR", f"embeddings upstream failed: {type(e).__name__}: {e}")
            self._send_json(503, {"error": {"message": "embeddings upstream down", "type": "upstream_down"}})
            return
        status = resp.status
        body = _read_body(resp)
        try:
            conn.close()
        except Exception:
            pass
        self._send_json(status, body)
