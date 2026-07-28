# ════════════════════════════════════════════════════════════════════
# R2192 任务3 骨架: anthropic to_anth 路径 zombie 命中后内部换 key 重试
# 落盘到: /opt/cc-infra/proxy/nv-gw/gateway/handlers.py (_stream_openai_to_anth, L909)
# 改前备份: cp handlers.py handlers.py.bak.RNN_task3
# 改后: docker compose restart nv_gw
# 回滚: NVU_ZOMBIE_KEYRETRY_KEYS=0 + restart, 或 .bak
# ════════════════════════════════════════════════════════════════════
#
# 关键 (核证 converter 源码 oai_to_anth.py):
# - converter 有 message_start_sent 守卫 (L116): 换 key 重放新流不重发 message_start. ✅
# - converter 无 next_block_idx/active_block_type 重置守卫 → 必须限制只在
#   content_chars==0 且 reasoning_chars==0 且 saw_tool_calls==False 时重试.
#   (此时 converter 只发了 message_start, 没开任何 content_block, 状态干净.)
# - 换 key 重放新流: 不重置 converter (保留 message_start_sent=True). 只 swap resp/conn.
# - 实测近24h to_anth zombie: 14/24 为 content=0c reasoning=0c (干净, 可重试覆盖58%).
#
# ─── 新增 upstream.py 函数 (镜像 _peek_retry_next_key, L492 附近) ───
def _zombie_retry_next_key(oai_body, tier_model, request_id, metrics, t_start,
                           is_stream, prior_cycle_attempts, start_key_idx,
                           upstream_timeout_override=None):
    """R2192 task3: 主循环 zombie 命中后内部换 ONE 个 NVCF key 整流重放 (不 advance RR)."""
    return _try_tier_keys(oai_body, tier_model, request_id, metrics, t_start,
                         is_stream, prior_cycle_attempts,
                         upstream_timeout_override=upstream_timeout_override,
                         start_key_idx_override=start_key_idx,
                         max_attempts_override=1)

# ─── handlers.py 顶部 import (L49) ───
# from .upstream import (execute_request, UpstreamResult, _ms_fallback_request,
#                        _peek_retry_next_key, _zombie_retry_next_key)

# ─── config.py knob (L501 附近) ───
NVU_ZOMBIE_KEYRETRY_KEYS = int(os.environ.get('NVU_ZOMBIE_KEYRETRY_KEYS', '2'))
NVU_ZOMBIE_KEYRETRY_BUDGET_S = float(os.environ.get('NVU_ZOMBIE_KEYRETRY_BUDGET_S', '0'))

# ─── _stream_openai_to_anth (L909) 改造 ───
# 在 zombie 检测块 (L1509-1527) 改造. 当前命中后直接 set zombie_detected → finish(zombie=True).

# === 函数开头 (L930 zombie_detected = False 附近) 新增重试状态初始化 ===
        _zombie_keyretry_left = NVU_ZOMBIE_KEYRETRY_KEYS
        _zombie_keyretry_next_k = -1
        _zombie_keyretry_budget_deadline = (
            time.time() + NVU_ZOMBIE_KEYRETRY_BUDGET_S
            if NVU_ZOMBIE_KEYRETRY_BUDGET_S > 0 else None
        )

# === L1509-1527 zombie 命中块改造 ===
# 当前:
#   elif (fr in ("stop","tool_calls") and not saw_tool_calls
#           and content_chars < NVU_ZOMBIE_EMPTY_CONTENT_CHARS
#           and metrics.get("total_input_chars",0) >= NVU_ZOMBIE_MIN_INPUT_CHARS):
#       zombie_detected = True
#       metrics["error_type"] = "zombie_empty_completion"
#       _log("NV-ANTH-ZOMBIE", ...)
#       _dump_zombie_body(...)
#       ...big_input breaker...
#
# 改造为:
                        elif (fr in ("stop", "tool_calls")
                                and not saw_tool_calls
                                and content_chars < NVU_ZOMBIE_EMPTY_CONTENT_CHARS
                                and metrics.get("total_input_chars", 0) >= NVU_ZOMBIE_MIN_INPUT_CHARS):
                            # R2192 task3: 干净 zombie (content==0 且 reasoning==0) + 剩余次数 → 内部换 key 重放
                            _can_zr_anth = (
                                content_chars == 0
                                and reasoning_chars == 0
                                and not saw_tool_calls
                                and _zombie_keyretry_left > 0
                            )
                            if _can_zr_anth and not (_zombie_keyretry_budget_deadline
                                                     and time.time() > _zombie_keyretry_budget_deadline):
                                _zombie_keyretry_left -= 1
                                if _zombie_keyretry_next_k < 0:
                                    _orig_k = metrics.get("nv_key_idx", -1)
                                    _zombie_keyretry_next_k = (
                                        ((_orig_k + 1) % NVU_NUM_KEYS) if _orig_k >= 0 else 0
                                    )
                                _zr_k = _zombie_keyretry_next_k
                                _log("NV-ZOMBIE-KEYRETRY-TRY",
                                     f"({request_model}) anth zombie keyretry k{_zr_k+1} "
                                     f"(left={_zombie_keyretry_left}, req={metrics.get('request_id','?')})")
                                try:
                                    conn.close()
                                except Exception:
                                    pass
                                _mapped = metrics.get("mapped_model", request_model)
                                _zr = _zombie_retry_next_key(
                                    oai_body, _mapped, metrics.get("request_id", "?"),
                                    metrics, t_start, True, [], _zr_k, None)
                                if (_zr and _zr.resp is not None
                                        and _zr.conn is not None
                                        and not _zr.all_keys_exhausted):
                                    # 新 key 健康成功 → swap resp/conn, 不重置 converter (保留 message_start_sent=True)
                                    resp = _zr.resp
                                    conn = _zr.conn
                                    metrics["nv_key_idx"] = _zr.nv_key_idx
                                    metrics["egress_route"] = _zr.egress_route
                                    metrics["egress_ip"] = _zr.egress_ip
                                    metrics["litellm_model"] = _zr.nv_model_label
                                    metrics["zombie_keyretry_rescued"] = True
                                    metrics["zombie_keyretry_attempts"] = (
                                        NVU_ZOMBIE_KEYRETRY_KEYS - _zombie_keyretry_left
                                    )
                                    # 重置流式循环状态 (不碰 converter!)
                                    sse_buffer = ""
                                    content_chars = 0
                                    reasoning_chars = 0
                                    saw_tool_calls = False
                                    zombie_detected = False  # 清除, 回循环顶读新 resp
                                    # 重置 poll_sock
                                    try:
                                        _poll_sock = conn.sock
                                        if _poll_sock is None and resp is not None:
                                            _poll_sock = resp.fp.raw._sock
                                        if _poll_sock is not None:
                                            _poll_sock.settimeout(NVU_STREAM_POLL_S)
                                    except Exception:
                                        _poll_sock = None
                                    # 重置 deadline (新流重新计时)
                                    _ic = metrics.get("total_input_chars", 0) or 0
                                    _fb_s = (NVU_STREAM_FIRST_BYTE_DEADLINE_S if _ic <= 50000
                                             else float(os.environ.get("NVU_STREAM_FB_50K_S","60")) if _ic <= 200000
                                             else float(os.environ.get("NVU_STREAM_FB_200K_S","45")) if _ic <= 350000
                                             else float(os.environ.get("NVU_STREAM_FB_350K_S","60")))
                                    stream_first_byte_deadline = time.time() + _fb_s
                                    stream_idle_deadline = None
                                    last_real_content_time = None
                                    cap_origin = time.time()
                                    _zombie_keyretry_next_k = (_zr.nv_key_idx + 1) % NVU_NUM_KEYS
                                    _log("NV-ZOMBIE-KEYRETRY-RESCUE",
                                         f"({request_model}) anth k{_zr.nv_key_idx+1} rescued, "
                                         f"resuming (converter kept, req={metrics.get('request_id','?')})")
                                    continue  # 回 while 顶读新 resp
                                else:
                                    _log("NV-ZOMBIE-KEYRETRY-FAIL",
                                         f"({request_model}) anth k{_zr_k+1} also zombie/fail, "
                                         f"next (req={metrics.get('request_id','?')})")
                                    _zombie_keyretry_next_k = (_zr_k + 1) % NVU_NUM_KEYS
                                    continue
                            else:
                                # 不干净 (content>0/reasoning>0/saw_tool_calls) 或 budget/次数耗尽 → 保持现状
                                zombie_detected = True
                                metrics["error_type"] = "zombie_empty_completion"
                                _log("NV-ANTH-ZOMBIE",
                                     f"({request_model}) anth zombie (no keyretry: content={content_chars}c "
                                     f"reasoning={reasoning_chars}c left={_zombie_keyretry_left}), "
                                     f"finishing as zombie (req={metrics.get('request_id','?')})")
                                _dump_zombie_body(oai_body, request_model, metrics, trigger="stream_zombie")
                                _log("NV-ZOMBIE-WIRE", f"({request_model}) fr={fr} content={content_chars}c "
                                     f"reasoning={reasoning_chars}c | sse_buf_tail={sse_buffer[-600:]!r}")
                                _bi_input = metrics.get("total_input_chars", 0) or 0
                                if big_input_breaker.is_big_input(_bi_input):
                                    big_input_breaker.record_big_input_failure("zombie_empty_completion")
                                    _log("NV-BIGINPUT-FAIL", f"big_input anth stream zombie for {request_model} "
                                         f"input={_bi_input}c (req={metrics.get('request_id','?')}), "
                                         f"breaker={big_input_breaker.big_input_breaker_state()}")

# 注意: 原 finish(zombie=True) 分支保留 — 只在不可重试 (zombie_detected=True) 时走.
# 可重试路径 continue 后, 若 _zombie_keyretry_left 归 0 仍 zombie → _can_zr_anth=False →
#   set zombie_detected → 走 finish(zombie=True) 下沉.
