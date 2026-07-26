#!/usr/bin/env python3
"""R1712: cc4101 纯透传层 (转换已下沉 nv_gw/ms_gw /v1/messages 端点).

R1705/R1711 透传化后, cc4101 不再做 anth→oai→anth 双转换, 只透传 nv_gw 已发的
anthropic SSE/JSON 给 CC. 格式转换、zombie/content_filter 诊断全在 nv_gw 端 (R1704).

两个透传函数:
  1. passthrough_stream — 流: 透传 nv_gw anthropic SSE, breaker 信号纯连接级.
  2. passthrough_nonstream — 非流: 透传 nv_gw 已合成的 anthropic JSON.

旧 stream_to_anth/collect_stream_to_anth (oai→anth 转换) 已删, format 包已不再依赖.
"""
import json
import uuid
import time
import datetime
import http.client
import socket

from .config import THINKING_SIGNATURE_DEFAULT, UPSTREAM_TIMEOUT, UPSTREAM_IDLE_TIMEOUT, \
    CC4101_STREAM_TOTAL_DEADLINE_S, CC4101_STREAM_IDLE_GAP_S, CC4101_STREAM_POLL_S
from .logger import _log, _log_metrics, _log_error_detail
from .circuit import record_primary_failure, record_primary_success
# cc4101 的读循环/stall-watcher/recv-fallback/breaker 留在本文件不动 — 只换"转换体".


def passthrough_stream(handler, resp, conn, metrics, t_start):
    """R1705: 纯透传 nv_gw /v1/messages 已发的 anthropic SSE 到 CC.

    不做 oai→anth 转换 (nv_gw 端点已发 anthropic SSE), 不判 zombie/content_filter
    (nv_gw 端点已判并发 api_error SSE, cc4101 透传). breaker 信号纯连接级:
      - 正常读到结束 (resp.read 返空或 [DONE]) → record_primary_success
      - 连接级异常 (RemoteDisconnected/Reset/OSError, 非客户端断开) → record_primary_failure
      - 客户端断开 (BrokenPipe) 不计 breaker (非上游错)
    保留最小 stall-watcher (总时长兜底 CC4101_STREAM_TOTAL_DEADLINE_S, 防纯挂死).
    """
    try:
        handler.send_response(200)
        handler.send_header("Content-Type", "text/event-stream")
        handler.send_header("Cache-Control", "no-cache")
        handler.send_header("Connection", "close")
        handler.close_connection = True
        handler.end_headers()
    except (BrokenPipeError, ConnectionResetError, OSError) as e:
        _log("ERR", f"client gone before SSE headers after {int((time.time()-t_start)*1000)}ms: {e}")
        metrics["error_type"] = "client_gone_pre_stream"
        metrics["status"] = 499
        metrics["duration_ms"] = int((time.time() - t_start) * 1000)
        _log_metrics(metrics)
        # R2253 t1: 499 完整 trace (BUG1 抓证) — pre-headers 阶段断.
        _dur = metrics.get("duration_ms") or 0
        _log_error_detail({
            "trace": "CC4101-499-PRE-HEADERS",
            "request_id": metrics.get("request_id"),
            "ts": datetime.datetime.now().isoformat(),
            "host_machine": metrics.get("host_machine"),
            "stage": "pre_headers",
            "is_stream": metrics.get("is_stream"),
            "upstream_used": metrics.get("upstream_used"),
            "fallback_triggered": metrics.get("fallback_triggered"),
            "request_model": metrics.get("request_model"),
            "total_input_chars": metrics.get("total_input_chars"),
            "ttfb_ms": 0,
            "duration_ms": _dur,
            "post_ttfb_ms": 0,
            "bytes_sent": 0,
            "exc_type": type(e).__name__,
            "exc_msg": str(e)[:200],
            "upstream_error_seen": None,
        })
        try:
            conn.close()
        except Exception:
            pass
        return

    stream_total_deadline = None
    ttfb_recorded = False

    _bytes_written = 0
    _disc_exc = None
    def _write_bytes(b):
        nonlocal _bytes_written, _disc_exc
        if not b:
            return True
        try:
            handler.wfile.write(b)
            handler.wfile.flush()
            _bytes_written += len(b)
            return True
        except (BrokenPipeError, ConnectionResetError, OSError) as e:
            _disc_exc = e
            _log("ERR", f"client gone mid-stream after {int((time.time()-t_start)*1000)}ms: {e}")
            return False

    upstream_used = metrics.get("upstream_used", "primary")
    is_primary = (upstream_used == "primary")
    # R1719: lightweight detect nv_gw api_error SSE (mid-stream soft-fail signal). nv_gw anth path
    # on zombie/no_content_gap/total_deadline emits `event: error` SSE then clean-close. Without this,
    # the clean EOF below is treated as record_primary_success -> cc4101 circuit always CLOSED ->
    # death loop. We grep the byte sequence b"event: error" across chunks (NOT full SSE JSON parse,
    # minimal R1711 passthrough violation) -> mark _upstream_error_seen -> record_primary_failure
    # instead of success at clean EOF. Current req still interrupts (api_error passed through to CC);
    # this only makes the circuit accumulate so SUBSEQUENT reqs switch to ms_gw.
    _err_probe = b""
    _upstream_error_seen = False
    try:
        while True:
            # 最小 stall-watcher: ttfb 后总时长兜底 (防纯挂死, 不做 idle gap — nv_gw 端点自有 deadline)
            if ttfb_recorded and stream_total_deadline and time.time() > stream_total_deadline:
                metrics["error_type"] = "stream_total_deadline"
                _log("STREAM-DEADLINE", f"passthrough total deadline "
                    f"{CC4101_STREAM_TOTAL_DEADLINE_S}s after ttfb exceeded")
                raise socket.timeout("stream_total_deadline")
            try:
                chunk = resp.read(8192)
            except socket.timeout:
                continue
            except OSError as _re:
                # recv-fallback (镜像 R1704 nv_gw / cc4101 旧 L241-272): http.client timed-out-object
                # 后用 sock.recv 取 buffer 已到达数据 (nv_gw 发的 [DONE]/api_error 等).
                if "timed out object" in str(_re) or "timeout" in str(_re).lower():
                    try:
                        _sc = resp.fp.raw._sock
                        _peek = _sc.recv(8192, socket.MSG_PEEK)
                    except Exception:
                        _peek = b''
                    if _peek:
                        try:
                            chunk = _sc.recv(8192)
                        except Exception:
                            chunk = b''
                        if chunk:
                            _log("DBG", f"passthrough recv-fallback got {len(chunk)}b")
                        else:
                            continue
                    else:
                        continue
                else:
                    raise
            if not chunk:
                # 干净 EOF — 流正常结束. (nv_gw /v1/messages 已发 message_stop + [DONE])
                break
            if not ttfb_recorded:
                metrics["ttfb_ms"] = int((time.time() - t_start) * 1000)
                ttfb_recorded = True
                stream_total_deadline = time.time() + CC4101_STREAM_TOTAL_DEADLINE_S
            # R1719: probe for nv_gw api_error SSE (cross-chunk safe).
            if not _upstream_error_seen:
                _probe = _err_probe + chunk
                if b"event: error" in _probe:
                    _upstream_error_seen = True
                _err_probe = _probe[-32:]
            if not _write_bytes(chunk):
                # 客户端断开 — 不计 breaker (非上游错)
                metrics["error_type"] = "client_gone_mid_stream"
                metrics["status"] = 499
                metrics["duration_ms"] = int((time.time() - t_start) * 1000)
                _log_metrics(metrics)
                # R2253 t1: 499 完整 trace (BUG1 抓证). 不动 metrics 流, 只写 JSONL.
                _ttfb = metrics.get("ttfb_ms") or 0
                _dur = metrics.get("duration_ms") or 0
                _log_error_detail({
                    "trace": "CC4101-499-MIDSTREAM",
                    "request_id": metrics.get("request_id"),
                    "ts": datetime.datetime.now().isoformat(),
                    "host_machine": metrics.get("host_machine"),
                    "stage": "streaming_post_ttfb",
                    "is_stream": metrics.get("is_stream"),
                    "upstream_used": metrics.get("upstream_used"),
                    "fallback_triggered": metrics.get("fallback_triggered"),
                    "request_model": metrics.get("request_model"),
                    "total_input_chars": metrics.get("total_input_chars"),
                    "ttfb_ms": _ttfb,
                    "duration_ms": _dur,
                    "post_ttfb_ms": max(0, _dur - _ttfb),
                    "bytes_sent": _bytes_written,
                    "exc_type": type(_disc_exc).__name__ if _disc_exc else None,
                    "exc_msg": str(_disc_exc)[:200] if _disc_exc else None,
                    "upstream_error_seen": _upstream_error_seen,
                })
                try:
                    conn.close()
                except Exception:
                    pass
                return
        # 正常结束
        if not metrics.get("error_type"):
            metrics["status"] = 200
        metrics["duration_ms"] = int((time.time() - t_start) * 1000)
        # R1719: if nv_gw emitted `event: error` SSE mid-stream, treat clean EOF as upstream
        # soft-fail (not success) so the circuit accumulates -> OPEN -> subsequent reqs go ms_gw.
        if is_primary and not metrics.get("error_type") and _upstream_error_seen:
            record_primary_failure()
            _log("CC4101-UPSTREAM-ERROR-SEEN", f"passthrough detected nv_gw api_error SSE "
                f"-> breaker failure (req_id={metrics.get('request_id','?')}, "
                f"ttfb={metrics.get('ttfb_ms')}ms)")
        elif is_primary and not metrics.get("error_type"):
            record_primary_success()
        _log_metrics(metrics)
    except socket.timeout as e:
        # stall-watcher 命中 = 上游静默挂死, 计 breaker (primary)
        elapsed_ms = int((time.time() - t_start) * 1000)
        _log("STREAM-STALLED", f"passthrough stall after {elapsed_ms}ms: {e}")
        if not metrics.get("error_type"):
            metrics["error_type"] = "stream_total_deadline"
        metrics["status"] = 502
        metrics["duration_ms"] = elapsed_ms
        if is_primary:
            record_primary_failure()
            _log("CC4101-STREAM-STALL-FAIL", f"stall recorded as primary failure "
                f"(req_id={metrics.get('request_id','?')}, elapsed={elapsed_ms}ms) "
                f"[R1771 time-window now accumulates instead of being reset by success]")
        _log_metrics(metrics)
    except (http.client.RemoteDisconnected, ConnectionResetError, OSError) as e:
        # 连接级异常 (上游断连) — 计 breaker (primary), emit 502
        elapsed_ms = int((time.time() - t_start) * 1000)
        error_class = type(e).__name__
        _log("ERR", f"passthrough {error_class} after {elapsed_ms}ms: {e}")
        if not metrics.get("error_type"):
            metrics["error_type"] = f"stream_{error_class}"
        metrics["status"] = 502
        metrics["duration_ms"] = elapsed_ms
        if is_primary:
            record_primary_failure()
        _log_metrics(metrics)
    except Exception as e:
        _log("ERR", f"passthrough unexpected: {type(e).__name__}: {e}")
        if not metrics.get("error_type"):
            metrics["error_type"] = "stream_unexpected"
        metrics["status"] = 502
        metrics["duration_ms"] = int((time.time() - t_start) * 1000)
        if is_primary:
            record_primary_failure()
        _log_metrics(metrics)
    finally:
        try:
            conn.close()
        except Exception:
            pass


def passthrough_nonstream(handler, resp, conn, metrics, t_start):
    """R1705: 透传 nv_gw /v1/messages stream=false 已合成的 anthropic JSON 给 CC.

    nv_gw 端点内部已 collect upstream stream + 合成 anthropic 非流式 JSON,
    cc4101 读完整响应体透传. breaker 信号连接级 (同 passthrough_stream).
    """
    upstream_used = metrics.get("upstream_used", "primary")
    is_primary = (upstream_used == "primary")
    try:
        body = resp.read()
    except (http.client.RemoteDisconnected, ConnectionResetError, OSError) as e:
        elapsed_ms = int((time.time() - t_start) * 1000)
        error_class = type(e).__name__
        _log("ERR", f"passthrough nonstream {error_class} after {elapsed_ms}ms: {e}")
        metrics["error_type"] = f"nonstream_{error_class}"
        metrics["status"] = 502
        metrics["duration_ms"] = elapsed_ms
        if is_primary:
            record_primary_failure()
        _log_metrics(metrics)
        try:
            conn.close()
        except Exception:
            pass
        return
    try:
        conn.close()
    except Exception:
        pass
    status = resp.status
    # 透传响应体 (anthropic JSON). 4xx/5xx 也透传 (nv_gw 已返 anthropic error 格式).
    if not metrics.get("error_type") and status >= 400:
        metrics["error_type"] = f"upstream_{status}"
    metrics["status"] = status
    metrics["duration_ms"] = int((time.time() - t_start) * 1000)
    if is_primary and status < 400:
        record_primary_success()
    elif is_primary and status >= 500:
        record_primary_failure()
    _log_metrics(metrics)
    # 透传
    body_bytes = body if isinstance(body, bytes) else body.encode("utf-8")
    handler._send_raw(status, body_bytes, "application/json")
