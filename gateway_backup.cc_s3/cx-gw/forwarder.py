#!/usr/bin/env python3
"""无状态转发 + fallback + circuit (标准库 http.client, 同步).

不持 key, 不做 key 轮转. 转发到 nv_gw(40006)/ms_gw(40007), 由它们处理 key.
"""
import json
import time
import threading
import http.client
from urllib.parse import urlparse
from .config import (
    PRIMARY_URL, FALLBACK_URL, PRIMARY_MODEL, FALLBACK_MODEL,
    FALLBACK_TIMEOUT_S, CIRCUIT_FAILURE_THRESHOLD, CIRCUIT_OPEN_S,
    FALLBACK_RECOVER_S, NV_GW_API_KEY, MS_GW_API_KEY, FALLBACK_NOTICE,
)
from .logger import _log


class CircuitState:
    def __init__(self):
        self._lock = threading.Lock()
        self.consecutive_failures = 0
        self.circuit_open_until = 0.0
        self.last_fallback_at = 0.0

    def should_try_primary(self):
        with self._lock:
            now = time.time()
            if now < self.circuit_open_until:
                return False
            if now - self.last_fallback_at < FALLBACK_RECOVER_S:
                return False
            return True

    def record_primary_failure(self):
        with self._lock:
            self.consecutive_failures += 1
            self.last_fallback_at = time.time()
            if self.consecutive_failures >= CIRCUIT_FAILURE_THRESHOLD:
                self.circuit_open_until = time.time() + CIRCUIT_OPEN_S
                _log("CIRCUIT-OPEN",
                     f"primary 连续 {self.consecutive_failures} 次故障, circuit 打开 {CIRCUIT_OPEN_S}s",
                     failures=self.consecutive_failures)

    def record_primary_success(self):
        with self._lock:
            self.consecutive_failures = 0


_circuit = CircuitState()


def _is_primary_failure(status, body):
    """自包含判定: 5xx / all_tiers_exhausted / None(连接失败)."""
    if status is None:
        return True
    if status >= 500:
        return True
    if isinstance(body, dict):
        err = body.get("error", {})
        msg = ""
        if isinstance(err, dict):
            msg = str(err.get("message", "")) + " " + str(err.get("type", ""))
        elif isinstance(err, str):
            msg = err
        if "all_tiers_exhausted" in msg or "exhausted" in msg.lower():
            return True
    return False


def _post_upstream(base_url, model, api_key, oai_body, stream, timeout_s):
    """同步 POST 到上游, 返回 (resp, conn) 或 (None, error_str)."""
    p = urlparse(base_url)
    conn_cls = http.client.HTTPSConnection if p.scheme == "https" else http.client.HTTPConnection
    path = p.path.rstrip("/") + "/chat/completions"
    if not path.startswith("/"):
        path = "/" + path
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream" if stream else "application/json",
    }
    body = dict(oai_body)
    body["model"] = model
    body["stream"] = stream
    body_bytes = json.dumps(body).encode("utf-8")
    try:
        conn = conn_cls(p.hostname, p.port or (443 if p.scheme == "https" else 80), timeout=timeout_s)
        conn.request("POST", path, body=body_bytes, headers=headers)
        resp = conn.getresponse()
        return resp, conn
    except Exception as e:
        _log("UPSTREAM-ERR", f"connect to {base_url} failed: {type(e).__name__}: {e}")
        return None, str(e)


def _read_body(resp):
    try:
        raw = resp.read()
        return json.loads(raw.decode("utf-8"))
    except Exception as e:
        _log("READ-ERR", f"read upstream body failed: {e}")
        return {"_raw_read_error": str(e)}


def _iter_sse_chunks(resp):
    """从 http.client resp 读 SSE, yield 每个 data: 行解析后的 dict.
    遇到 [DONE] 停止. 出错抛异常."""
    buffer = ""
    while True:
        chunk = resp.read(8192)
        if not chunk:
            return
        buffer += chunk.decode("utf-8", errors="replace")
        while "\n\n" in buffer:
            event_str, buffer = buffer.split("\n\n", 1)
            for line in event_str.split("\n"):
                if not line.startswith("data:"):
                    continue
                data_str = line[5:].strip()
                if data_str == "[DONE]":
                    return
                try:
                    yield json.loads(data_str)
                except Exception:
                    continue


def forward_non_stream(oai_body, request_model):
    """非流转发 + fallback. 返回 (responses_api_dict, status_code)."""
    try_primary = _circuit.should_try_primary()

    if try_primary:
        resp, conn = _post_upstream(PRIMARY_URL, PRIMARY_MODEL, NV_GW_API_KEY,
                                    oai_body, False, FALLBACK_TIMEOUT_S)
        if resp is not None:
            status = resp.status
            body = _read_body(resp)
            try:
                conn.close()
            except Exception:
                pass
            if not _is_primary_failure(status, body):
                _circuit.record_primary_success()
                return _chat_to_responses_safe(body, request_model, None), 200
            _log("PRIMARY-FAIL", f"nv_gw status={status}, 触发 fallback",
                 status=status, err=str(body)[:200])
        else:
            _log("PRIMARY-FAIL", "nv_gw 连接失败, 触发 fallback")
        _circuit.record_primary_failure()

    # fallback
    resp, conn = _post_upstream(FALLBACK_URL, FALLBACK_MODEL, MS_GW_API_KEY,
                                oai_body, False, FALLBACK_TIMEOUT_S)
    if resp is None:
        _log("FALLBACK-FAIL", "ms_gw 连接失败")
        return {"error": {"message": "cx4102: primary 和 fallback 均不可用",
                          "type": "cx_all_backends_down"}}, 503
    status = resp.status
    body = _read_body(resp)
    try:
        conn.close()
    except Exception:
        pass
    if status >= 400:
        return body, status
    return _chat_to_responses_safe(body, request_model, FALLBACK_NOTICE), 200


def _stream_from_upstream(resp, conn, converter, fallback_used):
    """通用: 从上游 SSE 读 chunk → 转换 → yield (event_name, payload).
    流结束后发 final_events. 异常时也发 final_events (尽量闭环)."""
    try:
        for chunk_data in _iter_sse_chunks(resp):
            for ev in converter.feed_chunk(chunk_data):
                yield ev
        for ev in converter.final_events():
            yield ev
    except Exception as e:
        _log("STREAM-UPSTREAM-ERR", f"上游流读取失败: {type(e).__name__}: {e}")
        for ev in converter.final_events():
            yield ev
    finally:
        try:
            conn.close()
        except Exception:
            pass


def forward_stream(oai_body, request_model):
    """流式转发 + fallback. 生成器, yield (event_name, payload).

    策略:
      - primary 首字节前失败 (连接失败 / 5xx) → 静默切 fallback, fallback 用独立 converter
      - primary 流中途失败 → 已发部分流无法回溯, 发 final 收尾 (不切 fallback)
      - 走了 fallback 时 converter.fallback_used=True, 提醒放 response.completed metadata
        (不插 output_text delta, 避免污染 codex reasoning 流)
    """
    from .codex import StreamConverter
    try_primary = _circuit.should_try_primary()

    if try_primary:
        resp, conn = _post_upstream(PRIMARY_URL, PRIMARY_MODEL, NV_GW_API_KEY,
                                    oai_body, True, FALLBACK_TIMEOUT_S)
        if resp is None:
            # 连接失败 → 直接走 fallback
            _log("PRIMARY-FAIL-STREAM", "nv_gw 流式连接失败, 切 fallback")
            _circuit.record_primary_failure()
        elif resp.status >= 500:
            _log("PRIMARY-FAIL-STREAM",
                 f"nv_gw 流式 5xx: status={resp.status}, 切 fallback")
            try:
                conn.close()
            except Exception:
                pass
            _circuit.record_primary_failure()
        else:
            # primary 正常 (2xx/4xx): 用 primary converter, 流中途失败不切 fallback
            converter = StreamConverter(request_model)
            for ev in converter.initial_events():
                yield ev
            for ev in _stream_from_upstream(resp, conn, converter, False):
                yield ev
            _circuit.record_primary_success()
            return

    # fallback 流 (circuit 打开 / primary 首字节前失败)
    converter = StreamConverter(request_model)
    converter.fallback_used = True
    for ev in converter.initial_events():
        yield ev

    resp, conn = _post_upstream(FALLBACK_URL, FALLBACK_MODEL, MS_GW_API_KEY,
                                oai_body, True, FALLBACK_TIMEOUT_S)
    if resp is None:
        _log("FALLBACK-FAIL-STREAM", "ms_gw 流式连接失败")
        yield ("response.output_text.delta", {
            "type": "response.output_text.delta", "output_index": 0, "content_index": 0,
            "delta": "⚠️ [cx4102] primary 和 fallback 均不可用, 请稍后重试.",
        })
        converter.text_buffer += "⚠️ [cx4102] primary 和 fallback 均不可用, 请稍后重试."
        for ev in converter.final_events():
            yield ev
        return

    if resp.status >= 400:
        # fallback 返回错误 (非 SSE), 读 body 转成 output_text
        body = _read_body(resp)
        try:
            conn.close()
        except Exception:
            pass
        err_msg = json.dumps(body, ensure_ascii=False)[:500]
        _log("FALLBACK-STREAM-ERR", f"ms_gw status={resp.status}: {err_msg[:200]}")
        yield ("response.output_text.delta", {
            "type": "response.output_text.delta", "output_index": 0, "content_index": 0,
            "delta": f"⚠️ [cx4102 fallback 错误] {err_msg}",
        })
        converter.text_buffer += f"⚠️ [cx4102 fallback 错误] {err_msg}"
        for ev in converter.final_events():
            yield ev
        return

    _log("FALLBACK-STREAM", "从 primary 切到 ms_gw 流式, 提醒放 metadata")
    for ev in _stream_from_upstream(resp, conn, converter, True):
        yield ev


def _chat_to_responses_safe(body, request_model, fallback_notice=None):
    from .codex import chat_to_responses
    try:
        return chat_to_responses(body, request_model, fallback_notice)
    except Exception as e:
        _log("CONVERT-ERR", f"chat_to_responses failed: {e}", body=str(body)[:300])
        return {
            "id": f"resp_err_{int(time.time())}", "object": "response",
            "status": "completed", "output": [{
                "type": "message", "id": f"msg_err_{int(time.time())}", "role": "assistant",
                "content": [{"type": "output_text", "text": "[cx4102 转换错误] " + str(body)[:500]}],
                "status": "completed",
            }], "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}, "metadata": {},
        }
