#!/usr/bin/env python3
"""cx4102 http.server 入口. 纯标准库, 无第三方依赖.

路由:
  GET  /health
  POST /v1/responses   (Codex CLI Responses API)
  POST /v1/chat/completions  (调试透传, 不做转换)
"""
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from .config import (
    LISTEN_HOST, LISTEN_PORT, PROXY_TIMEOUT, CX_GATEWAY_API_KEY, AUTH_ENABLED,
    PRIMARY_URL, FALLBACK_URL, PRIMARY_MODEL, FALLBACK_MODEL,
)
from .logger import _log
from .codex import responses_to_chat_body
from .forwarder import forward_non_stream, forward_stream


class CxHandler(BaseHTTPRequestHandler):
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
        return token == CX_GATEWAY_API_KEY

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
                "status": "ok", "proxy": "cx4102", "role": "cx",
                "listen": f"{LISTEN_HOST}:{LISTEN_PORT}",
                "primary_url": PRIMARY_URL, "fallback_url": FALLBACK_URL,
                "primary_model": PRIMARY_MODEL, "fallback_model": FALLBACK_MODEL,
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

        if self.path == "/v1/responses":
            self._handle_responses()
        elif self.path == "/v1/chat/completions":
            self._send_json(404, {"error": {
                "message": "cx4102 仅服务 /v1/responses (Codex), 不支持 /v1/chat/completions",
                "type": "unsupported"}})
        else:
            self._send_json(404, {"error": {"message": "not found", "type": "not_found"}})

    def _handle_responses(self):
        length = int(self.headers.get("Content-Length", 0))
        try:
            raw = self.rfile.read(length) if length else b"{}"
            cx_body = json.loads(raw.decode("utf-8"))
        except Exception as e:
            self._send_json(400, {"error": {"message": f"invalid json: {e}", "type": "invalid_request"}})
            return

        request_model = cx_body.get("model", PRIMARY_MODEL)
        is_stream = cx_body.get("stream", False)
        oai_body = responses_to_chat_body(cx_body, PRIMARY_MODEL)

        _log("REQ", f"model={request_model} stream={is_stream} tools={len(cx_body.get('tools', []))}",
             stream=is_stream, model=request_model)

        if is_stream:
            self._handle_stream(oai_body, request_model)
        else:
            result, status = forward_non_stream(oai_body, request_model)
            self._send_json(status, result)

    def _handle_stream(self, oai_body, request_model):
        # SSE 流式响应: HTTP/1.1 下用 Connection: close 让客户端能感知流结束
        # (http.server 不支持 chunked 透传生成器, 用 close_connection 最简)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.close_connection = True
        self.end_headers()

        def write_sse(event_name, payload):
            data = f"event: {event_name}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
            self.wfile.write(data.encode("utf-8"))
            self.wfile.flush()

        try:
            for event_name, payload in forward_stream(oai_body, request_model):
                write_sse(event_name, payload)
        except Exception as e:
            _log("STREAM-ERR", f"stream handler error: {type(e).__name__}: {e}")
            try:
                write_sse("error", {"error": {"message": str(e), "type": "stream_error"}})
            except Exception:
                pass


def main():
    server = ThreadingHTTPServer((LISTEN_HOST, LISTEN_PORT), CxHandler)
    server.daemon_threads = True
    _log("START", f"cx4102 listening on {LISTEN_HOST}:{LISTEN_PORT}")
    _log("START", f"AUTH_ENABLED={AUTH_ENABLED} PROXY_TIMEOUT={PROXY_TIMEOUT}s")
    _log("START", f"primary={PRIMARY_URL}/{PRIMARY_MODEL} fallback={FALLBACK_URL}/{FALLBACK_MODEL}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        _log("STOP", "shutting down")
        server.shutdown()
