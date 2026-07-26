#!/usr/bin/env python3
"""cc4101 HTTP handler — Anthropic format only (/v1/messages).

R684/R854: Serves only Claude Code on HM2. Anthropic /v1/messages → glm5.2
(nv_gw glm5_2_nv ONLY, no ms_gw/40007 fallback). Always forces upstream stream=true.

Delegation:
  - Upstream (primary only)    → upstream.py
  - Format conversion          → converters.py (Anthropic↔OpenAI)
  - Streaming                  → stream.py (Anthropic SSE)
  - Error mapping              → error_mapping.py
  - DB logging                 → db.py (async)
"""
import http.server
import json
import os
import time
import datetime
import hmac
import uuid
import urllib.parse

from .config import (
    MODEL_INPUT_TOKEN_SAFETY,
    CHARS_PER_TOKEN_ESTIMATE, CC4101_GATEWAY_API_KEY, AUTH_ENABLED,
    CC_FRONTEND_MODEL, PROXY_ROLE, map_model,
)
from .logger import _log, _log_metrics, _log_error_detail
# R1705: 透传化 — 不再做 anth→oai 转换 (转换下沉 nv_gw/ms_gw /v1/messages 端点).
# cc4101 只透传 anthropic body + passthrough 响应. 保留 error_mapping/db.
from .stream import passthrough_stream, passthrough_nonstream
# 轻量 input 估算 (不再依赖 converters._estimate_text_chars)
def _estimate_input_chars(anth_body):
    try:
        return len(json.dumps(anth_body, ensure_ascii=False))
    except Exception:
        return 0
from .error_mapping import (
    convert_error, get_upstream_status_for_client, is_input_overflow,
)
from .upstream import execute_request
from .db import enqueue_metrics


class ProxyHandler(http.server.BaseHTTPRequestHandler):

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path in ("/health", "/"):
            self._send_json(200, {
                "status": "ok",
                "proxy_role": PROXY_ROLE,
                "primary": os.environ.get("PRIMARY_UPSTREAM_MODEL", "glm5_2_nv"),
                "port": int(os.environ.get("LISTEN_PORT", "4101")),
            })
        elif parsed.path in ("/v1/models", "/models"):
            self._anthropic_models_list()
        elif parsed.path.startswith("/v1/models/") or parsed.path.startswith("/models/"):
            model_id = parsed.path.split("/models/")[1].strip("/")
            self._anthropic_model_detail(model_id)
        else:
            self._send_json(404, {"error": "not found"})

    def do_HEAD(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path in ("/health", "/", "/v1/models", "/models") or parsed.path.startswith("/v1/models/") or parsed.path.startswith("/models/"):
            self.send_response(200)
            self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/v1/messages":
            # Auth check. Claude Code (Anthropic JS SDK) sends `x-api-key: <token>`,
            # NOT `Authorization: Bearer <token>` (OpenAI style). Accept both so CC
            # can actually authenticate. (R690: this was the #1 blocker — CC got 401.)
            if AUTH_ENABLED:
                token = ""
                xkey = self.headers.get("x-api-key", "")
                if xkey:
                    token = xkey.strip()
                if not token:
                    auth = self.headers.get("Authorization", "")
                    if auth.lower().startswith("bearer "):
                        token = auth[7:].strip()
                # R690 cc2 red-team: constant-time compare to avoid timing side-channel
                # on token comparison (defense-in-depth; local-only, but cheap).
                if not hmac.compare_digest(token, CC4101_GATEWAY_API_KEY):
                    self._send_json(401, {"type": "error", "error": {
                        "type": "authentication_error",
                        "message": "invalid or missing API key (expected x-api-key or Bearer cc4101-token)"}})
                    return
            self._handle_messages()
        else:
            self._send_json(404, {"error": {"message": f"cc4101 only serves /v1/messages. Role={PROXY_ROLE}", "type": "invalid_request_error"}})

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    # ─── /v1/messages ───
    def _handle_messages(self):
        t_start = time.time()
        request_id = str(uuid.uuid4())[:8]
        metrics = {
            "request_id": request_id,
            "timestamp": datetime.datetime.now().isoformat(),
            "path": "/v1/messages",
            "proxy_role": PROXY_ROLE,
            "request_model": "?",
            "mapped_model": "?",
            "upstream_used": "?",
            "fallback_triggered": False,  # R854: always False (no fallback), kept for DB schema
            "is_stream": False,
            "num_messages": 0,
            "num_tools": 0,
            "total_input_chars": 0,
            "ttfb_ms": None,
            "duration_ms": 0,
            "status": 0,
            "finish_reason": None,
            "input_tokens": 0,
            "output_tokens": 0,
            "error_type": None,
            "error_message": None,
            "primary_error_type": None,
            "primary_elapsed_ms": None,
        }

        try:
            length = int(self.headers.get("Content-Length", 0))
            # R690 cc2 red-team: cap request body at 50 MB. CC request bodies are
            # small (system prompt + history + tools), so 50 MB is a generous ceiling
            # that still rejects accidental unbounded reads / memory DoS.
            if length <= 0 or length > 50 * 1024 * 1024:
                self._send_json(413, {"type": "error", "error": {
                    "type": "invalid_request_error",
                    "message": f"request body size {length} out of range (max 50MB)"}})
                metrics["status"] = 413; metrics["error_type"] = "PayloadTooLarge"
                _log("ERROR", f"body size {length} rejected")
                _log_metrics(metrics); enqueue_metrics(metrics)
                return
            raw_body = self.rfile.read(length)
            anth_body = json.loads(raw_body)
        except Exception as e:
            self._send_json(400, {"error": {"message": f"bad request: {e}"}})
            metrics["status"] = 400; metrics["error_type"] = "BadRequest"; metrics["error_message"] = str(e)
            _log("ERROR", f"bad request: {e}")
            _log_metrics(metrics); enqueue_metrics(metrics)
            return

        request_model = anth_body.get("model", CC_FRONTEND_MODEL)
        is_stream = anth_body.get("stream", False)
        metrics["request_model"] = request_model
        metrics["is_stream"] = is_stream

        mapped_model = map_model(request_model)

        # R1705: 透传化 — 不调 anth_to_openai, 直接透传 anth_body 给 nv_gw/ms_gw /v1/messages.
        # 转换 (anth↔oai) 下沉到网关端点. cc4101 只在 upstream.py 内改写 model 字段做路由.
        metrics["num_messages"] = len(anth_body.get("messages", []))
        metrics["num_tools"] = len(anth_body.get("tools", []))
        text_chars = _estimate_input_chars(anth_body)
        metrics["total_input_chars"] = text_chars
        metrics["estimated_input_tokens"] = int(text_chars / CHARS_PER_TOKEN_ESTIMATE)

        # R1705: 不强制 upstream stream=True — 透传 CC 的 stream 意图. nv_gw /v1/messages 端点
        # 内部自己强制 upstream stream=True + collect (R684 的 glm5.2 non-stream broken 修复
        # 已下沉到网关). cc4101 只透传.
        _log("REQ", f"model={request_model}→{mapped_model} cc_stream={is_stream} "
                    f"msgs={metrics['num_messages']} tools={metrics['num_tools']} (R1705 passthrough)")

        # ─── Execute: primary nv_gw /v1/messages (R1643 fallback + breaker 保留) ───
        result = execute_request(anth_body, request_id, metrics, t_start)

        if not result.success:
            # Upstream error from primary (or 4xx that we didn't retry). R854: no fallback.
            err_json = result.error_json or {"error": {"message": result.error_message or "upstream failed"}}
            resp_status = result.error_status or 502

            # Input overflow → invalid_request_error (CC stops, no compact)
            if is_input_overflow(err_json, resp_status):
                _log("INPUT-OVERFLOW", f"400 input overflow → invalid_request_error")
                err_msg = json.dumps(err_json)[:500]
                self._send_json(400, {"type": "error", "error": {
                    "type": "invalid_request_error",
                    "message": f"Input tokens exceed backend limit. Please start a new conversation. Detail: {err_msg}",
                    "model": request_model}})
                metrics["status"] = 400
                metrics["error_type"] = "InputExceedsInvalidRequest"
                metrics["duration_ms"] = int((time.time() - t_start) * 1000)
                _log_metrics(metrics); enqueue_metrics(metrics)
                return

            client_status = get_upstream_status_for_client(resp_status)
            error_payload = convert_error(err_json, request_model)
            extra_hdrs = {"retry-after": "5"} if client_status == 429 else None
            metrics["status"] = client_status
            metrics["error_type"] = result.error_kind or "upstream_error"
            metrics["error_message"] = str(err_json)[:200]
            metrics["duration_ms"] = int((time.time() - t_start) * 1000)
            _log_metrics(metrics); enqueue_metrics(metrics)
            self._send_json(client_status, error_payload, extra_headers=extra_hdrs)
            return

        # ─── Success: stream or collect ───
        resp = result.resp
        conn = result.conn

        if is_stream:
            # R1705: 透传 nv_gw /v1/messages 已发的 anthropic SSE, 不做 oai→anth 转换.
            # zombie/content_filter 等诊断已由 nv_gw 在 /v1/messages 端点判定并发 api_error SSE,
            # cc4101 透传给 CC, CC 重试整个请求 (用户已确认接受"同请求中途 fallback"降级).
            # breaker 信号改纯连接级 (passthrough_stream 内 record_primary_success/failure).
            try:
                passthrough_stream(self, resp, conn, metrics, t_start)
            except (BrokenPipeError, ConnectionResetError, OSError) as e:
                _log("ERR", f"client gone mid-stream after {int((time.time()-t_start)*1000)}ms: {e}")
                if not metrics.get("error_type"):
                    metrics["error_type"] = "client_gone_mid_stream"
                if not metrics.get("status"):
                    metrics["status"] = 499
                metrics["duration_ms"] = int((time.time() - t_start) * 1000)
                _log_metrics(metrics)
                # R2253 t1: 499 trace (外层 catch 兜底, passthrough 内未记时).
                _ttfb = metrics.get("ttfb_ms") or 0
                _dur = metrics.get("duration_ms") or 0
                _log_error_detail({
                    "trace": "CC4101-499-OUTER-MIDSTREAM",
                    "request_id": metrics.get("request_id"),
                    "ts": datetime.datetime.now().isoformat(),
                    "host_machine": metrics.get("host_machine"),
                    "stage": "mid_stream_outer_catch",
                    "is_stream": metrics.get("is_stream"),
                    "upstream_used": metrics.get("upstream_used"),
                    "fallback_triggered": metrics.get("fallback_triggered"),
                    "request_model": metrics.get("request_model"),
                    "total_input_chars": metrics.get("total_input_chars"),
                    "ttfb_ms": _ttfb,
                    "duration_ms": _dur,
                    "post_ttfb_ms": max(0, _dur - _ttfb),
                    "exc_type": type(e).__name__,
                    "exc_msg": str(e)[:200],
                })
                try:
                    conn.close()
                except Exception:
                    pass
            enqueue_metrics(metrics)
            return
        else:
            # R1705: 透传 nv_gw /v1/messages stream=false 已合成的 anthropic JSON.
            # nv_gw 端点内部自己 collect upstream stream + 合成 anthropic 非流式 JSON,
            # cc4101 直接透传响应体.
            try:
                passthrough_nonstream(self, resp, conn, metrics, t_start)
            except (BrokenPipeError, ConnectionResetError, OSError) as e:
                _log("ERR", f"client gone mid-collect after {int((time.time()-t_start)*1000)}ms: {e}")
                if not metrics.get("error_type"):
                    metrics["error_type"] = "client_gone_mid_stream"
                if not metrics.get("status"):
                    metrics["status"] = 499
                metrics["duration_ms"] = int((time.time() - t_start) * 1000)
                _log_metrics(metrics)
                # R2253 t1: 499 trace (非流式 collect 阶段 client 断).
                _dur = metrics.get("duration_ms") or 0
                _log_error_detail({
                    "trace": "CC4101-499-MIDCOLLECT",
                    "request_id": metrics.get("request_id"),
                    "ts": datetime.datetime.now().isoformat(),
                    "host_machine": metrics.get("host_machine"),
                    "stage": "mid_collect",
                    "is_stream": metrics.get("is_stream"),
                    "upstream_used": metrics.get("upstream_used"),
                    "fallback_triggered": metrics.get("fallback_triggered"),
                    "request_model": metrics.get("request_model"),
                    "total_input_chars": metrics.get("total_input_chars"),
                    "ttfb_ms": metrics.get("ttfb_ms") or 0,
                    "duration_ms": _dur,
                    "post_ttfb_ms": 0,
                    "exc_type": type(e).__name__,
                    "exc_msg": str(e)[:200],
                })
                try:
                    conn.close()
                except Exception:
                    pass
            enqueue_metrics(metrics)
            return

    # ─── /v1/models (Anthropic format) ───
    def _anthropic_models_list(self):
        self._send_json(200, {
            "data": [{
                "id": CC_FRONTEND_MODEL,
                "type": "model",
                "display_name": "GLM-5.2 (cc4101)",
                "created_at": "2024-01-01T00:00:00Z",
                "context_window": MODEL_INPUT_TOKEN_SAFETY,
            }],
            "has_more": False,
        })

    def _anthropic_model_detail(self, model_id):
        self._send_json(200, {
            "id": model_id,
            "type": "model",
            "display_name": "GLM-5.2 (cc4101)",
            "created_at": "2024-01-01T00:00:00Z",
            "context_window": MODEL_INPUT_TOKEN_SAFETY,
        })

    # ─── Helpers ───
    def _send_json(self, code, data, extra_headers=None):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self._send_raw(code, body, "application/json", extra_headers)

    def _send_raw(self, code, body_bytes, content_type="application/json", extra_headers=None):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body_bytes)))
        self.send_header("Connection", "close")
        self.close_connection = True
        if extra_headers:
            for k, v in extra_headers.items():
                self.send_header(k, str(v))
        self.end_headers()
        self.wfile.write(body_bytes)

    def _send_sse(self, event_type, data_dict):
        data_str = json.dumps(data_dict, ensure_ascii=False)
        msg = f"event: {event_type}\ndata: {data_str}\n\n"
        try:
            self.wfile.write(msg.encode("utf-8"))
            self.wfile.flush()
        except Exception:
            pass

    def log_message(self, fmt, *args):
        pass
