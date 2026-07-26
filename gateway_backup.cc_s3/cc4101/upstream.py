#!/usr/bin/env python3
"""Upstream request executor for cc4101 — nv_gw glm5_2_nv ONLY (R854).

R854: ms_gw/40007 fallback removed per user request. NV glm5.2 only.
  1. Try PRIMARY (nv_gw glm5_2_nv) with stream=true.
  2. On failure (5xx/conn/timeout/empty-stream/zombie) → return error to handler;
     CC retries the whole request. Circuit breaker opens after N consecutive
     fails → fast-fail 503 (no fallback to serve).

The handler (handlers.py) owns response formatting (stream or collect) and the
metrics lifecycle. This module returns an UpstreamResult with resp+conn ready
to read (stream) or an error classification.
"""
import json
import time
import http.client
import socket
import urllib.parse

from .config import (
    UPSTREAM_TIMEOUT,
    UPSTREAM_IDLE_TIMEOUT,
    UPSTREAM_HEADER_TIMEOUT,
    PRIMARY_HEADER_TIMEOUT,
    CC4101_STREAM_POLL_S,
    PRIMARY_UPSTREAM_URL, PRIMARY_UPSTREAM_MODEL, PRIMARY_UPSTREAM_TOKEN,
    FALLBACK_UPSTREAM_URL, FALLBACK_UPSTREAM_MODEL, FALLBACK_UPSTREAM_TOKEN,
    FORCE_FALLBACK_MODEL,
)
from .logger import _log, _log_error_detail
from .circuit import is_primary_open, record_primary_success, record_primary_failure


class UpstreamResult:
    def __init__(self):
        self.success = False
        self.resp = None          # http.client.HTTPResponse (ready to read SSE)
        self.conn = None          # http.client.HTTPConnection (caller closes)
        self.upstream_used = None  # "primary" (R854: only stage)
        self.mapped_model = None   # the model id sent upstream
        # error classification (when not success)
        self.error_kind = None     # "client_4xx" | "server_5xx" | "conn" | "timeout" | "empty_stream"
        self.error_status = 0      # upstream HTTP status (for 4xx/5xx)
        self.error_json = None     # upstream error body (dict) — for 4xx
        self.error_message = ""    # human-readable
        self.elapsed_ms = 0


def _parse_url(url):
    parsed = urllib.parse.urlparse(url)
    host = parsed.hostname
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    path = parsed.path or "/v1/chat/completions"
    if parsed.query:
        path += "?" + parsed.query
    return parsed.scheme, host, port, path


def _restore_read_timeout(conn, read_timeout, resp=None):
    """R822/R853: after response headers arrive, switch the socket to the per-read
    poll timeout (CC4101_STREAM_POLL_S=30s) so resp.read(8192) raises socket.timeout
    every 30s → stream.py read loop wakes → stall-watcher 双门槛 gets a checkpoint.
    R853 真根因: conn.sock 在 getresponse() 后是 None (http.client 把 sock 移到
    resp.fp.raw._sock) → 旧代码 if sock is not None 失败静默 pass → 30s 超时根本没
    应用到流式 read → resp.read() 无限阻塞 → stall-watcher 永远不跑 → R847/R850
    idle-gap/total-deadline 全变死代码 → 8min+ 挂死 CC 永远收不到 api_error.
    现: 优先 conn.sock, None 则从 resp.fp.raw._sock 取真 socket."""
    try:
        sock = conn.sock
        if sock is None and resp is not None:
            # R853: http.client detach 后真 socket 在 resp.fp.raw._sock
            try:
                sock = resp.fp.raw._sock
            except Exception:
                sock = None
        if sock is not None:
            sock.settimeout(read_timeout)
            return True
    except Exception:
        pass  # best-effort; header timeout will still apply as fallback
    return False


def _call_upstream(oai_body, url, model, token, request_id, timeout=UPSTREAM_TIMEOUT, header_timeout=None, idle_timeout=CC4101_STREAM_POLL_S, caller_tag="cc-via-cc4101"):
    """Make one streaming POST to an upstream. Returns (resp, conn) on HTTP 200,
    or raises _UpstreamError with classification on any failure.

    We do NOT read the body here — the caller streams it. For non-200 we read
    the error body for classification.

    R854: header_timeout is the connect+TTFB timeout. If None, falls back to
    min(timeout, UPSTREAM_HEADER_TIMEOUT). Caller passes PRIMARY_HEADER_TIMEOUT.

    R1700: caller_tag 注入 X-Caller header, 让下游 nv_gw/ms_gw 能区分来源
      (primary vs fallback), 全链路日志可诊断"ms fallback 次数". primary 传
      "cc4101-primary", fallback 传 "cc4101-fallback". nv_gw _detect_caller
      对 X-Caller 取值即用(无需改 nv_gw 代码); ms_gw 需识别 cc4101 前缀.
    """
    scheme, host, port, path = _parse_url(url)
    if header_timeout is None:
        header_timeout = min(timeout, UPSTREAM_HEADER_TIMEOUT)
    # R1602: 删除 `header_timeout = min(header_timeout, timeout)` 封顶. 旧逻辑用 body
    # timeout (UPSTREAM_TIMEOUT) 封顶 header_timeout, 导致 R1420 的 120s 缩放被
    # min(120, UPSTREAM_TIMEOUT=60)=60 砍掉, 120s 从未生效. 2026-07-16 01:35 实锤:
    # NVCF glm5_2_nv 劣化时 nv_gw mode chain budget=120s 合法耗时 (5 key×mode 重试),
    # 但 cc4101 header 60s 就超时误判 primary 失败, 累计5次 OPEN breaker → 503 死循环.
    # header (getresponse 等首字节) 与 body (流式 read poll, CC4101_STREAM_POLL_S) 超时
    # 解耦: header 给到 R1420 缩放值 (≤120s), body 由 stream poll + idle-watcher 兜底.
    if scheme == "https":
        conn = http.client.HTTPSConnection(host, port, timeout=header_timeout)
    else:
        conn = http.client.HTTPConnection(host, port, timeout=header_timeout)

    # R1705: 透传 anthropic body (不做 anth→oai 转换, 转换下沉 nv_gw/ms_gw /v1/messages 端点).
    # 仅改写 model 字段做路由 (CC 发 claude-opus-4-8 → 改 glm5_2_nv/glm5_2_ms, 否则 nv_gw
    # detect_nv_model 把 claude-* fallback 到 dsv4p_nv 路由错误). 深拷贝由调用方做, 此处只 encode.
    body_bytes = json.dumps(oai_body, ensure_ascii=False).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
        "Accept": "text/event-stream",
        "Connection": "close",
        "anthropic-version": "2023-06-01",
        # R1700: 标记本请求来源, 供下游网关日志区分 primary/fallback 流量.
        # nv_gw/ms_gw _detect_caller 读取 X-Caller 后记入 metrics.caller.
        "X-Caller": caller_tag,
    }
    try:
        conn.request("POST", path, body=body_bytes, headers=headers)
        resp = conn.getresponse()
    except socket.timeout as e:
        try:
            conn.close()
        except Exception:
            pass
        raise _UpstreamError("timeout", 0, None, f"header/ttfb timeout after {header_timeout}s: {e}")
    except (ConnectionRefusedError, ConnectionResetError, OSError,
            http.client.HTTPException) as e:
        try:
            conn.close()
        except Exception:
            pass
        raise _UpstreamError("conn", 0, None, f"{type(e).__name__}: {e}")

    # R822/R830/R845: response header received — restore read timeout for body streaming.
    # R845 B7: per-read 改用短轮询 CC4101_STREAM_POLL_S(默认30s) 而非旧 UPSTREAM_IDLE_TIMEOUT(150s),
    # 让 stream.py 主循环的双门槛 stall-watcher 在 read 阻塞时也能获得检查点 (每 POLL_S 抛 socket.timeout→continue→检查).
    # UPSTREAM_IDLE_TIMEOUT(150s) 退为"总预算"语义, 由 stream.py 的 except 用 elapsed>=UPSTREAM_IDLE_TIMEOUT 判定真 idle.
    _restore_read_timeout(conn, idle_timeout, resp=resp)

    if resp.status != 200:
        # Read error body for classification
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
        raise _UpstreamError(kind, resp.status, err_json, f"upstream {resp.status}")

    # 200 — caller will stream. (Empty-stream detection happens in stream.py
    # when no content arrives; that's a fallback trigger, handled by caller.)
    return resp, conn


class _UpstreamError(Exception):
    def __init__(self, kind, status, error_json, message):
        self.kind = kind
        self.status = status
        self.error_json = error_json
        self.message = message
        super().__init__(message)


def execute_request(oai_body, request_id, metrics, t_start):
    """Try primary (nv_gw glm5_2_nv); on retryable failure try fallback (ms_gw glm5_2_ms).

    R854 曾删 fallback; R1643 加回(末位兜底, nv 不限额优先, ms 限额仅兜底):
      - primary circuit OPEN -> 直走 fallback(省 nv 超时, 不每条等 60-120s).
      - CLOSED 时 primary 先试; 5xx/conn/timeout 失败 -> 立即试 fallback 一次.
      - client_4xx 不 fallback(请求级错误, ms 也会 4xx).
      - fallback 成败不计 breaker(breaker 只盯 primary 健康).
    R1705: oai_body 实为原始 anthropic body (cc4101 不再做 anth→oai 转换, 透传给 nv_gw/ms_gw
    /v1/messages 端点, 转换下沉). 仅 model 字段在 _try_primary/_try_fallback 内改写做路由.
    """
    result = UpstreamResult()
    attempts = []  # for metrics
    t_start_mon = time.monotonic()  # R823: total-budget baseline across stages

    def _try_primary(stage_label):
        """One primary attempt. Returns True on success, client_4xx for
        non-retryable client errors, False for retryable failures."""
        t0 = time.monotonic()
        try:
            # R1420: header_timeout 按 input 缩放 (对齐本地 legacy_cc 宽松风格 + nv_gw R1416
            # first-byte 缩放). 旧: 固定 PRIMARY_HEADER_TIMEOUT=25s 对大 context 请求首字节太短
            # (384K 请求 NVCF prefill 慢, nv_gw 等 NVCF 首字节, cc4101 25s 先超时 -> 连续5次
            # header/ttfb timeout -> breaker OPEN 503 死循环, 2026-07-15 00:26-00:28 实锤).
            # 大请求给到 120s (对齐 nv_gw R1416 first-byte 上限, 让 nv_gw 有机会等 NVCF 首字节);
            # 小请求仍 25s (死连接快断, R828 原意). 上限 min(120, UPSTREAM_TIMEOUT=60)... 但 60s 仍
            # 对大请求太短, 故用 120 (超过 UPSTREAM_TIMEOUT body 超时, body 阶段另由 stream
            # stall-watcher 兜底, header 阶段不受 body timeout 限制 — http.client timeout 是
            # connect+read 共用, 但 getresponse 只等 header, body 在流式 read 另设 poll).
            _hdr_ic = len(json.dumps(oai_body, ensure_ascii=False)) if oai_body else 0
            # R2154: 精化 R1420 分档表 4->6 档. 旧 50-200K 一档全给 75s 太粗, 实测 60-150K
            # 段 p99 ttfb 141-246s 全被 75s 误杀滑 ms (6h 窗口 82 个慢成功���砍). 新表据实测 p99
            # + nv_gw first-byte deadline 倒挂规避 (cc4101 header_timeout 必须 > nv_gw 端
            # first_byte deadline, 让 nv_gw 用满自己的检测主动 break 发 err_chunk=干净
            # Scenario A 让 CC 重试, cc4101 不抢先断切 ms):
            #   nv_gw first-byte: <50K=20s, 50-200K=60s, 200-350K=45s, >350K=60s
            #   实测 p99 ttfb:  30-60K~40s, 60-90K=141s, 90-120K=142s, 120-150K=246s
            # cc4101 给: <30K=25s(死连快断), 30-50K=40s, 50-90K=150s, 90-150K=160s,
            #   150-350K=180s(R2202: 120->180, NVCF 120-142s 慢请求被 120s 砍致 499), >350K=120s(同).
            # R2202: 499 真根因深查发现 150-189K chars 命中本档(120s), NVCF ttfb 120-142s
            #   精确踩 120s 线 -> cc4101 primary 120s timeout -> fallback 期间 cc2 已断 ->
            #   client_gone_mid_stream(499). 7/14 改前 499 primary_elapsed_ms≈120100 全命中本档.
            #   调 180s 让 NVCF 120-142s 慢请求等到首字节不触发 timeout. 倒挂安全: 180s >
            #   nv_gw 200-350K first-byte 45s / 150-200K first-byte 60s.
            if _hdr_ic > 350000:
                _hdr_to = 120
            elif _hdr_ic > 200000:
                _hdr_to = 180  # R2197: 200-350K 档 120->180s (延续 R2202). R2202 只改 150-200K 档(120->180), 漏改本档. 6h 41 个 499 (139-223K chars) 仍有 ~4 个命中 206-223K 踩本档 120s 线致 client_gone_mid_stream. PRIMARY-FAIL elapsed 实测 10x 踩 120s 线. 同 R2202 根因 (NVCF ttfb 120-142s 慢请求被 120s 砍). 180s 覆盖. 倒挂安全: 180s > nv_gw 200-350K first-byte 45s (同 R2202 论证).
            elif _hdr_ic > 150000:
                _hdr_to = 180  # R2202: 150-200K 档 120->180s. NVCF 120-142s ttfb 踩 120s 线致 499, 180s 覆盖. 倒挂安全(>nv_gw 60s).
            elif _hdr_ic > 90000:
                _hdr_to = 160  # R2154: 90-150K 档. nv_gw first-byte 60s 先 break 发 err_chunk,
                                # cc4101 160s 兜底真 NVCF 慢 (实测 p99 142s, 120-150K p99 246s
                                # 但 nv_gw 60s first-byte 会先处理, 160s 足兜底). 旧 75s 误杀.
            elif _hdr_ic > 50000:
                _hdr_to = 150  # R2154: 50-90K 档. nv_gw first-byte 60s + 90s 余量. 实测 p99 141s,
                                # 旧 75s (R1772) 砍掉 60-90K 慢成功. 150s 覆盖 p99 + 留余量.
            elif _hdr_ic > 30000:
                _hdr_to = 40   # R2154: 30-50K 新拆档. nv_gw first-byte 20s + 20s 余量. 小请求
                                # 快断仍由 25s 兜底, 这档给 40s 覆盖中等请求偶发慢.
            else:
                _hdr_to = PRIMARY_HEADER_TIMEOUT  # 默认 25s, 小请求快断
            # R1705: 深拷贝 anth_body 改写 model 做路由 (claude-*→glm5_2_nv), 透传其余.
            import copy as _copy
            _pri_body = _copy.copy(oai_body)
            _pri_body["model"] = PRIMARY_UPSTREAM_MODEL
            # R2254obs: 观测点 — 打印 _hdr_ic 实际值 + 落档 + 最终 header_timeout,
            # 用于确认 60s 误杀(7/22 21:43 e60791ac req msgs=2 tools=27 触发 60s)是 _hdr_ic 落 <30K 档
            # 还是分档表未生效. 抓 1-2 窗口后删.
            _nm = len(oai_body.get("messages", [])) if isinstance(oai_body, dict) else 0
            _nt = len(oai_body.get("tools", [])) if isinstance(oai_body, dict) else 0
            _log("R2254-OBS", f"primary req={request_id} _hdr_ic={_hdr_ic} hdr_to={_hdr_to} msgs={_nm} tools={_nt}")
            resp, conn = _call_upstream(
                _pri_body, PRIMARY_UPSTREAM_URL, PRIMARY_UPSTREAM_MODEL,
                PRIMARY_UPSTREAM_TOKEN, request_id,
                header_timeout=_hdr_to,
                caller_tag="cc4101-primary",
            )
        except _UpstreamError as e:
            ms = int((time.monotonic() - t0) * 1000)
            attempts.append({"stage": stage_label, "kind": e.kind, "status": e.status, "elapsed_ms": ms, "message": e.message})
            metrics["primary_error_type"] = e.kind
            metrics["primary_elapsed_ms"] = ms
            _log("PRIMARY-FAIL", f"primary ({PRIMARY_UPSTREAM_MODEL}) {e.kind} status={e.status} after {ms}ms ({stage_label}): {e.message[:160]}")
            if e.kind == "client_4xx":
                result.error_kind = e.kind
                result.error_status = e.status
                result.error_json = e.error_json
                result.error_message = e.message
                result.elapsed_ms = ms
                metrics["upstream_used"] = "primary"
                metrics["mapped_model"] = PRIMARY_UPSTREAM_MODEL
                metrics["key_cycle_details"] = attempts
                return "client_4xx"
            # R1602: 区分"cc4101 自抢超时"vs"nv_gw 真坏". 旧: 所有 retryable 都
            # record_primary_failure -> cc4101 header 超时 (60-130s 抢在 nv_gw 120s chain
            # 跑完前) 也计数 -> 累计5次 OPEN breaker -> 503 死循环 (2026-07-16 01:35 实锤).
            # 新: 仅当 (a) nv_gw 明确返回 5xx (server_5xx), 或 (b) timeout 但耗时已 >
            # CHAIN_BUDGET_S (说明 nv_gw 跑完 chain 仍没好, 真坏), 或 (c) conn/unexpected
            # 才计数. header 超时且耗时 < CHAIN_BUDGET_S 大概率是 cc4101 抢断, 不计数,
            # CC 自然重试, breaker 不误开.
            _CHAIN_BUDGET_S = 120  # 对齐 nv_gw NVU_TIER_BUDGET_GLM5_2_NV
            _should_record = (
                e.kind == "server_5xx"
                or (e.kind == "timeout" and ms > _CHAIN_BUDGET_S * 1000)
                or e.kind not in ("timeout", "server_5xx")
            )
            if _should_record:
                record_primary_failure()  # R824d: retryable fail -> may open circuit
            else:
                _log("PRIMARY-FAIL-SKIP-CIRCUIT", f"primary {e.kind} after {ms}ms < chain budget {_CHAIN_BUDGET_S}s, likely cc4101 pre-empted nv_gw retry, NOT counted toward circuit (req={request_id})")
            return False  # retryable: server_5xx / conn / timeout
        except Exception as e:
            ms = int((time.monotonic() - t0) * 1000)
            _log("PRIMARY-ERR", f"primary unexpected {type(e).__name__} ({stage_label}): {e}")
            _log_error_detail({
                "request_id": request_id, "stage": stage_label,
                "error": f"{type(e).__name__}: {e}", "elapsed_ms": ms,
            })
            attempts.append({"stage": stage_label, "kind": "unexpected", "elapsed_ms": ms, "message": str(e)})
            metrics["primary_error_type"] = "unexpected"
            metrics["primary_elapsed_ms"] = ms
            record_primary_failure()  # R824d: unexpected retryable
            return False
        # success
        result.success = True
        result.resp = resp
        result.conn = conn
        result.upstream_used = "primary"
        result.mapped_model = PRIMARY_UPSTREAM_MODEL
        result.elapsed_ms = int((time.monotonic() - t0) * 1000)
        metrics["upstream_used"] = "primary"
        metrics["mapped_model"] = PRIMARY_UPSTREAM_MODEL
        metrics["key_cycle_details"] = attempts
        # R849: 移除 connect 成功即 record_primary_success. 旧洞: GLM5.2 劣化表现为
        # "connect 200 + 流到一半静默", connect 成功就重置 fail_count=0 -> R848 流式
        # failure 永远累积不到阈值 5, circuit 永远不开. 现改在 stream.py 真正流式成功
        # 完成(收到 finish_reason 非 zombie 非 interrupted)时才 record_primary_success.
        return True

    def _try_fallback(stage_label):
        """R1643: One fallback (ms_gw glm5_2_ms) attempt. 成败都不计 breaker.
        Returns True on success, False on failure(result 已填好 error_*)."""
        if not FALLBACK_UPSTREAM_URL:
            return False  # fallback disabled (R854 行为)
        t0 = time.monotonic()
        try:
            # fallback header 缩放: ms_gw 不需等 nv 的 chain budget, 用稍宽松分档.
            # R1643: oai_body["model"] 是 primary 的 glm5_2_nv, ms_gw 会 404 "model not found".
            # 深拷贝一份换 model 字段为 fallback model. 不改原 oai_body(避免污染后续重试).
            import copy as _copy
            _fb_body = _copy.copy(oai_body)
            _fb_body["model"] = FALLBACK_UPSTREAM_MODEL
            _hdr_ic = len(json.dumps(_fb_body, ensure_ascii=False)) if _fb_body else 0
            # R2154: fallback 分档对齐 primary 6 档 (ms_gw chain budget 同 120s). ms_gw 不走 nv
            # first-byte 倒挂问题, 但分档粗同样砍慢请求. 50-150K 给 120s (ms 比 nv 慢, 多留余量).
            if _hdr_ic > 350000:
                _hdr_to = 120
            elif _hdr_ic > 200000:
                _hdr_to = 120
            elif _hdr_ic > 150000:
                _hdr_to = 120
            elif _hdr_ic > 90000:
                _hdr_to = 120
            elif _hdr_ic > 50000:
                _hdr_to = 120
            elif _hdr_ic > 30000:
                _hdr_to = 60
            else:
                _hdr_to = PRIMARY_HEADER_TIMEOUT  # 25s
            resp, conn = _call_upstream(
                _fb_body, FALLBACK_UPSTREAM_URL, FALLBACK_UPSTREAM_MODEL,
                FALLBACK_UPSTREAM_TOKEN, request_id,
                header_timeout=_hdr_to,
                caller_tag="cc4101-fallback",
            )
        except _UpstreamError as e:
            ms = int((time.monotonic() - t0) * 1000)
            attempts.append({"stage": stage_label, "kind": e.kind, "status": e.status, "elapsed_ms": ms, "message": e.message})
            _log("FALLBACK-FAIL", f"fallback ({FALLBACK_UPSTREAM_MODEL}) {e.kind} status={e.status} after {ms}ms: {e.message[:160]}")
            result.error_kind = e.kind
            result.error_status = e.status
            result.error_json = e.error_json
            result.error_message = e.message
            result.elapsed_ms = ms
            metrics["upstream_used"] = "fallback"
            metrics["mapped_model"] = FALLBACK_UPSTREAM_MODEL
            metrics["key_cycle_details"] = attempts
            return False
        except Exception as e:
            ms = int((time.monotonic() - t0) * 1000)
            _log("FALLBACK-ERR", f"fallback unexpected {type(e).__name__}: {e}")
            _log_error_detail({"request_id": request_id, "stage": stage_label,
                "error": f"{type(e).__name__}: {e}", "elapsed_ms": ms})
            attempts.append({"stage": stage_label, "kind": "unexpected", "elapsed_ms": ms, "message": str(e)})
            result.error_kind = "unexpected"
            result.error_message = str(e)
            result.elapsed_ms = ms
            metrics["upstream_used"] = "fallback"
            metrics["mapped_model"] = FALLBACK_UPSTREAM_MODEL
            metrics["key_cycle_details"] = attempts
            return False
        # fallback success
        result.success = True
        result.resp = resp
        result.conn = conn
        result.upstream_used = "fallback"
        result.mapped_model = FALLBACK_UPSTREAM_MODEL
        result.elapsed_ms = int((time.monotonic() - t0) * 1000)
        metrics["upstream_used"] = "fallback"
        metrics["mapped_model"] = FALLBACK_UPSTREAM_MODEL
        metrics["fallback_triggered"] = True
        metrics["key_cycle_details"] = attempts
        _log("FALLBACK-OK", f"fallback ({FALLBACK_UPSTREAM_MODEL}) succeeded after {result.elapsed_ms}ms (req={request_id})")
        return True

    # -- Stage -1 (R1712-force-fb): 客户端指定 FORCE_FALLBACK_MODEL -> 跳过 primary 直走 ms_gw.
    # 用途: loop 自优化子会话绕开 nv_gw 间歇劣化窗口. 不经断路器(fallback 本就不计 breaker).
    # 见 config.py FORCE_FALLBACK_MODEL 注释.
    if FORCE_FALLBACK_MODEL and oai_body.get("model") == FORCE_FALLBACK_MODEL:
        _log("FORCE-FALLBACK", f"client model={FORCE_FALLBACK_MODEL} -> skip primary, go straight to ms_gw (req={request_id})")
        metrics["force_fallback"] = True
        if _try_fallback("fallback(forced)"):
            return result
        _log("FALLBACK-FAIL", f"forced fallback also failed ({result.error_kind}) -> returning error, CC will retry (req={request_id})")
        return result

    # -- Stage 0: circuit OPEN? R1643 改为直走 fallback(不再 fast-fail 503) --
    # 旧 R854: OPEN 直接 503 让 CC 重试. 新: 既然有 fallback, OPEN 时跳过 primary 直接
    # 走 ms, 省掉每条等 nv 超时 60-120s, 且不丢请求. 冷却后 HALF_OPEN probe nv.
    if is_primary_open():
        _log("PRIMARY-BREAKER-OPEN", f"primary circuit OPEN -> go straight to fallback ms_gw glm5_2_ms (req={request_id})")
        metrics["primary_breaker_skipped"] = True
        if _try_fallback("fallback(circuit-open)"):
            return result
        # fallback 也失败 -> 返回 fallback 的 error
        return result

    # -- Stage 1: primary nv_gw glm5_2_nv --
    r = _try_primary("primary")
    if r is True:
        return result
    if r == "client_4xx":
        return result  # client error, do not fallback

    # -- Stage 2 (R1643): primary retryable 失败 -> 立即试 fallback 一次 --
    # primary 已计 breaker(若该计). fallback 不计 breaker. fallback 成 -> return;
    # fallback 败 -> 用 fallback 的 error 返回(覆盖 primary 的, 因 fallback 是最后尝试).
    _log("PRIMARY-FAIL", f"primary failed ({result.error_kind or 'unknown'}) -> trying fallback ms_gw glm5_2_ms (req={request_id})")
    if _try_fallback("fallback"):
        return result
    # fallback 也失败
    _log("FALLBACK-FAIL", f"fallback also failed ({result.error_kind}) -> returning error, CC will retry (req={request_id})")
    return result
