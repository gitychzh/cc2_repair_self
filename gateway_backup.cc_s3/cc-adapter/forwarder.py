#!/usr/bin/env python3
"""ChatCompletions 透传 + fallback + circuit (标准库 http.client, 同步).

不持 key, 不做 key 轮转. 转发到 nv_gw(40006)/ms_gw(40007), 由它们处理 key.
与 cx4102 的区别: 不做 Responses↔ChatCompletions 转换, 直接透传 chat 响应.
fallback 时 reminder 插入 chat 响应 (非流: content 前缀; 流: 首 delta 前缀).

R844: fallback 机制对齐 cc4101.
  - 超时三层分离 (connect/header-TTFB/body-idle), 修复 PRIMARY_STREAM_TIMEOUT_S=90s
    混用致 connect 抖动卡 90s + thinking 静默>90s 误判.
  - circuit 三态 CLOSED/OPEN/HALF_OPEN (模块级, time.monotonic).
  - retry primary (fallback 失败后, 门控严格: 仅首字节前失败 retry, 流式晚判定路线不 retry 流中途).
  - 4xx 不 fallback (client 错误同内容重试同失败).
  保留 opclaw4103 特有: R842c content_filter zombie 拦截切 fallback, R766 supplement,
  R790 异常补 content, FALLBACK_NOTICE, prompt 预检, all_tiers_exhausted 判定, FALLBACK_RECOVER_S.
"""
import json
import time
import threading
import socket
import http.client
from urllib.parse import urlparse
from .config import (
    PRIMARY_URL, FALLBACK_URL, PRIMARY_MODEL, FALLBACK_MODEL,
    PRIMARY_HEADER_TIMEOUT, FALLBACK_HEADER_TIMEOUT, UPSTREAM_IDLE_TIMEOUT,
    CC4101_TOTAL_BUDGET_S, RETRY_PRIMARY_AFTER_FALLBACK,
    FALLBACK_TIMEOUT_S, PRIMARY_STREAM_TIMEOUT_S, CIRCUIT_FAILURE_THRESHOLD,
    CIRCUIT_OPEN_S, FALLBACK_RECOVER_S, NV_GW_API_KEY, MS_GW_API_KEY,
    FALLBACK_NOTICE, FALLBACK_ENABLED,
    PROMPT_TOKEN_LIMIT, SUPPLEMENT_REASONING_AS_CONTENT,
)
from .logger import _log

# R763: connect timeout 与 read timeout 分离.
#   改前: HTTPConnection(timeout=PRIMARY_STREAM_TIMEOUT_S=90s) 同时管 connect+read.
#   问题: nv_gw 瞬时网络抖动时 connect 卡 90s 才报 TimeoutError 切 fallback, 浪费 90s.
#   修复: connect 用短 timeout (默认 10s, env CC_CONNECT_TIMEOUT_S 可调),
#         read 用 PRIMARY_HEADER_TIMEOUT / UPSTREAM_IDLE_TIMEOUT.
#   实现: socket.create_connection(connect_timeout) 预连, 再交给 HTTPConnection.sock,
#         getresponse 前 settimeout(header_timeout), 响应头后 settimeout(idle_timeout).
CC_CONNECT_TIMEOUT_S = float(__import__("os").environ.get("CC_CONNECT_TIMEOUT_S", "10"))


# ─── R844: 失败分类 (对齐 cc4101 _UpstreamError) ──────────────────────────
class _UpstreamError(Exception):
    """单次上游调用失败. kind 决定是否 fallback."""
    def __init__(self, kind, status, error_json, message):
        self.kind = kind        # "client_4xx" | "server_5xx" | "conn" | "timeout"
        self.status = status    # HTTP status (0 表示无响应)
        self.error_json = error_json
        self.message = message
        super().__init__(message)


def _restore_read_timeout(conn, read_timeout):
    """R844/R822: 响应头到达后, 把 socket 切回长 idle timeout, 避免短 header timeout
    杀掉慢 body 流 (长 generation / thinking 静默期). http.client read() 用 sock.settimeout."""
    try:
        sock = conn.sock
        if sock is not None:
            sock.settimeout(read_timeout)
    except Exception:
        pass  # best-effort; header timeout 兜底


# ─── R844: circuit 三态 (对齐 cc4101 circuit.py, 模块级, time.monotonic) ──
# CLOSED: primary 健康, 先试. OPEN: primary 降级, 跳过直走 fallback, 到期进 HALF_OPEN.
# HALF_OPEN: 探活一次, 成功→CLOSED, retryable 失败→re-OPEN.
_lock = threading.Lock()
_fail_count = 0          # 连续 retryable primary 失败 (成功归零)
_open_until = 0.0        # monotonic 截止; 0=CLOSED, 过期=HALF_OPEN


def is_primary_open():
    """True = primary 应跳过 (circuit OPEN, 冷却内). False = CLOSED 或 HALF_OPEN (允许探活)."""
    with _lock:
        if _open_until == 0.0:
            return False
        return time.monotonic() < _open_until


def record_primary_success():
    """primary 成功 → CLOSED (清计数 + 清 open_until)."""
    global _fail_count, _open_until
    with _lock:
        _fail_count = 0
        _open_until = 0.0


def record_primary_failure():
    """primary retryable 失败 → 计数+1, 到阈值开路; 已开路则 re-arm.
    client_4xx 不应调用此函数 (client 错误非上游健康信号)."""
    global _fail_count, _open_until
    with _lock:
        now = time.monotonic()
        _fail_count += 1
        if _open_until != 0.0:
            # 已 OPEN 或 HALF_OPEN (过期) — 探活失败, re-arm 冷却
            _open_until = now + CIRCUIT_OPEN_S
            if _fail_count < CIRCUIT_FAILURE_THRESHOLD:
                _fail_count = CIRCUIT_FAILURE_THRESHOLD
            return
        if _fail_count >= CIRCUIT_FAILURE_THRESHOLD:
            _open_until = now + CIRCUIT_OPEN_S
            _log("CIRCUIT-OPEN",
                 f"primary 连续 {_fail_count} 次故障, circuit 打开 {CIRCUIT_OPEN_S}s",
                 failures=_fail_count)


def circuit_state():
    """调试快照: (state, fail_count, seconds_left)."""
    with _lock:
        now = time.monotonic()
        if _open_until == 0.0:
            return "CLOSED", _fail_count, 0
        if now >= _open_until:
            return "HALF_OPEN", _fail_count, 0
        return "OPEN", _fail_count, int(_open_until - now)


# 单次 fallback 后短冷却 (opclaw4103 特有, 独立于 circuit 三态)
_fallback_recover_lock = threading.Lock()
_last_fallback_at = 0.0


def _mark_fallback():
    """记录刚发生一次 fallback, 进入 FALLBACK_RECOVER_S 短冷却.

    R2 fix: 冷却期内不重置计时器, 防止持续 fallback 流量自锁 (每次 fallback
    成功都重置 120s 计时器 → 永远不回 primary)。改为: 仅在冷却期外首次 fallback
    时设置计时器, 冷却期内调用无操作 (让计时器自然到期)。"""
    global _last_fallback_at
    with _fallback_recover_lock:
        now = time.monotonic()
        # 不在冷却期内才设置, 防止持续 fallback 自我重置
        if _last_fallback_at == 0.0 or (now - _last_fallback_at) >= FALLBACK_RECOVER_S:
            _last_fallback_at = now


def _in_fallback_recover():
    """是否在 fallback 后短冷却期内 (应跳过 primary 直走 fallback)."""
    with _fallback_recover_lock:
        if _last_fallback_at == 0.0:
            return False
        return (time.monotonic() - _last_fallback_at) < FALLBACK_RECOVER_S


def should_try_primary_full():
    """完整判定: circuit 未开 + 不在 fallback 短冷却."""
    if is_primary_open():
        return False
    if _in_fallback_recover():
        return False
    return True


def _estimate_tokens(oai_body):
    """粗略估算请求 token 数 (chars/4). 用于 prompt 超限预检."""
    n = 0
    for m in oai_body.get("messages", []):
        if isinstance(m, dict):
            c = m.get("content", "")
            if isinstance(c, list):
                for part in c:
                    if isinstance(part, dict):
                        n += len(str(part.get("text", "")))
            else:
                n += len(str(c))
            # tool_calls / function args 也算
            for k in ("tool_calls", "function_call"):
                if m.get(k):
                    n += len(json.dumps(m[k], ensure_ascii=False))
    for t in oai_body.get("tools", []) or []:
        n += len(json.dumps(t, ensure_ascii=False))
    return n // 4


def _prompt_too_large(oai_body):
    """R766: prompt token 超限预检. 返回 (True, est_tokens) 或 (False, 0)."""
    if PROMPT_TOKEN_LIMIT <= 0:
        return False, 0
    est = _estimate_tokens(oai_body)
    return est > PROMPT_TOKEN_LIMIT, est


def _is_exhausted(body):
    """opclaw4103 特有: body 含 all_tiers_exhausted/exhausted (额度耗尽, 应 fallback)."""
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


def _post_upstream(base_url, model, api_key, oai_body, stream,
                   header_timeout, idle_timeout):
    """同步 POST 到上游, 返回 (resp, conn) 或抛 _UpstreamError.

    R844 超时三层分离:
      connect: CC_CONNECT_TIMEOUT_S (10s) — TCP 建连, socket.create_connection(timeout=)
      header/TTFB: header_timeout (PRIMARY_HEADER_TIMEOUT=25 / FALLBACK_HEADER_TIMEOUT=30) — getresponse
      body idle: idle_timeout (UPSTREAM_IDLE_TIMEOUT=150) — 响应头后 read, _restore_read_timeout 切换
    修复前 PRIMARY_STREAM_TIMEOUT_S=90s 混用 connect+TTFB+body, 致抖动卡 90s + thinking 静默误杀.
    """
    p = urlparse(base_url)
    is_https = (p.scheme == "https")
    port = p.port or (443 if is_https else 80)
    path = p.path.rstrip("/") + "/chat/completions"
    if not path.startswith("/"):
        path = "/" + path
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream" if stream else "application/json",
        "Connection": "close",
    }
    body = dict(oai_body)
    body["model"] = model
    body["stream"] = stream
    body_bytes = json.dumps(body, ensure_ascii=False).encode("utf-8")
    try:
        # R763: 先用短 connect_timeout 做 TCP 建连, 避免抖动时卡满 read timeout.
        sock = socket.create_connection((p.hostname, port), timeout=CC_CONNECT_TIMEOUT_S)
        # 建连成功后, getresponse (TTFB) 阶段用 header_timeout (短, 失败快切 fallback)
        sock.settimeout(header_timeout)
        if is_https:
            import ssl
            ctx = ssl.create_default_context()
            sock = ctx.wrap_socket(sock, server_hostname=p.hostname)
            sock.settimeout(header_timeout)
        conn = http.client.HTTPConnection(p.hostname, port, timeout=header_timeout)
        conn.sock = sock
        try:
            conn.request("POST", path, body=body_bytes, headers=headers)
            resp = conn.getresponse()
        except socket.timeout as e:
            try:
                conn.close()
            except Exception:
                pass
            raise _UpstreamError("timeout", 0, None,
                                 f"header/ttfb timeout after {header_timeout}s: {e}")
        except (ConnectionRefusedError, ConnectionResetError, OSError,
                http.client.HTTPException) as e:
            try:
                conn.close()
            except Exception:
                pass
            raise _UpstreamError("conn", 0, None, f"{type(e).__name__}: {e}")
        # R844: 响应头到达 — 切回长 idle_timeout 供 body 流式读 (容纳 thinking 静默期)
        _restore_read_timeout(conn, idle_timeout)
        # 非 200: 读 body 分类
        if resp.status != 200:
            try:
                err_bytes = resp.read()
                try:
                    err_json = json.loads(err_bytes.decode("utf-8", errors="replace"))
                except Exception:
                    err_json = {"error": {"message": err_bytes.decode("utf-8", errors="replace")[:500]}}
            except Exception:
                err_json = {"error": {"message": f"upstream status {resp.status} (no body)"}}
            try:
                conn.close()
            except Exception:
                pass
            kind = "client_4xx" if 400 <= resp.status < 500 else "server_5xx"
            # opclaw4103 特有: exhausted (额度耗尽) 即使 4xx 也应 fallback, 归为 server_5xx retryable
            if kind == "client_4xx" and _is_exhausted(err_json):
                kind = "server_5xx"
            raise _UpstreamError(kind, resp.status, err_json, f"upstream {resp.status}")
        return resp, conn
    except _UpstreamError:
        raise
    except Exception as e:
        # 兜底: 未预期异常归为 conn
        _log("UPSTREAM-ERR", f"connect to {base_url} failed: {type(e).__name__}: {e}")
        raise _UpstreamError("conn", 0, None, f"{type(e).__name__}: {e}")


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


def _inject_notice_non_stream(chat_body, notice):
    """fallback reminder 插入非流式 chat 响应的 content 前缀."""
    try:
        choices = chat_body.get("choices", [])
        if choices:
            msg = choices[0].get("message", {})
            content = msg.get("content", "")
            msg["content"] = notice + "\n\n" + content if content else notice
    except Exception:
        pass
    return chat_body


def forward_non_stream(oai_body, request_model):
    """非流透传 + fallback. 返回 (chat_completions_dict, status_code).

    R844: 用 _UpstreamError 分类. client_4xx 不 fallback 直接透传; server_5xx/conn/timeout
    record_primary_failure 后进 fallback; fallback 失败 + 门控满足则 retry primary 一次.
    """
    t_start_mon = time.monotonic()

    # Stage 1: primary (circuit OPEN 或 fallback 短冷却内则跳过)
    if FALLBACK_ENABLED and not should_try_primary_full():
        _log("PRIMARY-BREAKER-SKIP", "primary 跳过 (circuit OPEN 或 fallback 冷却), 直走 fallback")
    else:
        try:
            resp, conn = _post_upstream(PRIMARY_URL, PRIMARY_MODEL, NV_GW_API_KEY,
                                         oai_body, False,
                                         PRIMARY_HEADER_TIMEOUT, UPSTREAM_IDLE_TIMEOUT)
            body = _read_body(resp)
            status = resp.status
            try:
                conn.close()
            except Exception:
                pass
            record_primary_success()
            return body, status
        except _UpstreamError as e:
            ms = int((time.monotonic() - t_start_mon) * 1000)
            if e.kind == "client_4xx":
                # client 错误不 fallback, 透传错误
                _log("PRIMARY-4xx", f"nv_gw client {e.status}, 不 fallback 直接透传 ({ms}ms)")
                return e.error_json, e.status
            _log("PRIMARY-FAIL", f"nv_gw {e.kind} status={e.status} after {ms}ms, 触发 fallback: {e.message[:160]}",
                 status=e.status, err=str(e.message)[:200])
            record_primary_failure()

    if not FALLBACK_ENABLED:
        return {"error": {"message": "primary 不可用且 fallback 已禁用",
                          "type": "primary_down_no_fallback"}}, 503

    # Stage 2: fallback
    try:
        resp, conn = _post_upstream(FALLBACK_URL, FALLBACK_MODEL, MS_GW_API_KEY,
                                    oai_body, False,
                                    FALLBACK_HEADER_TIMEOUT, UPSTREAM_IDLE_TIMEOUT)
        body = _read_body(resp)
        status = resp.status
        try:
            conn.close()
        except Exception:
            pass
        if status >= 400:
            return body, status
        _mark_fallback()
        _log("FALLBACK", "从 primary 切到 ms_gw, 提醒插入 content 前缀")
        return _inject_notice_non_stream(body, FALLBACK_NOTICE), 200
    except _UpstreamError as e:
        fb_ms = int((time.monotonic() - t_start_mon) * 1000)
        _log("FALLBACK-FAIL", f"ms_gw {e.kind} status={e.status} after {fb_ms}ms: {e.message[:160]}")
        # R844: retry primary 一次 (门控: 开关 + 预算 + circuit 未开)
        elapsed_total = time.monotonic() - t_start_mon
        remaining = CC4101_TOTAL_BUDGET_S - elapsed_total
        if (RETRY_PRIMARY_AFTER_FALLBACK and remaining >= PRIMARY_HEADER_TIMEOUT
                and not is_primary_open()):
            try:
                resp, conn = _post_upstream(PRIMARY_URL, PRIMARY_MODEL, NV_GW_API_KEY,
                                            oai_body, False,
                                            PRIMARY_HEADER_TIMEOUT, UPSTREAM_IDLE_TIMEOUT)
                body = _read_body(resp)
                status = resp.status
                try:
                    conn.close()
                except Exception:
                    pass
                record_primary_success()
                _log("PRIMARY-RETRY-OK", f"primary retry 成功 (fallback {e.kind} {fb_ms}ms 后)")
                return body, status
            except _UpstreamError as e2:
                _log("PRIMARY-RETRY-FAIL", f"primary retry 也失败: {e2.kind} {e2.status}")
                if e2.kind == "client_4xx":
                    return e2.error_json, e2.status
                record_primary_failure()
        return {"error": {"message": "primary 和 fallback 均不可用",
                          "type": "all_backends_down"}}, 503
    except Exception as e:
        _log("FALLBACK-ERR", f"fallback unexpected {type(e).__name__}: {e}")
        return {"error": {"message": "primary 和 fallback 均不可用",
                          "type": "all_backends_down"}}, 503


def _stream_from_upstream(resp, conn, notice, fallback_used):
    """从上游 SSE 读 chat-completions chunk → 原样 yield (event_name, raw_dict).
    fallback_used 时在第一个 content delta 前插 notice.
    流结束/异常时尽量闭环 ([DONE]).

    R766: 若 SUPPLEMENT_REASONING_AS_CONTENT 开启, 且整流没发过 content delta 但
    累积了 reasoning_content (glm5_2_nv thinking 模式: 只发 reasoning 不发 content),
    流末补一个 content chunk = reasoning 全文, 让客户端 (openclaw) 收到 content 不超时.

    body read 超时由 _post_upstream 的 _restore_read_timeout 设好 (UPSTREAM_IDLE_TIMEOUT=150s),
    本函数 resp.read(8192) 继承该 idle timeout, 容纳 thinking 静默期.
    """
    notice_sent = not fallback_used  # primary 模式不插 notice
    reasoning_buf = []  # R766: 累积 reasoning_content
    content_seen = False  # R766: 是否发过 content delta
    tool_calls_seen = False  # R841b: 是否见过 tool_calls (工具调用响应绝不触发 SUPPLEMENT)
    last_finish_reason = None
    last_chunk_template = None  # R766: 留最后一个 chunk 做模板, 补 content 用
    try:
        for chunk_data in _iter_sse_chunks(resp):
            try:
                choices = chunk_data.get("choices", [])
                if choices:
                    d = choices[0].get("delta", {})
                    rc = d.get("reasoning_content")
                    if rc:
                        reasoning_buf.append(str(rc))
                    # R766c: content="" (空字符串) 不算有 content (ms_gw 返回 content="" + reasoning)
                    c_val = d.get("content")
                    if isinstance(c_val, str) and c_val:
                        content_seen = True
                    # R841b: 标记见过 tool_calls — 工具调用响应绝不触发 SUPPLEMENT
                    # (否则 reasoning 塞 content 污染回复 + 覆盖 finish_reason=tool_calls→stop 矛盾)
                    if d.get("tool_calls"):
                        tool_calls_seen = True
                    fr = choices[0].get("finish_reason")
                    if fr:
                        last_finish_reason = fr
                        last_chunk_template = chunk_data
            except Exception:
                pass
            # fallback 模式: 在第一个有 choices[].delta.content 的 chunk 前插 notice
            if not notice_sent:
                try:
                    choices = chunk_data.get("choices", [])
                    # R766d: content 非空字符串才插 notice (ms_gw content="" 不触发)
                    _c = choices[0].get("delta", {}).get("content") if choices else None
                    if isinstance(_c, str) and _c:
                        notice_sent = True
                        notice_chunk = json.loads(json.dumps(chunk_data))  # deep copy
                        d = notice_chunk["choices"][0]["delta"]
                        d["content"] = notice + "\n\n"
                        yield ("message", notice_chunk)
                except Exception:
                    pass
            # R842c: 检测 nv_gw R840 发的 content_filter zombie 信号.
            # nv_gw 检测到空僵尸响应 (fr=stop + content<50 + input>5000) 时, 主动发一个
            # finish_reason=content_filter chunk 替代原 stop chunk, 意在让 openclaw throw.
            # 但 openclaw mapOpenAIStopReason(content_filter)→stopReason=error, 且
            # classifyAssistantFailoverReason 返回 null (content_filter 不匹配任何 failover 模式)
            # → openclaw 走 empty-error-retry 重试同 provider 3 次全 zombie → LLM failed, 永不 fallback.
            # 修复: opclaw4103 在此拦截 content_filter, 不透传给 openclaw, 改发 ("content_filter_zombie", None)
            # 信号让 forward_stream 切 ms_gw fallback (已发过的少量 content delta 影响可忽略, content_chars<=50).
            if fr == "content_filter":
                _log("CONTENT_FILTER_ZOMBIE", "primary 流中检测到 content_filter (R840 zombie), 切 ms_gw fallback")
                yield ("content_filter_zombie", None)
                return
            yield ("message", chunk_data)
        # R766: 流末补 content (thinking 模式只发 reasoning, content=null)
        if SUPPLEMENT_REASONING_AS_CONTENT and not content_seen and not tool_calls_seen and reasoning_buf:
            full_reasoning = "".join(reasoning_buf)
            _log("SUPPLEMENT-CONTENT",
                 f"流末补 content: 整流无 content delta, reasoning {len(full_reasoning)} chars, "
                 f"finish={last_finish_reason}")
            tmpl = json.loads(json.dumps(last_chunk_template)) if last_chunk_template else {
                "choices": [{"index": 0, "delta": {}, "finish_reason": None}]
            }
            ch = tmpl["choices"][0]
            d = ch.setdefault("delta", {})
            d.pop("reasoning_content", None)
            d["content"] = full_reasoning
            # R841b: 不强制 stop — 保留原 last_finish_reason, 若为 tool_calls 则保持 tool_calls
            # (避免同流不同 chunk 的 finish_reason 矛盾; 仅 None 时默认 stop)
            ch["finish_reason"] = last_finish_reason if last_finish_reason else "stop"
            yield ("message", tmpl)
        # 正常结束: 发 done (不在 finally 里, 避免 GeneratorExit 时 yield 报错)
        yield ("done", None)
    except Exception as e:
        _log("STREAM-UPSTREAM-ERR", f"上游流读取失败: {type(e).__name__}: {e}")
        # R790: 流中途异常 (timeout 等) 时, 若已累积 reasoning 但未发 content,
        # 补一个 content chunk = reasoning 全文, 避免客户端 (openclaw) 收空 content 卡死.
        # 复用 supplement 语义 (仅 SUPPLEMENT_REASONING_AS_CONTENT 开启时生效).
        if SUPPLEMENT_REASONING_AS_CONTENT and not content_seen and not tool_calls_seen and reasoning_buf:
            full_reasoning = "".join(reasoning_buf)
            _log("SUPPLEMENT-CONTENT-ON-ERR",
                 f"流中途异常补 content: reasoning {len(full_reasoning)} chars, finish={last_finish_reason}")
            tmpl = json.loads(json.dumps(last_chunk_template)) if last_chunk_template else {
                "choices": [{"index": 0, "delta": {}, "finish_reason": None}]
            }
            ch = tmpl["choices"][0]
            d = ch.setdefault("delta", {})
            d.pop("reasoning_content", None)
            d["content"] = full_reasoning
            ch["finish_reason"] = "stop"
            yield ("message", tmpl)
        yield ("done", None)
    finally:
        try:
            conn.close()
        except Exception:
            pass


def forward_stream(oai_body, request_model):
    """流式透传 + fallback. 生成器, yield (event_name, payload).

    R844 策略 (对齐 cc4101 + 保留 opclaw4103 晚判定):
      - primary 首字节前失败 (连接失败 / 5xx / header 超时 / circuit OPEN) → 静默切 fallback
      - primary 正常 2xx → 透传; 流中 content_filter zombie (R842c) → break 切 fallback
      - primary 流中途其它异常 → 已发部分流无法回溯, 直接收尾 (不切 fallback)
      - fallback 首字节前失败 + 门控满足 → retry primary 一次 (流中途失败不 retry, 避拼接)
      - 走 fallback 时在首个 content delta 前插 notice (不污染 reasoning)
    """
    t_start_mon = time.monotonic()

    # Stage 1: primary (circuit OPEN 或 fallback 短冷却内则跳过)
    if FALLBACK_ENABLED and not should_try_primary_full():
        _log("PRIMARY-BREAKER-SKIP-STREAM", "primary 流式跳过 (circuit OPEN 或 fallback 冷却), 直走 fallback")
    else:
        try:
            resp, conn = _post_upstream(PRIMARY_URL, PRIMARY_MODEL, NV_GW_API_KEY,
                                        oai_body, True,
                                        PRIMARY_HEADER_TIMEOUT, UPSTREAM_IDLE_TIMEOUT)
        except _UpstreamError as e:
            ms = int((time.monotonic() - t_start_mon) * 1000)
            if e.kind == "client_4xx":
                # client 4xx 流式: 读 body 发 err_chunk 透传, 不切 fallback
                _log("PRIMARY-4xx-STREAM", f"nv_gw client {e.status} stream, 透传错误 ({ms}ms)")
                err_chunk = {
                    "choices": [{"index": 0, "delta": {
                        "content": f"⚠️ [primary 错误] {json.dumps(e.error_json, ensure_ascii=False)[:400]}"
                    }, "finish_reason": None}]
                }
                yield ("message", err_chunk)
                yield ("done", None)
                return
            _log("PRIMARY-FAIL-STREAM", f"nv_gw 流式 {e.kind} status={e.status} after {ms}ms, 切 fallback: {e.message[:160]}")
            record_primary_failure()
            # 落到下方 fallback 流逻辑
        else:
            # primary 连接成功 (2xx): 透传, 流中途 content_filter zombie 切 fallback
            # R842c: 若 nv_gw R840 发了 content_filter zombie 信号, 切 ms_gw fallback
            content_filter_zombie = False
            for ev in _stream_from_upstream(resp, conn, FALLBACK_NOTICE, False):
                if ev[0] == "content_filter_zombie":
                    content_filter_zombie = True
                    break  # 不 yield 信号本身, 中断 primary 流
                yield ev
            if content_filter_zombie:
                _log("PRIMARY-ZOMBIE-FALLBACK", "nv_gw 返回 content_filter zombie, 切 ms_gw fallback 流式")
                record_primary_failure()
                _mark_fallback()
                # 落到下面的 fallback 流逻辑
            else:
                record_primary_success()
                return

    if not FALLBACK_ENABLED:
        # fallback 禁用: 发一个错误 chunk + done
        err_chunk = {
            "choices": [{"index": 0, "delta": {"content": "⚠️ primary 不可用且 fallback 已禁用"},
                          "finish_reason": None}]
        }
        yield ("message", err_chunk)
        yield ("done", None)
        return

    # Stage 2: fallback 流 (circuit 打开 / primary 首字节前失败 / content_filter zombie)
    try:
        resp, conn = _post_upstream(FALLBACK_URL, FALLBACK_MODEL, MS_GW_API_KEY,
                                    oai_body, True,
                                    FALLBACK_HEADER_TIMEOUT, UPSTREAM_IDLE_TIMEOUT)
    except _UpstreamError as e:
        ms = int((time.monotonic() - t_start_mon) * 1000)
        _log("FALLBACK-FAIL-STREAM", f"ms_gw 流式 {e.kind} status={e.status} after {ms}ms: {e.message[:160]}")
        # R844: retry primary 一次 — 仅 fallback 首字节前失败 (未发过 fallback content, 拼接安全)
        elapsed_total = time.monotonic() - t_start_mon
        remaining = CC4101_TOTAL_BUDGET_S - elapsed_total
        retried = False
        if (RETRY_PRIMARY_AFTER_FALLBACK and remaining >= PRIMARY_HEADER_TIMEOUT
                and not is_primary_open()):
            try:
                resp, conn = _post_upstream(PRIMARY_URL, PRIMARY_MODEL, NV_GW_API_KEY,
                                            oai_body, True,
                                            PRIMARY_HEADER_TIMEOUT, UPSTREAM_IDLE_TIMEOUT)
                _log("PRIMARY-RETRY-OK-STREAM", f"primary 流式 retry 成功 (fallback {e.kind} {ms}ms 后)")
                record_primary_success()
                retried = True
                # 透传 primary retry 流 (无 notice, 这是 primary 不是 fallback)
                for ev in _stream_from_upstream(resp, conn, FALLBACK_NOTICE, False):
                    if ev[0] == "content_filter_zombie":
                        # retry 又遇 zombie — 不再递归切, 补 done 收尾
                        _log("PRIMARY-RETRY-ZOMBIE", "primary retry 又遇 content_filter zombie, 收尾")
                        record_primary_failure()
                        yield ("done", None)
                        return
                    yield ev
                return
            except _UpstreamError as e2:
                _log("PRIMARY-RETRY-FAIL-STREAM", f"primary 流式 retry 也失败: {e2.kind} {e2.status}")
                record_primary_failure()
        if not retried:
            err_chunk = {
                "choices": [{"index": 0, "delta": {
                    "content": "⚠️ primary 和 fallback 均不可用, 请稍后重试."
                }, "finish_reason": None}]
            }
            yield ("message", err_chunk)
            yield ("done", None)
            return
    else:
        if resp.status >= 400:
            body = _read_body(resp)
            try:
                conn.close()
            except Exception:
                pass
            err_msg = json.dumps(body, ensure_ascii=False)[:500]
            _log("FALLBACK-STREAM-ERR", f"ms_gw status={resp.status}: {err_msg[:200]}")
            err_chunk = {
                "choices": [{"index": 0, "delta": {
                    "content": f"⚠️ [fallback 错误] {err_msg}"
                }, "finish_reason": None}]
            }
            yield ("message", err_chunk)
            yield ("done", None)
            return

        _mark_fallback()
        _log("FALLBACK-STREAM", "从 primary 切到 ms_gw 流式, 提醒插入首 delta 前")
        for ev in _stream_from_upstream(resp, conn, FALLBACK_NOTICE, True):
            yield ev
