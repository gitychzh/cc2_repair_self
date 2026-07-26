#!/usr/bin/env python3
"""Streaming SSE conversion and non-stream collect+synthesize for cc4101.

R684: Adapted from legacy-cc/gateway/stream.py. Two modes:
  1. stream_to_anth — real-time SSE: OpenAI streaming chunk → Anthropic SSE event.
     Handles reasoning_content → thinking block, content → text block,
     tool_calls → tool_use block. Used when CC requests stream=true.
  2. collect_stream_to_anth — collect streaming chunks → synthesize non-stream
     Anthropic response. Used when CC requests stream=false (but upstream is
     still stream — glm5.2 non-stream is broken on both backends).

Simplified vs legacy-cc: no prefill_buffer / NV peek (cc4101's upstreams are
nv_gw/ms_gw, not raw NVCF; they handle their own empty-stream detection).
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


def stream_to_anth(handler, resp, request_model, target_model, conn, metrics, t_start):
    """Real-time SSE conversion: OpenAI streaming chunks → Anthropic SSE events."""
    # R845 B5: send_response 阶段在主 try 之外, CC 早断会 BrokenPipe 冒泡致上游 conn 泄漏 + metrics 漏记.
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
        try:
            conn.close()
        except Exception:
            pass
        return

    message_start_sent = False
    message_delta_sent = False
    ttfb_recorded = False
    buffer = ""
    next_block_idx = 0
    active_block_type = None  # "thinking" | "text" | "tool_use"
    streaming_input_tokens = 0
    streaming_output_tokens = 0
    pending_stop_reason = None
    # R844 F5: 自身空僵尸检测累积量. cc4101 一旦开始 stream_to_anth 就无法切 fallback
    # (SSE 头已发), 唯一出路是检测空僵尸后 emit api_error 让 Claude Code 重试整个请求
    # (下次大概率命中 fallback ms_gw 或 nv_gw 不同 mode/IP). 不依赖 nv_gw 的 content_filter
    # 信号 — cc4101 自己也要能抓 "大 input + 少 content + 无真 tool_call" 的空壳.
    stream_content_chars = 0
    stream_reasoning_chars = 0
    stream_saw_real_tool_call = False  # tool_calls 带 id 且 arguments 非空才算真工具调用
    stream_zombie = False  # 命中空僵尸 → 走 api_error 路径, 不发 end_turn

    # R848: 流式中途失败也触发 circuit breaker. 旧洞: record_primary_failure 只在 upstream.py
    # connect/header 阶段失败时调, 流到一半挂掉(stall-watcher/zombie/content_filter/idle-deadline)
    # 全在 stream.py 里, 从不记 circuit -> NVCF 劣化表现为"connect 成功+流到一半静默"时 circuit
    # 永远 CLOSED -> CC 每次重试都打 primary -> 每次流式中断 -> 死循环卡死. 现在所有流式失败点
    # (仅当 upstream_used==primary) 调 record_primary_failure, 连续 N 次后 circuit OPEN 直走 fallback.
    def _record_primary_stream_fail(reason):
        if metrics.get("upstream_used") == "primary":
            record_primary_failure()
            _log("CIRCUIT-STREAM-FAIL", f"({request_model}) primary stream mid-flight failure: {reason} "
                f"- recorded to circuit breaker (req={metrics.get('request_id','?')})")

    # R845 B7: stream stall-watcher 双门槛状态.
    stream_total_deadline = None  # ttfb 后设 = ttfb + CC4101_STREAM_TOTAL_DEADLINE_S
    last_progress_time = None  # 最近一次收到真内容(content/reasoning/tool_call)的时刻; idle间隙超限即stall

    def _emit_message_start(msg_id=None, input_tokens_est=0):
        nonlocal message_start_sent
        handler._send_sse("message_start", {
            "type": "message_start",
            "message": {
                "id": msg_id or f"msg_{uuid.uuid4().hex[:24]}",
                "type": "message", "role": "assistant",
                "model": request_model, "content": [],
                "stop_reason": None, "stop_sequence": None,
                "usage": {"input_tokens": input_tokens_est, "output_tokens": 0,
                          "cache_creation_input_tokens": 0,
                          "cache_read_input_tokens": 0},
            },
        })
        message_start_sent = True

    def _emit_graceful_end(stop_reason="end_turn", output_tokens=0, input_tokens_real=0, interrupted=False, zombie=False):
        nonlocal message_start_sent, message_delta_sent, active_block_type, pending_stop_reason
        # R846: 放宽守卫. 旧: 仅 next_block_idx==0 (从未开 block) 判 empty. 但 drip 场景上游先吐
        # 首 reasoning_content 开了 thinking block (next_block_idx>0) 再静默断流 → 旧守卫失效.
        # R852: 判定改只看 stream_content_chars (text answer), 不加 reasoning_chars. GLM5.2 thinking
        # 模式实测会产出 3182c reasoning 但 0c content — 模型把答案写进思考里没给正式回答, CC 收到
        # "只有 thinking 没 text" 的 message 报 empty/filtered completion. 故 thinking 不算有效完成.
        if (next_block_idx == 0
                or (stream_content_chars < 50
                    and not stream_saw_real_tool_call
                    and metrics.get("total_input_chars", 0) >= 5000)):
            _log("WARN", f"empty_stream_response: stream ended with no content "
                         f"(model={metrics.get('mapped_model','?')} output_tokens={streaming_output_tokens})")
            _log_error_detail({
                "request_id": metrics.get("request_id", "?"),
                "timestamp": datetime.datetime.now().isoformat(),
                "error_subcategory": "empty_stream_response",
                "upstream_status": 200,
                "mapped_model": metrics.get("mapped_model", "?"),
                "upstream_used": metrics.get("upstream_used", "?"),
                "streaming_output_tokens": streaming_output_tokens,
                "finish_reason": pending_stop_reason,
            })
            metrics["empty_stream_response"] = True
        if active_block_type is not None:
            handler._send_sse("content_block_stop",
                           {"type": "content_block_stop", "index": next_block_idx - 1})
            active_block_type = None
        if not message_start_sent:
            _emit_message_start(input_tokens_est=metrics.get("estimated_input_tokens", 0))
        # R844 F4/F5: zombie 空响应 (content_filter from nv_gw, 或自身检测的空壳) → emit api_error
        # 让 Claude Code 重试整个请求 (下次命中 fallback 或不同 mode/IP). 不发 end_turn — 否则 CC
        # 认为正常完成不重试. 与 interrupted 路径同形但 zombie 不要求 pending_stop_reason is None.
        if zombie:
            _log("ERR", f"zombie empty stream — emitting api_error SSE so CC retries "
                        f"(req={metrics.get('request_id','?')} model={metrics.get('mapped_model','?')})")
            handler._send_sse("error", {
                "type": "error",
                "error": {"type": "api_error",
                          "message": "upstream returned empty/filtered completion, please retry"},
            })
            handler._send_sse("message_stop", {"type": "message_stop"})
            metrics["status"] = 502
            if not metrics.get("error_type"):
                metrics["error_type"] = "zombie_empty_completion"
            metrics["duration_ms"] = int((time.time() - t_start) * 1000)
            _log_metrics(metrics)
            try:
                conn.close()
            except Exception:
                pass
            return
        # R690 cc2 red-team: if the stream was interrupted mid-flight (socket error / timeout)
        # AND we never saw a real finish_reason, do NOT fake stop_reason=end_turn — CC would
        # treat the truncated response as a complete one and not retry. Instead emit an
        # Anthropic error SSE (api_error) so CC retries the whole request.
        if interrupted and pending_stop_reason is None:
            _log("ERR", f"stream interrupted without finish_reason — emitting api_error SSE so CC retries "
                        f"(req={metrics.get('request_id','?')})")
            handler._send_sse("error", {
                "type": "error",
                "error": {"type": "api_error",
                          "message": "upstream stream interrupted before completion"},
            })
            handler._send_sse("message_stop", {"type": "message_stop"})
            metrics["status"] = 502
            if not metrics.get("error_type"):
                metrics["error_type"] = "StreamInterrupted"
            metrics["duration_ms"] = int((time.time() - t_start) * 1000)
            _log_metrics(metrics)
            try:
                conn.close()
            except Exception:
                pass
            return
        if not message_delta_sent:
            real_output = streaming_output_tokens or output_tokens or metrics.get("output_tokens", 0)
            real_input = streaming_input_tokens or input_tokens_real or metrics.get("input_tokens", 0)
            metrics["output_tokens"] = real_output
            metrics["input_tokens"] = real_input
            final_stop = pending_stop_reason or stop_reason
            usage_delta = {"output_tokens": real_output}
            if real_input > 0:
                usage_delta["input_tokens"] = real_input
            handler._send_sse("message_delta", {
                "type": "message_delta",
                "delta": {"stop_reason": final_stop, "stop_sequence": None},
                "usage": usage_delta,
            })
            message_delta_sent = True
        # R849: 真正流式成功完成(非 zombie/非 interrupted/有 finish_reason) 才
        # record_primary_success 重置 circuit. 修复 R848 盲区: connect 成功不再
        # 重置(已从 upstream.py 移除), 避免劣化期 connect 成功+流式中断死循环
        # (每次 connect 都 reset 导致 failure 永远累积不到 5).
        if metrics.get("upstream_used") == "primary" and not interrupted and not zombie:
            record_primary_success()
        handler._send_sse("message_stop", {"type": "message_stop"})
        if metrics.get("error_type") and metrics["error_type"] not in (None, "empty_stream_response"):
            metrics["status"] = 502
        elif metrics.get("empty_stream_response"):
            metrics["status"] = 502
            metrics["error_type"] = "empty_stream_response"
        else:
            metrics["status"] = 200
        metrics["duration_ms"] = int((time.time() - t_start) * 1000)
        _log_metrics(metrics)
        try:
            conn.close()
        except Exception:
            pass

    try:
        while True:
            # R845 B7: stall-watcher 双门槛检查点 (chunk 之间). per-read 用短轮询
            # CC4101_STREAM_POLL_S, read 阻塞最多 POLL_S 就抛 socket.timeout 进 except,
            # 非致命时 except 内 continue 回到这里再检查 — 让双门槛在纯静默期也能生效.
            if ttfb_recorded and stream_total_deadline and time.time() > stream_total_deadline:
                metrics["error_type"] = "stream_total_deadline"
                _log("STREAM-DEADLINE", f"({request_model}) stream total deadline "
                    f"{CC4101_STREAM_TOTAL_DEADLINE_S}s after ttfb exceeded (stall-watcher)")
                raise socket.timeout("stream_total_deadline")
            # R850: 动态 IDLE_GAP. 旧洞: 固定 100s → GLM5.2 thinking 请求首块 reasoning 后上游
            # 长时间静默思考(实测>120s不发chunk), 100s 误判中断 → "Server error mid-response".
            # 现: 见过 reasoning_content (thinking 流) 用 200s 容纳长思考静默, 非 thinking 用 100s 快速兜底.
            # 200s > nv_gw thinking idle 180s, 让 nv_gw 先发 content_filter, cc4101 后兜底.
            _idle_gap = 200.0 if stream_reasoning_chars > 0 else CC4101_STREAM_IDLE_GAP_S
            if last_progress_time is not None and time.time() - last_progress_time > _idle_gap:
                metrics["error_type"] = "stream_idle_stall"
                # R1414 diag: stall 时 dump resp socket 的 timeout 值, 确认 30s poll 是否真生效
                _sockinfo = "?"
                try:
                    _sc = resp.fp.raw._sock
                    _sockinfo = f"fd={_sc.fileno()} gettimeout={_sc.gettimeout()}"
                except Exception as _e:
                    _sockinfo = f"dump_err={_e}"
                _log("STREAM-IDLE-STALL", f"({request_model}) no real content for "
                    f"{int(_idle_gap)}s (stall-watcher, last_progress_age="
                    f"{int(time.time()-last_progress_time)}s, thinking={'Y' if stream_reasoning_chars>0 else 'N'}) "
                    f"sock={_sockinfo}")
                raise socket.timeout("stream_idle_stall")
            try:
                chunk = resp.read(8192)
                # R1414 diag: 记录 read 返回字节数, 查路径B [DONE] 是否到达 cc4101
                if chunk:
                    _log("DBG", f"read got {len(chunk)}b tail={chunk[-40:]!r}")
            except socket.timeout:
                # per-read 短轮询超时 — 非致命, 上面的双门槛会在下一轮循环判定是否真 stall.
                # 若已达双门槛上限, 上面已 raise 了带 error_type 的 socket.timeout, 会落到下面的 except.
                continue
            except OSError as _read_e:
                # R846 修3 / R1415 真根因: socket.SocketIO.read() 在 sock.settimeout 超时后, 下次 read
                # 抛裸 OSError("cannot read from timed out object") (socket.py:717 _timeout_occurred).
                # R846 当非致命 continue, 但实测发现 http.client 的 fp 一旦进入 timed-out-object 状态就
                # **永久崩坏** — 之后即使数据已到达 socket (如 nv_gw 路径B 写的 [DONE]), resp.read() 永远
                # 抛 OSError 读不出来, cc4101 收不到 [DONE] → 100s stall-watcher kill → mid-response.
                # (2026-07-15 复现: sock.recv(MSG_PEEK) 能读到 [DONE] 但 resp.read 不能).
                # R1415 修复: timed-out-object 时不盲目 continue (会永久崩坏), 改用底层 sock.recv 直接
                # 读 socket buffer 里已到达但 http.client 读不出的数据. 读到就当正常 chunk 处理
                # (能收 [DONE] 走 graceful_end), 读不到 (真无数据) 才 continue 让 stall-watcher 判 stall.
                if "timed out object" in str(_read_e) or "timeout" in str(_read_e).lower():
                    try:
                        _sc = resp.fp.raw._sock
                        _peek = _sc.recv(8192, socket.MSG_PEEK)
                    except Exception:
                        _peek = b''
                    if _peek:
                        # socket buffer 有数据但 http.client 读不出 — 用 recv 取出当 chunk.
                        # MSG_PEEK 不消费, 但 http.client 已崩坏无法再用 read, 这里直接 recv 消费.
                        try:
                            chunk = _sc.recv(8192)
                        except Exception:
                            chunk = b''
                        if chunk:
                            _log("DBG", f"recv-fallback got {len(chunk)}b tail={chunk[-40:]!r} (http.client fp was timed-out, used sock.recv)")
                            # chunk 已拿到, 跳过下面的 resp.read 路径, 进入 chunk 解析.
                            # 用 continue 会回到循环顶 (先过 stall 检查), 但 chunk 变量已赋值.
                            # 此处直接落到 chunk 解析: 设标志让下面的 if not chunk / 解析逻辑处理.
                            # 简单做法: 手动处理 — 把 chunk 当 read 返回值, 用 goto 风格做不到,
                            # 改: 在 except 内不 continue, 而是让代码落到 except 之后的 chunk 解析.
                            # 但 except 块内赋值的 chunk 在 except 外不可见? 实际 Python except 内赋值
                            # 的变量在 except 块外可见. 但若 chunk 非空, 下面 "if not chunk" 不触发,
                            # 会走到 buffer += chunk. 但要注意: except 块执行后会跳过 try 内 chunk=resp.read
                            # 之后的代码, 直接到 except 块结束后的下一行. 这里我们需要 chunk 已赋值.
                            pass  # chunk 已赋值, 落到 except 后的 chunk 解析逻辑
                        else:
                            continue  # recv 返回空, 真无数据, continue 让 stall 判定
                    else:
                        continue  # PEEK 无数据, continue
                    # 注意: 若 chunk 非空, 代码落到 except 块外继续执行 (chunk 解析). 但 except 块后
                    # 紧接 "if not chunk:" — chunk 非空不触发, 继续 buffer += chunk. OK.
                else:
                    raise  # 真 OSError (连接重置等) — 致命, 落到下面的 except 处理
            if not chunk:
                # R846: 干净 EOF 但无 finish_reason = 上游断流伪装完成 (nv_gw deadline/except 静默 break).
                # 旧洞: 干净 EOF 不进 except → interrupted=False, 且若已开 block 则 empty_stream_response
                # 守卫 (next_block_idx==0) 也失效 → 直接走正常 message_stop → status=200+0token → Claude
                # Code 收到空响应. 现判定 "无 finish_reason + 已开 block + text content 极少 + 无真 tool_call + 大 input"
                # 当 zombie 处理, emit api_error 让 CC 重试整个请求.
                # R852: 只看 stream_content_chars (text answer), 不加 reasoning — thinking-only-empty 同样是空回答.
                if (pending_stop_reason is None and next_block_idx > 0
                        and not stream_saw_real_tool_call
                        and stream_content_chars < 50
                        and metrics.get("total_input_chars", 0) >= 5000):
                    stream_zombie = True
                    metrics["error_type"] = "zombie_clean_eof"
                    _record_primary_stream_fail("zombie_clean_eof")
                    _log("ZOMBIE-CLEAN-EOF", f"({request_model}) clean EOF without finish_reason but content="
                        f"{stream_content_chars}c reasoning={stream_reasoning_chars}c input="
                        f"{metrics.get('total_input_chars',0)}c no real tool_call — upstream silent disconnect, "
                        f"emitting api_error so CC retries (req={metrics.get('request_id','?')})")
                    _emit_graceful_end(zombie=True)
                    return
                break
            buffer += chunk.decode("utf-8", errors="replace")

            while "\n\n" in buffer:
                event_str, buffer = buffer.split("\n\n", 1)
                lines = event_str.split("\n")
                event_type = None
                data_str = ""
                for line in lines:
                    if line.startswith("event:"):
                        event_type = line[6:].strip()
                    elif line.startswith("data:"):
                        data_str = line[5:].strip()

                if data_str == "[DONE]":
                    _emit_graceful_end()
                    return
                # R1409: 跳过空 event (event_str 与 data_str 均空). nv_gw 的 NV-UPSTREAM-ERROR-CHUNK
                # 前置 \n\n (R846 Fix6) 在上游从未发过内容 (200-then-hang, ttfb_recorded=False) 时
                # 会产生一个前导空 event. 旧洞: 空 data_str 命中上面的 `not data_str` 分支 → 当作正常
                # 流结束 _emit_graceful_end()(非 zombie) → 发 end_turn → CC 不重试 → 用户看到 mid-response,
                # 且 nv_gw 真正的 content_filter chunk 永远没被解析. 现空 event 跳过, 让后续 content_filter
                # chunk + [DONE] 正常解析走 zombie 路径.
                if not data_str and not event_type and not event_str.strip():
                    continue

                if event_type and event_type != "chunk":
                    continue

                try:
                    chunk_data = json.loads(data_str)
                except json.JSONDecodeError:
                    _log("WARN", f"malformed SSE chunk: {data_str[:200]}")
                    # R846 Fix5: malformed chunk 兜底提取 content_filter.
                    # 旧洞: nv_gw 的 content_filter error chunk 若与上一个未 \n\n 终止的 event 拼接,
                    # json.loads 整体失败 → continue 吞掉 content_filter 信号 → cc4101 返回空 200.
                    # 此处兜底: data_str 含 "finish_reason":"content_filter" 子串即当上游断流信号,
                    # 走 zombie 路径 emit api_error 让 CC 重试. (Fix6 在 nv_gw 侧前置 \n\n 治本,
                    # 此处是下游兜底防 Fix6 失效/其他 malformed 拼接场景.)
                    if '"finish_reason":"content_filter"' in data_str or '"finish_reason": "content_filter"' in data_str:
                        stream_zombie = True
                        metrics["error_type"] = "upstream_content_filter_malformed"
                        _record_primary_stream_fail("upstream_content_filter_malformed")
                        _log("ZOMBIE-CONTENT-FILTER-MALFORMED", f"({request_model}) content_filter signal found in malformed chunk "
                            f"(nv_gw error chunk merged w/ prev event), emitting api_error so CC retries (req={metrics.get('request_id','?')})")
                        _emit_graceful_end(zombie=True)
                        return
                    continue

                choices = chunk_data.get("choices") or [{}]
                delta = choices[0].get("delta") or {}
                finish_reason = choices[0].get("finish_reason")

                chunk_usage = chunk_data.get("usage") or {}
                if chunk_usage:
                    pt = chunk_usage.get("prompt_tokens", 0)
                    ct = chunk_usage.get("completion_tokens", 0)
                    if pt > 0:
                        streaming_input_tokens = pt
                        metrics["input_tokens"] = pt
                    if ct > 0:
                        streaming_output_tokens = ct
                        metrics["output_tokens"] = ct

                if not message_start_sent:
                    _emit_message_start(chunk_data.get("id", f"msg_{uuid.uuid4().hex[:24]}"),
                                       input_tokens_est=metrics.get("estimated_input_tokens", 0))

                if not ttfb_recorded and (delta.get("content") or delta.get("reasoning_content") or delta.get("tool_calls")):
                    metrics["ttfb_ms"] = int((time.time() - t_start) * 1000)
                    ttfb_recorded = True
                    # R845 B7: ttfb 后启动 stall-watcher 双门槛计时
                    stream_total_deadline = time.time() + CC4101_STREAM_TOTAL_DEADLINE_S
                    last_progress_time = time.time()

                # R844 F5: 累积 content/reasoning 字符 + 标记真 tool_call (用于空僵尸判定)
                _delta_content = delta.get("content") or ""
                if _delta_content:
                    stream_content_chars += len(_delta_content)
                _delta_reasoning = delta.get("reasoning_content") or ""
                if _delta_reasoning:
                    stream_reasoning_chars += len(_delta_reasoning)
                for _tc in (delta.get("tool_calls") or []):
                    _fn = _tc.get("function", {}) or {}
                    if _tc.get("id") and _fn.get("arguments"):
                        stream_saw_real_tool_call = True
                # R845 B7: 收到真内容即刷新 idle 间隙计时 (防 drip 绕过: 持续产出时 idle 不超限)
                if _delta_content or _delta_reasoning or (delta.get("tool_calls") or []):
                    last_progress_time = time.time()

                # ── Reasoning/thinking ──
                # R690 cc2 red-team: Anthropic spec requires thinking blocks come BEFORE
                # text/tool_use and cannot re-open after. Once we've started a text or
                # tool_use block, drop further reasoning_content deltas instead of
                # opening a new thinking block (which CC would reject).
                reasoning = delta.get("reasoning_content")
                if reasoning and active_block_type not in (None, "thinking"):
                    reasoning = None
                if reasoning:
                    if active_block_type != "thinking":
                        if active_block_type is not None:
                            handler._send_sse("content_block_stop",
                                           {"type": "content_block_stop", "index": next_block_idx - 1})
                        handler._send_sse("content_block_start", {
                            "type": "content_block_start", "index": next_block_idx,
                            "content_block": {"type": "thinking", "thinking": "",
                                              "signature": THINKING_SIGNATURE_DEFAULT},
                        })
                        next_block_idx += 1
                        active_block_type = "thinking"
                    handler._send_sse("content_block_delta", {
                        "type": "content_block_delta", "index": next_block_idx - 1,
                        "delta": {"type": "thinking_delta", "thinking": reasoning},
                    })

                # ── Text ──
                text_delta = delta.get("content")
                if text_delta and active_block_type != "text":
                    if active_block_type is not None:
                        handler._send_sse("content_block_stop",
                                           {"type": "content_block_stop", "index": next_block_idx - 1})
                    handler._send_sse("content_block_start", {
                        "type": "content_block_start", "index": next_block_idx,
                        "content_block": {"type": "text", "text": ""},
                    })
                    next_block_idx += 1
                    active_block_type = "text"
                if text_delta:
                    handler._send_sse("content_block_delta", {
                        "type": "content_block_delta", "index": next_block_idx - 1,
                        "delta": {"type": "text_delta", "text": text_delta},
                    })

                # ── Tool calls ──
                tool_calls = delta.get("tool_calls") or []
                for tc in tool_calls:
                    fn = tc.get("function", {})
                    if tc.get("id"):
                        if active_block_type is not None:
                            handler._send_sse("content_block_stop",
                                           {"type": "content_block_stop", "index": next_block_idx - 1})
                        handler._send_sse("content_block_start", {
                            "type": "content_block_start", "index": next_block_idx,
                            "content_block": {
                                "type": "tool_use",
                                "id": tc["id"],
                                "name": fn.get("name", ""),
                                "input": {},
                            },
                        })
                        next_block_idx += 1
                        active_block_type = "tool_use"
                        if fn.get("arguments"):
                            handler._send_sse("content_block_delta", {
                                "type": "content_block_delta", "index": next_block_idx - 1,
                                "delta": {"type": "input_json_delta", "partial_json": fn["arguments"]},
                            })
                    elif fn.get("arguments") and active_block_type == "tool_use":
                        handler._send_sse("content_block_delta", {
                            "type": "content_block_delta", "index": next_block_idx - 1,
                            "delta": {"type": "input_json_delta", "partial_json": fn["arguments"]},
                        })

                # ── Finish ──
                if finish_reason:
                    if active_block_type is not None:
                        handler._send_sse("content_block_stop",
                                           {"type": "content_block_stop", "index": next_block_idx - 1})
                        active_block_type = None
                    metrics["finish_reason"] = finish_reason
                    # R844 F4: nv_gw 死亡窗口 zombie 会发 finish_reason=content_filter 的 err_chunk (R840).
                    # 原代码把它当正常 end_turn → Claude Code 认为完成不重试, 吞掉 fallback. 改: emit api_error.
                    if finish_reason == "content_filter":
                        stream_zombie = True
                        metrics["error_type"] = "upstream_content_filter"
                        # R1638: polarity 分流 (死根2). nv_gw 在 first-byte/no-content-gap/total deadline
                        # 主动 break 时发 content_filter err_chunk (nv_gw 日志 NV-UPSTREAM-ERROR-CHUNK
                        # zombie=False error_type=stream_first_byte_timeout/...), 设计意图=R1408 让 CC 重试,
                        # **不**计 breaker — 否则累积 CC4101_PRIMARY_FAIL_THRESHOLD(8) 次 → circuit OPEN
                        # 503 死循环 (实测已 4/8 次). 这些主动 break 全是 stream_content_chars=0
                        # reasoning_chars=0 (output_tokens=0, 8 个 req 实测); 真僵尸 (clean_eof/empty_completion)
                        # 往往有非零内容累积仍计. 严格按"无内容 = nv_gw 主动快速失败" vs "有内容 = 真中途死亡"切分.
                        # 此处只动 content_filter 路径; zombie_clean_eof(304)/malformed(353)/empty_completion(510)
                        # 等其他失败点仍 record_primary_failure — 留观察, 不在本轮 polarity 范围.
                        # 详见 [[r1638-cc4101-header-inversion-breaker-polarity]]
                        if stream_content_chars == 0 and stream_reasoning_chars == 0:
                            _log("ZOMBIE-CONTENT-FILTER", f"({request_model}) upstream sent finish_reason=content_filter "
                                f"(nv_gw active fail, no content yet — NOT counted to breaker), "
                                f"emitting api_error so Claude Code retries (req={metrics.get('request_id','?')})")
                        else:
                            _record_primary_stream_fail("upstream_content_filter")
                            _log("ZOMBIE-CONTENT-FILTER", f"({request_model}) upstream sent finish_reason=content_filter "
                                f"(content={stream_content_chars}c reasoning={stream_reasoning_chars}c — mid-flight zombie, "
                                f"counted to breaker), emitting api_error (req={metrics.get('request_id','?')})")
                        _emit_graceful_end(zombie=True)
                        return
                    # R844 F5: 自身空僵尸检测. 大 input + text content 极少 + 无真 tool_call + finish in (stop,tool_calls)
                    # → NVCF 返空壳 (dsv4p 大 context 1793 例, glm5.2 死亡窗口, glm5.2 thinking-only-empty). 不发 end_turn, emit api_error 让 CC 重试.
                    # R852: 只看 stream_content_chars (text answer), 不加 reasoning_chars. GLM5.2 thinking 模式
                    # 实测产出 3182c reasoning 但 0c content — 答案写进思考里, CC 报 empty/filtered completion. 此处抓到.
                    # R852c: 扩展 finish_reason=length. thinking 请求 reasoning 涨到 max_tokens(2048) 时 content 仍空,
                    # 上游返 finish_reason=length + 0c content. 旧代码只抓 stop/tool_calls, length 漏网 -> cc4101 发
                    # 干净 message_stop(max_tokens) -> CC 收空回答报 empty/filtered. 现 length 也判 zombie (需 reasoning>0
                    # 佐证是 thinking-only 截断, 非 真 length-truncated 有文本的答案).
                    _is_thinking_only_length = (
                        finish_reason == "length"
                        and stream_content_chars < 50
                        and stream_reasoning_chars > 50
                    )
                    if ((finish_reason in ("stop", "tool_calls") or _is_thinking_only_length)
                            and not stream_saw_real_tool_call
                            and stream_content_chars < 50
                            and metrics.get("total_input_chars", 0) >= 5000):
                        stream_zombie = True
                        metrics["error_type"] = "zombie_empty_completion"
                        _record_primary_stream_fail("zombie_empty_completion")
                        _log("ZOMBIE-EMPTY-STREAM", f"({request_model}) zombie empty stream: finish_reason={finish_reason} "
                            f"content={stream_content_chars}c reasoning={stream_reasoning_chars}c input="
                            f"{metrics.get('total_input_chars',0)}c no real tool_call — emitting api_error so CC retries "
                            f"(req={metrics.get('request_id','?')})")
                        _emit_graceful_end(zombie=True)
                        return
                    stop_reason = "end_turn"
                    if finish_reason == "length":
                        stop_reason = "max_tokens"
                    elif finish_reason == "tool_calls":
                        stop_reason = "tool_use"
                    pending_stop_reason = stop_reason

    except socket.timeout as e:
        elapsed_ms = int((time.time() - t_start) * 1000)
        # R845 B2: 区分 stall-watcher 命中 vs per-read 真 idle vs 上游断连伪装成 socket.timeout.
        # a1db6f13: 上游 120.8s 主动断连被 http.client read() 映射成 socket.timeout, 但 120.8 < 150s
        # 说明 per-read 不可能因 idle 触发 (150s 没到), 只能是上游断连 — 旧代码一律记 StreamSocketTimeout
        # 误导运维去调 timeout 治标不治本. 现按 error_type/elapsed 三分.
        if metrics.get("error_type") in ("stream_total_deadline", "stream_idle_stall"):
            error_subcat = metrics["error_type"]
            timeout_kind = "stall_watcher"
            log_lvl, log_tag = "STREAM-STALLED", "stall-watcher"
            metrics["error_type"] = "StreamStallWatcher"
            _record_primary_stream_fail("StreamStallWatcher")
        elif elapsed_ms >= UPSTREAM_IDLE_TIMEOUT * 1000 - 500:
            # 接近/超过 per-read 预算 (旧 150s 语义) = 真 idle, 上游静默
            error_subcat = "stream_socket_timeout"
            timeout_kind = "idle"
            log_lvl, log_tag = "TIMEOUT", "idle"
            metrics["error_type"] = "StreamSocketTimeout"
            _record_primary_stream_fail("StreamSocketTimeout")
        else:
            # elapsed < per-read 预算 = per-read 没到点就抛, 只能是上游主动 FIN/RST
            error_subcat = "stream_upstream_disconnect"
            timeout_kind = "upstream_disconnect"
            log_lvl, log_tag = "ERR", "upstream_disconnect"
            metrics["error_type"] = "StreamUpstreamDisconnect"
            _record_primary_stream_fail("StreamUpstreamDisconnect")
        _log_error_detail({
            "request_id": metrics.get("request_id", "?"),
            "timestamp": datetime.datetime.now().isoformat(),
            "error_subcategory": error_subcat,
            "upstream_timeout_setting_ms": UPSTREAM_IDLE_TIMEOUT * 1000,
            "upstream_timeout_kind": timeout_kind,
            "elapsed_since_request_start_ms": elapsed_ms,
            "mapped_model": metrics.get("mapped_model", "?"),
            "upstream_used": metrics.get("upstream_used", "?"),
            "error_message": str(e)[:200],
        })
        _log(log_lvl, f"stream {log_tag} after {elapsed_ms}ms "
            f"(UPSTREAM_IDLE_TIMEOUT={UPSTREAM_IDLE_TIMEOUT}s, POLL={CC4101_STREAM_POLL_S}s): {e}")
        _emit_graceful_end(interrupted=True)
        return
    except (http.client.RemoteDisconnected, ConnectionResetError,
            OSError, http.client.IncompleteRead) as e:
        elapsed_ms = int((time.time() - t_start) * 1000)
        error_class = type(e).__name__
        _log("ERR", f"stream {error_class} after {elapsed_ms}ms: {e}")
        _log_error_detail({
            "request_id": metrics.get("request_id", "?"),
            "timestamp": datetime.datetime.now().isoformat(),
            "error_subcategory": f"stream_{error_class}",
            "elapsed_since_request_start_ms": elapsed_ms,
            "mapped_model": metrics.get("mapped_model", "?"),
            "upstream_used": metrics.get("upstream_used", "?"),
            "error_message": str(e)[:300],
        })
        _emit_graceful_end(interrupted=True)
        return
    except Exception as e:
        _log("ERR", f"stream unexpected error: {e}")
        _emit_graceful_end(interrupted=True)
        return

    _emit_graceful_end()


def collect_stream_to_anth(handler, resp, request_model, target_model, conn, metrics, t_start):
    """Collect a streaming SSE response from upstream and synthesize a non-stream
    Anthropic-format response. Used when CC requests stream=false (upstream still
    streams — glm5.2 non-stream is broken on both backends)."""
    reasoning_text = ""
    content_text = ""
    tool_calls_data = []
    finish_reason = "stop"
    total_input_tokens = 0
    total_output_tokens = 0
    msg_id = f"msg_{uuid.uuid4().hex[:24]}"
    ttfb_recorded = False
    buffer = ""
    empty_stream = True  # assume empty until we see real content
    # R845 B7: stall-watcher 双门槛状态 (同 stream_to_anth)
    stream_total_deadline = None
    last_progress_time = None

    try:
        done = False
        while not done:
            # R845 B7: stall-watcher 双门槛检查点 (同 stream_to_anth)
            if ttfb_recorded and stream_total_deadline and time.time() > stream_total_deadline:
                metrics["error_type"] = "collect_stream_total_deadline"
                _log("STREAM-DEADLINE", f"({request_model}) collect stream total deadline "
                    f"{CC4101_STREAM_TOTAL_DEADLINE_S}s after ttfb exceeded (stall-watcher)")
                raise socket.timeout("collect_stream_total_deadline")
            if last_progress_time is not None and time.time() - last_progress_time > CC4101_STREAM_IDLE_GAP_S:
                metrics["error_type"] = "collect_stream_idle_stall"
                _log("STREAM-IDLE-STALL", f"({request_model}) collect no real content for "
                    f"{CC4101_STREAM_IDLE_GAP_S}s (stall-watcher)")
                raise socket.timeout("collect_stream_idle_stall")
            try:
                chunk = resp.read(8192)
                # R1414 diag: 记录 read 返回字节数, 查路径B [DONE] 是否到达 cc4101
                if chunk:
                    _log("DBG", f"read got {len(chunk)}b tail={chunk[-40:]!r}")
            except socket.timeout:
                continue
            except OSError as _read_e:
                # R846 修3 / R1415 / R1674: per-read 短轮询超时抛裸 OSError("cannot read from timed out
                # object") (socket.py:717 _timeout_occurred), 非 socket.timeout 子类. http.client 的 fp
                # 一旦进入 timed-out-object 状态就 **永久崩坏** — 之后即使数据已到达 socket (如 nv_gw
                # FULL_BUFFER deadline 命中后写的 content_filter err_chunk), resp.read() 永远抛 OSError
                # 读不出来, cc4101 nonstream 收不到 → collect 死循环 read → CC 超时 "{ Request timed out}".
                # (2026-07-17 复现: 294929 大 input, nv_gw 45s deadline 砍后发 err_chunk, cc4101 读不到,
                #  CC 等 62s 自超时). R1415 修了 stream_to_anth (L258 recv-fallback), collect 路径漏修.
                # R1674: collect 路径补同款 recv-fallback — 用 sock.recv(MSG_PEEK) 看 socket buffer 有
                # 无已到达数据, 有则 recv 取出当 chunk 处理 (能收 [DONE]/content_filter 走正常结束),
                # 无则 continue 让 stall-watcher 判真 stall.
                if "timed out object" in str(_read_e) or "timeout" in str(_read_e).lower():
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
                            _log("DBG", f"collect recv-fallback got {len(chunk)}b tail={chunk[-40:]!r} "
                                f"(http.client fp was timed-out, used sock.recv)")
                            pass  # chunk 已赋值, 落到 except 后的 chunk 解析逻辑
                        else:
                            continue
                    else:
                        continue
                else:
                    raise
            if not chunk:
                break
            buffer += chunk.decode("utf-8", errors="replace")

            while "\n\n" in buffer:
                event_str, buffer = buffer.split("\n\n", 1)
                lines = event_str.split("\n")
                event_type = None
                data_str = ""
                for line in lines:
                    if line.startswith("event:"):
                        event_type = line[6:].strip()
                    elif line.startswith("data:"):
                        data_str = line[5:].strip()

                if not data_str or data_str == "[DONE]":
                    # Stream complete. ms_gw keeps the socket open after [DONE]
                    # (no Connection: close), so we must actively close here —
                    # otherwise resp.read() blocks until UPSTREAM_TIMEOUT.
                    done = True
                    break

                if event_type and event_type != "chunk":
                    continue

                try:
                    chunk_data = json.loads(data_str)
                except json.JSONDecodeError:
                    continue

                if not ttfb_recorded:
                    metrics["ttfb_ms"] = int((time.time() - t_start) * 1000)
                    ttfb_recorded = True
                    # R845 B7: ttfb 后启动 stall-watcher 双门槛计时
                    stream_total_deadline = time.time() + CC4101_STREAM_TOTAL_DEADLINE_S
                    last_progress_time = time.time()

                msg_id = chunk_data.get("id", msg_id)
                choices = chunk_data.get("choices") or [{}]
                delta = choices[0].get("delta") or {}
                fr = choices[0].get("finish_reason")

                reasoning = delta.get("reasoning_content") or ""
                if reasoning:
                    reasoning_text += reasoning
                    empty_stream = False

                text = delta.get("content") or ""
                if text:
                    content_text += text
                    empty_stream = False

                # R845 B7: 收到真内容刷新 idle 计时
                if reasoning or text or (delta.get("tool_calls") or []):
                    last_progress_time = time.time()

                tool_calls = delta.get("tool_calls") or []
                for tc in tool_calls:
                    fn = tc.get("function", {})
                    if tc.get("id"):
                        tool_calls_data.append({
                            "id": tc["id"],
                            "name": fn.get("name", ""),
                            "arguments": fn.get("arguments", ""),
                        })
                        # R844 F6: 只有带 arguments 的真 tool_call 才算非空 (空壳 id+空args 不算)
                        if fn.get("arguments"):
                            empty_stream = False
                    elif fn.get("arguments") and tool_calls_data:
                        tool_calls_data[-1]["arguments"] += fn["arguments"]

                chunk_usage = chunk_data.get("usage") or {}
                if chunk_usage:
                    total_input_tokens = chunk_usage.get("prompt_tokens", total_input_tokens)
                    total_output_tokens = chunk_usage.get("completion_tokens", total_output_tokens)

                if fr:
                    finish_reason = fr

        conn.close()
    except socket.timeout as e:
        elapsed_ms = int((time.time() - t_start) * 1000)
        # R845 B2: collect 路径同样区分 stall-watcher / idle / 上游断连 (同 stream_to_anth)
        if metrics.get("error_type") in ("collect_stream_total_deadline", "collect_stream_idle_stall"):
            error_subcat = metrics["error_type"]
            timeout_kind = "stall_watcher"
            log_lvl, log_tag = "STREAM-STALLED", "stall-watcher"
            metrics["error_type"] = "CollectStreamStallWatcher"
        elif elapsed_ms >= UPSTREAM_IDLE_TIMEOUT * 1000 - 500:
            error_subcat = "collect_stream_socket_timeout"
            timeout_kind = "idle"
            log_lvl, log_tag = "TIMEOUT", "idle"
            metrics["error_type"] = "CollectStreamSocketTimeout"
        else:
            error_subcat = "collect_stream_upstream_disconnect"
            timeout_kind = "upstream_disconnect"
            log_lvl, log_tag = "ERR", "upstream_disconnect"
            metrics["error_type"] = "CollectStreamUpstreamDisconnect"
        _log_error_detail({
            "request_id": metrics.get("request_id", "?"),
            "timestamp": datetime.datetime.now().isoformat(),
            "error_subcategory": error_subcat,
            "upstream_timeout_kind": timeout_kind,
            "upstream_timeout_setting_ms": UPSTREAM_IDLE_TIMEOUT * 1000,
            "elapsed_since_request_start_ms": elapsed_ms,
            "mapped_model": metrics.get("mapped_model", "?"),
            "upstream_used": metrics.get("upstream_used", "?"),
            "error_message": str(e)[:200],
        })
        _log(log_lvl, f"collect_stream {log_tag} after {elapsed_ms}ms "
            f"(UPSTREAM_IDLE_TIMEOUT={UPSTREAM_IDLE_TIMEOUT}s, POLL={CC4101_STREAM_POLL_S}s): {e}")
        try:
            conn.close()
        except Exception:
            pass
    except Exception as e:
        elapsed_ms = int((time.time() - t_start) * 1000)
        error_class = type(e).__name__
        _log("ERR", f"collect_stream {error_class} after {elapsed_ms}ms: {e}")
        _log_error_detail({
            "request_id": metrics.get("request_id", "?"),
            "timestamp": datetime.datetime.now().isoformat(),
            "error_subcategory": f"collect_stream_{error_class}",
            "elapsed_since_request_start_ms": elapsed_ms,
            "error_message": str(e)[:300],
        })
        try:
            conn.close()
        except Exception:
            pass

    # R844 F4/F6: content_filter finish_reason (nv_gw R840 zombie err_chunk) → 空僵尸
    if finish_reason == "content_filter":
        _log("ZOMBIE-CONTENT-FILTER-COLLECT", f"({metrics.get('request_model','?')}) finish_reason=content_filter "
            f"from upstream (nv_gw zombie) — treating as empty (req={metrics.get('request_id','?')})")
        metrics["empty_stream_response"] = True
        metrics["error_type"] = "upstream_content_filter"
        _log_error_detail({
            "request_id": metrics.get("request_id", "?"),
            "timestamp": datetime.datetime.now().isoformat(),
            "error_subcategory": "upstream_content_filter",
            "upstream_used": metrics.get("upstream_used", "?"),
            "mapped_model": metrics.get("mapped_model", "?"),
            "finish_reason": finish_reason,
        })
    # Empty-stream detection (glm5.2 sometimes returns only reasoning then [DONE]
    # with no content; if BOTH reasoning and content and tool_calls are empty, that's empty)
    elif empty_stream and not reasoning_text and not content_text and not tool_calls_data:
        _log("WARN", f"empty_stream_response (collect): model={metrics.get('mapped_model','?')} "
                     f"output_tokens={total_output_tokens}")
        _log_error_detail({
            "request_id": metrics.get("request_id", "?"),
            "timestamp": datetime.datetime.now().isoformat(),
            "error_subcategory": "empty_stream_response",
            "upstream_used": metrics.get("upstream_used", "?"),
            "mapped_model": metrics.get("mapped_model", "?"),
            "total_output_tokens": total_output_tokens,
            "finish_reason": finish_reason,
        })
        metrics["empty_stream_response"] = True
    # R844 F5/F6: 大 input + 少 content + 无真 tool_call + finish in (stop,tool_calls) → 空壳僵尸
    # (dsv4p 大 context 空壳 tool_calls, glm5.2 死亡窗口). collect 路径返回 502 让 CC 重试.
    elif (finish_reason in ("stop", "tool_calls")
          and (len(reasoning_text) + len(content_text)) < 50
          and not any(tc.get("arguments") for tc in tool_calls_data)
          and metrics.get("total_input_chars", 0) >= 5000):
        _log("ZOMBIE-EMPTY-COLLECT", f"({metrics.get('request_model','?')}) zombie empty collect: "
            f"finish={finish_reason} content={len(content_text)}c reasoning={len(reasoning_text)}c "
            f"input={metrics.get('total_input_chars',0)}c no real tool_call (req={metrics.get('request_id','?')})")
        metrics["empty_stream_response"] = True
        metrics["error_type"] = "zombie_empty_completion"
        _log_error_detail({
            "request_id": metrics.get("request_id", "?"),
            "timestamp": datetime.datetime.now().isoformat(),
            "error_subcategory": "zombie_empty_completion",
            "upstream_used": metrics.get("upstream_used", "?"),
            "mapped_model": metrics.get("mapped_model", "?"),
            "finish_reason": finish_reason,
            "total_input_chars": metrics.get("total_input_chars", 0),
        })

    # Synthesize Anthropic non-stream response
    content = []
    if reasoning_text:
        content.append({"type": "thinking", "thinking": reasoning_text,
                        "signature": THINKING_SIGNATURE_DEFAULT})
    if content_text:
        content.append({"type": "text", "text": content_text})
    for tc_data in tool_calls_data:
        try:
            input_data = json.loads(tc_data["arguments"])
        except json.JSONDecodeError:
            input_data = {"raw": tc_data["arguments"]}
        content.append({"type": "tool_use", "id": tc_data["id"],
                        "name": tc_data["name"], "input": input_data})
    if not content:
        content.append({"type": "text", "text": ""})

    stop_reason = "end_turn"
    if finish_reason == "length":
        stop_reason = "max_tokens"
    elif finish_reason == "tool_calls":
        stop_reason = "tool_use"

    if metrics.get("error_type") and metrics["error_type"] not in (None, "empty_stream_response"):
        metrics["status"] = 502
    elif metrics.get("empty_stream_response"):
        metrics["status"] = 502
        metrics["error_type"] = "empty_stream_response"
    else:
        metrics["status"] = 200
    metrics["duration_ms"] = int((time.time() - t_start) * 1000)
    metrics["input_tokens"] = total_input_tokens
    metrics["output_tokens"] = total_output_tokens
    metrics["finish_reason"] = finish_reason
    _log_metrics(metrics)

    # R690 cc2 red-team: previously hardcoded _send_json(200, ...) even when
    # metrics status was 502 (empty stream / socket error). That made CC treat
    # truncated/empty responses as success and not retry. Now honor the real
    # status, and on error return a proper Anthropic error payload (so CC retries)
    # instead of an empty-content success message.
    client_status = metrics.get("status", 200)
    if client_status >= 400:
        from .error_mapping import convert_error
        error_payload = convert_error(
            {"error": {"message": metrics.get("error_message") or metrics.get("error_type") or "upstream stream failed"}},
            request_model,
        )
        handler._send_json(client_status, error_payload)
        return

    anth_response = {
        "id": msg_id,
        "type": "message",
        "role": "assistant",
        "model": request_model,
        "content": content,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {
            "input_tokens": total_input_tokens,
            "output_tokens": total_output_tokens,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
        },
    }
    handler._send_json(client_status, anth_response)
