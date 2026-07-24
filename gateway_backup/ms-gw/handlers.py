#!/usr/bin/env python3
"""HTTP handler for ms_gw — /health, /v1/models, /v1/chat/completions.

OpenAI-format passthrough (agents speak OpenAI; no Anthropic conversion).
Stream: 前置错误检查已在 upstream._try_ms_keys 做完 (第一 chunk 已预读),
  handler 直接 send 200 + 透传 (含已预读的 first_chunk) + 后续 chunk.
"""
import http.client
import json
import os
import socket
import ssl
import sys
import time
import uuid
from http.server import BaseHTTPRequestHandler

from .config import (
    LISTEN_HOST, LISTEN_PORT, PROXY_ROLE,
    MS_KEYS, NUM_KEYS, NUM_VARIANTS, MODEL_REGISTRY, DEFAULT_MODEL,
    MS_BASEURL, MSU_GATEWAY_API_KEY, AUTH_ENABLED,
    UPSTREAM_TIMEOUT,
)
from .logger import _log, _log_metrics, _log_error_detail
from .upstream import _try_ms_keys, _sanitize_request_body
# R1648d: /v1/messages anthropic endpoint (mirror of nv_gw R1648b).
from .format.anth_to_oai import anth_to_openai, _estimate_text_chars, CHARS_PER_TOKEN_ESTIMATE
from .format.oai_to_anth import (
    OaiSseToAnthropicConverter, oai_nonstream_to_anth, convert_error_to_anth,
    THINKING_SIGNATURE as OAI_TO_ANTH_THINKING_SIG,
)
from .error_mapping import (
    auth_error, bad_request_error, model_not_found_error,
    all_keys_exhausted_error,
)
from .cooldown import snapshot as cooldown_snapshot
from .rr_counter import _get_rr_counter_snapshot


class ProxyHandler(BaseHTTPRequestHandler):
    # Quiet default access log (we do our own structured logging)
    def log_message(self, fmt, *args):
        pass

    # ─── GET ─────────────────────────────────────────────────────────────
    def do_GET(self):
        from urllib.parse import urlparse
        parsed = urlparse(self.path)
        if parsed.path in ("/health", "/"):
            self._handle_health()
            return
        if parsed.path in ("/v1/models", "/models"):
            self._handle_models()
            return
        self._send_json(404, {"error": {"message": f"Not found: {parsed.path}",
                                        "type": "ms_not_found"}})

    def do_HEAD(self):
        from urllib.parse import urlparse
        parsed = urlparse(self.path)
        if parsed.path in ("/health", "/", "/v1/models", "/models",
                           "/v1/chat/completions", "/chat/completions",
                           "/v1/messages", "/messages"):
            self.send_response(200)
            self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers",
                         "Authorization, Content-Type, X-Caller")
        self.end_headers()

    # ─── POST /v1/chat/completions ───────────────────────────────────────
    def do_POST(self):
        from urllib.parse import urlparse
        parsed = urlparse(self.path)
        if parsed.path in ("/v1/chat/completions", "/chat/completions"):
            self._handle_chat()
            return
        # R1648d: anthropic-format endpoint (cc4101 pure-passthrough after R1648e).
        if parsed.path in ("/v1/messages", "/messages"):
            self._handle_messages_anthropic()
            return
        self._send_json(404, {"error": {"message": f"Not found: {parsed.path}",
                                        "type": "ms_not_found"}})

    # ─── /health ─────────────────────────────────────────────────────────
    def _handle_health(self):
        snap = cooldown_snapshot()
        body = {
            "status": "ok" if NUM_KEYS > 0 else "degraded",
            "proxy": "ms_gw",
            "role": PROXY_ROLE,
            "listen": f"{LISTEN_HOST}:{LISTEN_PORT}",
            "num_keys": NUM_KEYS,
            "num_variants": NUM_VARIANTS,
            "models": list(MODEL_REGISTRY.keys()),
            "default_model": DEFAULT_MODEL,
            "ms_baseurl": MS_BASEURL,
            "rr_counters": _get_rr_counter_snapshot(),
            "cooldown": snap,
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        self._send_json(200, body)

    # ─── /v1/models ──────────────────────────────────────────────────────
    def _handle_models(self):
        data = []
        for mid, spec in MODEL_REGISTRY.items():
            data.append({
                "id": mid,
                "object": "model",
                "created": 1700000000,
                "owned_by": "ms_gw",
                "name": spec.get("name", mid),
                "context_window": spec.get("context_window", 131072),
                "context_length": spec.get("context_window", 131072),  # R699 BUG-4: OpenAI标准字段名是context_length不是context_window. hermes background_review找context_length找不到→None→默认32768→报32K<64K失败. 加alias让客户端认出真实128K.
                "max_tokens": spec.get("max_tokens", 32768),
                "supports_thinking": spec.get("supports_thinking", False),
                "disabled": spec.get("_disabled", False),
            })
        self._send_json(200, {"object": "list", "data": data})

    # ─── /v1/chat/completions handler ────────────────────────────────────
    def _handle_chat(self):
        t_start = time.monotonic()  # for duration
        t_start_wall = time.time()  # R699 BUG-6: wall clock for ts (monotonic -> 1970)
        request_id = str(uuid.uuid4())[:8]

        # Auth
        if AUTH_ENABLED and not self._check_auth():
            status, err = auth_error()
            self._send_json(status, err)
            return

        # Read body
        try:
            body_len = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            body_len = 0
        try:
            raw = self.rfile.read(body_len) if body_len > 0 else b""
        except Exception as e:
            status, err = bad_request_error(f"read body failed: {e}")
            self._send_json(status, err)
            return

        # Parse
        try:
            req_body = json.loads(raw) if raw else {}
        except Exception as e:
            status, err = bad_request_error(f"invalid JSON: {e}")
            self._send_json(status, err)
            return

        agent_model = req_body.get("model") or DEFAULT_MODEL
        is_stream = bool(req_body.get("stream", False))

        # Caller detection
        user_agent = self.headers.get("User-Agent", "")
        x_caller = self.headers.get("X-Caller", "")
        caller = self._detect_caller(user_agent, x_caller)

        # Model exists?
        spec = MODEL_REGISTRY.get(agent_model)
        if not spec:
            status, err = model_not_found_error(agent_model)
            self._send_json(status, err)
            return
        if spec.get("_disabled"):
            from .error_mapping import model_disabled_error
            status, err = model_disabled_error(agent_model)
            self._send_json(status, err)
            return

        # Sanitize (strip NVCF-style params)
        cleaned_body = _sanitize_request_body(req_body, spec)

        metrics = {
            "request_id": request_id,
            "ts": int(t_start_wall * 1000),
            "caller": caller,
            "agent_model": agent_model,
            "is_stream": is_stream,
            "backend": "ms",
        }

        # Execute with 2D rotation
        result = _try_ms_keys(cleaned_body, agent_model, request_id,
                              metrics, t_start, is_stream)

        if not result.relay:
            # Error path
            status = result.error_status or 502
            err_body = result.error_body or {"error": {"message": "ms_gw: unknown failure"}}
            # Inject cycle attempts for debugging
            if isinstance(err_body, dict) and "error" in err_body:
                err_body["error"]["attempts"] = result.attempts[-5:]
            metrics["status"] = "error"
            metrics["error_status"] = status
            metrics["attempts_count"] = len(result.attempts)
            metrics["duration_ms"] = int((time.monotonic() - t_start) * 1000)
            _log_metrics(metrics)
            self._send_json(status, err_body)
            return

        # Success — relay
        metrics["backend_model"] = result.metrics.get("backend_model")
        metrics["variant_idx"] = result.metrics.get("variant_idx")
        metrics["key_idx"] = result.metrics.get("key_idx")
        metrics["cycle_attempts_before_success"] = len(
            [a for a in result.attempts if "ok" not in a.get("status", "")])

        if is_stream:
            self._relay_stream(result, metrics, t_start, request_id, agent_model)
        else:
            self._relay_nonstream(result, metrics, t_start, request_id, agent_model)

    # ─── Non-stream relay ────────────────────────────────────────────────
    def _relay_nonstream(self, result, metrics, t_start, request_id, agent_model):
        try:
            resp_status = result.metrics.get("_resp_status", 200)
            resp_body = result.metrics.get("_resp_body", b"")
            if isinstance(resp_body, str):
                resp_body = resp_body.encode("utf-8")
            # Rewrite model in body to agent-facing id (so agent sees glm5_2_ms not variant)
            try:
                parsed = json.loads(resp_body)
                if isinstance(parsed, dict):
                    parsed["model"] = agent_model
                    resp_body = json.dumps(parsed, ensure_ascii=False).encode("utf-8")
            except Exception:
                pass  # pass through as-is on parse failure

            self.send_response(resp_status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(resp_body)))
            self.send_header("X-MS-Backend-Model", result.metrics.get("backend_model", ""))
            self.send_header("X-MS-Variant", str(result.metrics.get("variant_idx", "")))
            self.send_header("X-MS-Key", str(result.metrics.get("key_idx", "")))
            self.send_header("X-MS-Proxy", "ms_gw")
            self.end_headers()
            self.wfile.write(resp_body)

            metrics["status"] = "ok"
            metrics["duration_ms"] = int((time.monotonic() - t_start) * 1000)
            metrics["resp_status"] = resp_status
            _log_metrics(metrics)
        except Exception as e:
            _log("MS-RELAY-ERR", f"req={request_id} nonstream relay: {type(e).__name__}: {e}")
            _log_error_detail({"request_id": request_id, "phase": "nonstream_relay",
                                "error": str(e)})
        finally:
            try:
                if result.conn: result.conn.close()
            except Exception:
                pass

    # ─── Stream relay ────────────────────────────────────────────────────
    def _relay_stream(self, result, metrics, t_start, request_id, agent_model):
        """Relay SSE stream. First chunk already prefetched & validated."""
        first_chunk = result.metrics.get("_first_chunk", b"")
        conn = result.conn
        resp = result.resp
        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            # R806d: Connection: close (NOT keep-alive). HTTP/1.0 + no
            # Content-Length + no chunked -> client cannot find response
            # boundary with keep-alive, blocks 120s -> CC interrupt.
            # close lets client read-to-EOF; BaseHTTPRequestHandler closes
            # wfile when handler returns.
            self.send_header("Connection", "close")
            self.close_connection = True
            self.send_header("X-MS-Backend-Model", result.metrics.get("backend_model", ""))
            self.send_header("X-MS-Variant", str(result.metrics.get("variant_idx", "")))
            self.send_header("X-MS-Key", str(result.metrics.get("key_idx", "")))
            self.send_header("X-MS-Proxy", "ms_gw")
            self.end_headers()

            # Replay prefetched first chunk
            if first_chunk:
                self.wfile.write(first_chunk)
                self.wfile.flush()

            # R806c: ensure socket timeout is set on resp before relay loop.
            # conn.sock may have been None'd by http.client after getresponse;
            # resp.fp is the BufferedReader wrapping the socket.
            try:
                if resp.fp and getattr(resp.fp, "raw", None) is not None:
                    resp.fp.raw._sock.settimeout(UPSTREAM_TIMEOUT)
            except Exception as _e:
                _log("MS-STREAM-SETTO-ERR", f"req={request_id} {_e}")
            # Stream the rest
            bytes_relayed = len(first_chunk)
            # We may need to rewrite model name in SSE chunks — but rewriting stream
            # chunks inline is fragile (partial JSON across chunks). Skip rewriting
            # for stream; agent gets backend variant name in SSE model field (cosmetic).
            while True:
                try:
                    # R806b: read1() not read(n) -- read(n) blocks until n bytes or EOF;
                    # ModelScope SSE sends small spaced chunks so read(8192) stalls relay.
                    # read1 returns as soon as any data is available from the socket.
                    chunk = resp.read1(8192)
                except (http.client.IncompleteRead, http.client.RemoteDisconnected,
                        ConnectionResetError, socket.timeout) as e:
                    _log("MS-STREAM-EOF", f"req={request_id} stream ended: {type(e).__name__}")
                    break
                if not chunk:
                    break
                self.wfile.write(chunk)
                self.wfile.flush()
                bytes_relayed += len(chunk)

            metrics["status"] = "ok"
            metrics["duration_ms"] = int((time.monotonic() - t_start) * 1000)
            metrics["bytes_relayed"] = bytes_relayed
            _log_metrics(metrics)
        except (http.client.RemoteDisconnected, ConnectionResetError,
                BrokenPipeError, OSError) as e:
            _log("MS-STREAM-CLIENT-EOF", f"req={request_id} client disconnected: "
                  f"{type(e).__name__}")
            metrics["status"] = "client_disconnect"
            metrics["duration_ms"] = int((time.monotonic() - t_start) * 1000)
            _log_metrics(metrics)
        except Exception as e:
            _log("MS-STREAM-ERR", f"req={request_id} {type(e).__name__}: {e}")
            _log_error_detail({"request_id": request_id, "phase": "stream_relay",
                                "error": str(e)})
        finally:
            try:
                if conn: conn.close()
            except Exception:
                pass

    # ─── Auth check ──────────────────────────────────────────────────────
    def _check_auth(self):
        """Require Authorization: Bearer <MSU_GATEWAY_API_KEY> or X-Api-Key.
        /health is exempt."""
        auth = self.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:].strip()
            if token == MSU_GATEWAY_API_KEY:
                return True
        xk = self.headers.get("X-Api-Key", "")
        if xk == MSU_GATEWAY_API_KEY:
            return True
        # Allow litellm-local compat (so CC's existing key works for testing)
        if MSU_GATEWAY_API_KEY and xk == "sk-litellm-local":
            return True
        return False

    # ─── Helpers ─────────────────────────────────────────────────────────
    @staticmethod
    def _detect_caller(user_agent, x_caller=""):
        ua = (user_agent or "").lower()
        xc = (x_caller or "").lower()
        # R1700: cc4101 注入的 X-Caller (cc4101-primary / cc4101-fallback) 原样保留,
        # 让 metrics.caller 区分 fallback 流量(回答"ms fallback 次数"). 精确标签优先.
        if xc.startswith("cc4101"):
            return xc
        if "hermes" in ua or "hermes" in xc:
            return "hermes"
        if "openclaw" in ua or "openclaw" in xc:
            return "openclaw"
        if "opencode" in ua or "opencode" in xc:
            return "opencode"
        if "curl" in ua:
            return "curl"
        return "unknown"

    # ─── R1648d: /v1/messages anthropic endpoint ───────────────────────
    def _handle_messages_anthropic(self):
        """Anthropic-format endpoint (mirror of nv_gw R1648b). Converts
        Anthropic→OpenAI request, runs _try_ms_keys, converts OpenAI SSE/JSON
        back to Anthropic. ms_gw has no peer-fallback; this is a format adapter
        on top of the existing 2D key×variant rotation."""
        t_start = time.monotonic()
        t_start_wall = time.time()
        request_id = str(uuid.uuid4())[:8]

        if AUTH_ENABLED and not self._check_auth():
            status, err = auth_error()
            # err is OpenAI-shape; convert to anthropic
            self._send_json(status, convert_error_to_anth(err, DEFAULT_MODEL))
            return

        metrics = {
            "request_id": request_id,
            "ts": int(t_start_wall * 1000),
            "caller": self._detect_caller(self.headers.get("User-Agent", ""),
                                          self.headers.get("X-Caller", "")),
            "agent_type": "_ms_anthropic",
            "path": "/v1/messages",
            "request_model": "?",
            "backend": "ms",
            "is_stream": False,
            "total_input_chars": 0,
            "estimated_input_tokens": 0,
            "duration_ms": 0,
            "status": 0,
            "finish_reason": None,
            "input_tokens": 0,
            "output_tokens": 0,
            "ttfb_ms": None,
            "error_type": None,
        }

        try:
            body_len = int(self.headers.get("Content-Length", "0"))
            if body_len <= 0 or body_len > 50 * 1024 * 1024:
                self._send_json(413, {"type": "error", "error": {
                    "type": "invalid_request_error",
                    "message": f"request body size {body_len} out of range (max 50MB)"}})
                metrics["status"] = 413
                metrics["error_type"] = "PayloadTooLarge"
                _log("MS-ANTH-ERR", f"req={request_id} body size {body_len} rejected")
                _log_metrics(metrics)
                return
            raw_body = self.rfile.read(body_len)
            anth_body = json.loads(raw_body) if raw_body else {}
        except Exception as e:
            self._send_json(400, {"type": "error", "error": {
                "type": "invalid_request_error", "message": f"bad request: {e}"}})
            metrics["status"] = 400
            metrics["error_type"] = "BadRequest"
            _log("MS-ANTH-ERR", f"req={request_id} bad request: {e}")
            _log_metrics(metrics)
            return

        request_model = anth_body.get("model", DEFAULT_MODEL)
        is_stream = bool(anth_body.get("stream", False))
        metrics["request_model"] = request_model
        metrics["is_stream"] = is_stream

        # Validate model exists (mirror _handle_chat)
        spec = MODEL_REGISTRY.get(request_model)
        if not spec:
            self._send_json(404, convert_error_to_anth(
                {"error": {"message": f"ms_gw: model '{request_model}' not found.",
                            "type": "ms_model_not_found"}},
                request_model))
            metrics["status"] = 404
            metrics["error_type"] = "ModelNotFound"
            _log_metrics(metrics)
            return
        if spec.get("_disabled"):
            from .error_mapping import model_disabled_error
            self._send_json(501, convert_error_to_anth(
                {"error": {"message": f"ms_gw: model '{request_model}' disabled.",
                            "type": "ms_model_disabled"}},
                request_model))
            metrics["status"] = 501
            metrics["error_type"] = "ModelDisabled"
            _log_metrics(metrics)
            return

        # Anthropic → OpenAI request body (target_model = request_model, the ms model id)
        try:
            oai_body = anth_to_openai(anth_body, target_model=request_model)
        except Exception as e:
            self._send_json(400, {"type": "error", "error": {
                "type": "invalid_request_error", "message": f"format conversion failed: {e}"}})
            metrics["status"] = 400
            metrics["error_type"] = "FormatConversion"
            _log("MS-ANTH-ERR", f"req={request_id} anth_to_openai failed: {e}")
            _log_metrics(metrics)
            return
        metrics["total_input_chars"] = _estimate_text_chars(oai_body)
        metrics["estimated_input_tokens"] = int(metrics["total_input_chars"] / CHARS_PER_TOKEN_ESTIMATE)

        # R684 parity: always force upstream stream=True (glm5.2 non-stream returns
        # empty content). is_stream here is the *client* intent.
        oai_body["stream"] = True
        oai_body["stream_options"] = {"include_usage": True}
        is_stream_upstream = True

        # MSG-FIX parity: trailing assistant → user "Continue."
        messages = oai_body.get("messages", [])
        if messages and isinstance(messages[-1], dict) and messages[-1].get("role") == "assistant":
            oai_body["messages"].append({"role": "user", "content": "Continue."})

        cleaned_body = _sanitize_request_body(oai_body, spec)

        result = _try_ms_keys(cleaned_body, request_model, request_id,
                              metrics, t_start, is_stream_upstream)

        if not result.relay:
            status = result.error_status or 502
            err_body = result.error_body or {"error": {"message": "ms_gw: unknown failure"}}
            if isinstance(err_body, dict) and "error" in err_body:
                err_body["error"]["attempts"] = result.attempts[-5:]
            anth_err = convert_error_to_anth(err_body, request_model)
            extra_hdrs = {"retry-after": "5"} if status == 429 else None
            metrics["status"] = status
            metrics["error_type"] = "ms_all_keys_exhausted" if status == 503 else "ms_upstream_error"
            metrics["duration_ms"] = int((time.monotonic() - t_start) * 1000)
            _log_metrics(metrics)
            self._send_json(status, anth_err, extra_headers=extra_hdrs)
            return

        # ─── Success: stream or collect → anthropic SSE/JSON ───
        metrics["backend_model"] = result.metrics.get("backend_model")
        metrics["variant_idx"] = result.metrics.get("variant_idx")
        metrics["key_idx"] = result.metrics.get("key_idx")
        first_chunk = result.metrics.get("_first_chunk", b"")
        resp = result.resp
        conn = result.conn

        if is_stream:
            self._relay_stream_to_anth(resp, conn, first_chunk, metrics, t_start, request_model)
        else:
            self._relay_nonstream_to_anth(resp, conn, first_chunk, metrics, t_start, request_model)

    def _relay_stream_to_anth(self, resp, conn, first_chunk, metrics, t_start, request_model):
        """Read ModelScope OpenAI-SSE stream (first_chunk prefetched by
        _try_ms_keys), convert each chunk via OaiSseToAnthropicConverter, write
        Anthropic SSE to client. Simpler than nv_gw (no deadline/zombie infra —
        ms_gw's own _relay_stream is also plain read1 passthrough)."""
        converter = OaiSseToAnthropicConverter(request_model)
        sse_buffer = ""
        ttfb_recorded = False
        streaming_input_tokens = 0
        streaming_output_tokens = 0
        content_chars = 0
        reasoning_chars = 0
        saw_tool_calls = False
        zombie_detected = False
        interrupted = False

        # SSE headers (anthropic event-stream)
        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self.close_connection = True
            self.send_header("X-MS-Proxy", "ms_gw")
            self.send_header("X-MS-Backend-Model", metrics.get("backend_model", ""))
            self.send_header("X-MS-Variant", str(metrics.get("variant_idx", "")))
            self.send_header("X-MS-Key", str(metrics.get("key_idx", "")))
            self.end_headers()
        except (BrokenPipeError, ConnectionResetError, OSError) as e:
            _log("MS-ANTH-ERR", f"req={metrics['request_id']} client gone before SSE headers: {e}")
            metrics["error_type"] = "client_gone_pre_stream"
            metrics["status"] = 499
            metrics["duration_ms"] = int((time.monotonic() - t_start) * 1000)
            _log_metrics(metrics)
            try: conn.close()
            except Exception: pass
            return

        # R806c parity: set socket timeout on resp before relay loop
        try:
            if resp.fp and getattr(resp.fp, "raw", None) is not None:
                resp.fp.raw._sock.settimeout(UPSTREAM_TIMEOUT)
        except Exception as _e:
            _log("MS-STREAM-SETTO-ERR", f"req={metrics['request_id']} {_e}")

        try:
            # Replay prefetched first_chunk then read1() the rest
            buf_chunks = [first_chunk] if first_chunk else []
            while True:
                if buf_chunks:
                    chunk = buf_chunks.pop(0)
                else:
                    try:
                        chunk = resp.read1(8192)
                    except (http.client.IncompleteRead, http.client.RemoteDisconnected,
                            ConnectionResetError, socket.timeout) as e:
                        _log("MS-ANTH-EOF", f"req={metrics['request_id']} stream ended: {type(e).__name__}")
                        break
                if not chunk:
                    break
                if not ttfb_recorded:
                    metrics["ttfb_ms"] = int((time.monotonic() - t_start) * 1000)
                    ttfb_recorded = True
                sse_buffer += chunk.decode("utf-8", errors="replace")
                while "\n\n" in sse_buffer:
                    event_str, sse_buffer = sse_buffer.split("\n\n", 1)
                    data_str = ""
                    for line in event_str.split("\n"):
                        if line.startswith("data:"):
                            data_str = line[5:].strip()
                    if not data_str or data_str == "[DONE]":
                        continue
                    try:
                        chunk_data = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue
                    chunk_usage = chunk_data.get("usage") or {}
                    if chunk_usage:
                        pt = chunk_usage.get("prompt_tokens", 0)
                        ct = chunk_usage.get("completion_tokens", 0)
                        if pt > 0: streaming_input_tokens = pt
                        if ct > 0: streaming_output_tokens = ct
                    choices = chunk_data.get("choices") or [{}]
                    delta = choices[0].get("delta") or {}
                    cont = delta.get("content")
                    if cont: content_chars += len(cont)
                    rcont = delta.get("reasoning_content")
                    if rcont: reasoning_chars += len(rcont)
                    for _tc in (delta.get("tool_calls") or []):
                        _fn = _tc.get("function", {}) if isinstance(_tc, dict) else {}
                        if _fn.get("arguments"): saw_tool_calls = True
                    fr = choices[0].get("finish_reason")
                    if fr:
                        metrics["finish_reason"] = fr
                    out_bytes = converter.feed_chunk(chunk_data)
                    if out_bytes:
                        try:
                            self.wfile.write(out_bytes)
                            self.wfile.flush()
                        except (BrokenPipeError, ConnectionResetError, OSError):
                            interrupted = True
                            break
                if interrupted:
                    break
        except (http.client.RemoteDisconnected, ConnectionResetError, OSError,
                http.client.IncompleteRead, socket.timeout) as e:
            _log("MS-ANTH-ERR", f"req={metrics['request_id']} stream {type(e).__name__}: {e}")
            metrics["error_type"] = f"MSAnth_{type(e).__name__}"
            interrupted = True
        except Exception as e:
            _log("MS-ANTH-ERR", f"req={metrics['request_id']} stream unexpected {type(e).__name__}: {e}")
            metrics["error_type"] = f"MSAnth_{type(e).__name__}"
            interrupted = True

        if metrics.get("error_type"):
            metrics["status"] = 502
        else:
            metrics["status"] = 200
        metrics["duration_ms"] = int((time.monotonic() - t_start) * 1000)
        if streaming_input_tokens > 0: metrics["input_tokens"] = streaming_input_tokens
        if streaming_output_tokens > 0: metrics["output_tokens"] = streaming_output_tokens
        _log_metrics(metrics)

        is_zombie = zombie_detected
        is_interrupted_no_content = interrupted and content_chars == 0
        try:
            fin = converter.finish(
                interrupted=(is_interrupted_no_content and not is_zombie),
                zombie=is_zombie or is_interrupted_no_content,
                input_tokens_real=streaming_input_tokens,
            )
            if fin:
                self.wfile.write(fin)
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        try: conn.close()
        except Exception: pass

    def _relay_nonstream_to_anth(self, resp, conn, first_chunk, metrics, t_start, request_model):
        """Collect upstream OpenAI-SSE stream (client asked stream=false), synthesize
        non-stream Anthropic message JSON via oai_nonstream_to_anth. Mirrors nv_gw
        _collect_stream_to_anth but simpler (no deadline infra)."""
        sse_buffer = ""
        all_content_parts = []
        reasoning_parts = []
        tool_calls_data = []
        finish_reason = "stop"
        msg_id = f"msg_{uuid.uuid4().hex[:24]}"
        total_input_tokens = 0
        total_output_tokens = 0
        ttfb_recorded = False

        buf_chunks = [first_chunk] if first_chunk else []
        try:
            while True:
                if buf_chunks:
                    chunk = buf_chunks.pop(0)
                else:
                    try:
                        chunk = resp.read1(8192)
                    except (http.client.IncompleteRead, http.client.RemoteDisconnected,
                            ConnectionResetError, socket.timeout) as e:
                        _log("MS-ANTH-COLLECT-EOF", f"req={metrics['request_id']} {type(e).__name__}")
                        break
                if not chunk:
                    break
                if not ttfb_recorded:
                    metrics["ttfb_ms"] = int((time.monotonic() - t_start) * 1000)
                    ttfb_recorded = True
                sse_buffer += chunk.decode("utf-8", errors="replace")
                while "\n\n" in sse_buffer:
                    event_str, sse_buffer = sse_buffer.split("\n\n", 1)
                    data_str = ""
                    for line in event_str.split("\n"):
                        if line.startswith("data:"):
                            data_str = line[5:].strip()
                    if not data_str or data_str == "[DONE]":
                        continue
                    try:
                        data = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue
                    msg_id = data.get("id", msg_id)
                    choices = data.get("choices") or [{}]
                    delta = choices[0].get("delta") or {}
                    fr = choices[0].get("finish_reason")
                    rc = delta.get("reasoning_content") or ""
                    if rc: reasoning_parts.append(rc)
                    cont = delta.get("content") or ""
                    if cont: all_content_parts.append(cont)
                    for tc in (delta.get("tool_calls") or []):
                        fn = tc.get("function", {}) or {}
                        if tc.get("id"):
                            tool_calls_data.append({"id": tc["id"], "name": fn.get("name",""), "arguments": fn.get("arguments","")})
                        elif fn.get("arguments") and tool_calls_data:
                            tool_calls_data[-1]["arguments"] += fn["arguments"]
                    chunk_usage = data.get("usage") or {}
                    if chunk_usage:
                        total_input_tokens = chunk_usage.get("prompt_tokens", total_input_tokens)
                        total_output_tokens = chunk_usage.get("completion_tokens", total_output_tokens)
                    if fr:
                        finish_reason = fr
        except (http.client.RemoteDisconnected, ConnectionResetError, OSError,
                http.client.IncompleteRead, socket.timeout) as e:
            _log("MS-ANTH-ERR", f"req={metrics['request_id']} collect {type(e).__name__}: {e}")
            metrics["error_type"] = f"MSAnthCollect_{type(e).__name__}"
        except Exception as e:
            _log("MS-ANTH-ERR", f"req={metrics['request_id']} collect unexpected {type(e).__name__}: {e}")
            metrics["error_type"] = f"MSAnthCollect_{type(e).__name__}"

        content_text = "".join(all_content_parts)
        reasoning_text = "".join(reasoning_parts)

        if finish_reason == "content_filter":
            metrics["error_type"] = "upstream_content_filter"
        elif (not reasoning_text and not content_text and not tool_calls_data):
            metrics["error_type"] = "empty_stream_response"
        elif (finish_reason in ("stop", "tool_calls")
              and (len(reasoning_text) + len(content_text)) < 50
              and not any(tc.get("arguments") for tc in tool_calls_data)
              and metrics.get("total_input_chars", 0) >= 5000):
            metrics["error_type"] = "zombie_empty_completion"

        if metrics.get("error_type"):
            metrics["status"] = 502
        else:
            metrics["status"] = 200
        metrics["duration_ms"] = int((time.monotonic() - t_start) * 1000)
        metrics["input_tokens"] = total_input_tokens
        metrics["output_tokens"] = total_output_tokens
        metrics["finish_reason"] = finish_reason
        _log_metrics(metrics)

        if metrics["status"] >= 400:
            anth_err = convert_error_to_anth(
                {"error": {"message": metrics.get("error_type") or "upstream stream failed"}},
                request_model)
            self._send_json(metrics["status"], anth_err)
            try: conn.close()
            except Exception: pass
            return

        # synthesize non-stream Anthropic message JSON
        oai_json = {
            "id": msg_id,
            "model": request_model,
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": content_text,
                    "reasoning_content": reasoning_text or None,
                    "tool_calls": [
                        {"id": tc["id"], "type": "function",
                         "function": {"name": tc["name"], "arguments": tc["arguments"]}}
                        for tc in tool_calls_data
                    ] or None,
                },
                "finish_reason": finish_reason,
            }],
            "usage": {"prompt_tokens": total_input_tokens, "completion_tokens": total_output_tokens},
        }
        anth_response = oai_nonstream_to_anth(oai_json, request_model)
        self._send_json(metrics["status"], anth_response)
        try: conn.close()
        except Exception: pass

    def _send_json(self, status, body_dict, extra_headers=None):
        try:
            body = json.dumps(body_dict, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            if extra_headers:  # R1648d: anthropic error path adds retry-after on 429
                for k, v in extra_headers.items():
                    self.send_header(k, str(v))
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:
            _log("MS-SEND-ERR", f"_send_json: {type(e).__name__}: {e}")
