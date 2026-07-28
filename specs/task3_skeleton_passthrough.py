# ════════════════════════════════════════════════════════════════════
# R2192 任务3 骨架: openai passthrough 路径 zombie 命中后内部换 key 重试
# 落盘到: /opt/cc-infra/proxy/nv-gw/gateway/handlers.py (_stream_openai_passthrough, L1825)
# 改前备份: cp handlers.py handlers.py.bak.RNN_task3
# 改后: docker compose restart nv_gw
# 回滚: NVU_ZOMBIE_KEYRETRY_KEYS=0 + restart, 或 .bak
# ════════════════════════════════════════════════════════════════════
#
# 设计要点 (见 spec 第1/4节):
# 1. 只对 content_chars==0 且 reasoning_chars==0 且 saw_tool_calls==False 的 zombie 重试.
#    (passthrough 无 converter, openai 透传. 零内容时下游只收空 delta, 换 key 重放无重复.)
# 2. 实测近24h passthrough zombie: content_chars=0 的几乎都带 reasoning (glm5.2 thinking,
#    reasoning 3356-5078c) → reasoning_chars>0 → 不重试. 故本路径重试命中预期低.
#    主要受益方是 to_anth (cc2 自身). 但仍加守卫逻辑兜住干净的 case.
# 3. 全 key (NVU_ZOMBIE_KEYRETRY_KEYS 次) 都 zombie → set zombie_detected → 注 content_filter 下沉.
# 4. 不 advance RR (用 _try_tier_keys 的 start_key_idx_override, R2224 已有).
# 5. to_anth 路径另见 task3_skeleton_to_anth.py.

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

# ─── handlers.py import (L49) ───
# from .upstream import (execute_request, UpstreamResult, _ms_fallback_request,
#                        _peek_retry_next_key, _zombie_retry_next_key)

# ─── config.py knob (L501 附近) ───
NVU_ZOMBIE_KEYRETRY_KEYS = int(os.environ.get('NVU_ZOMBIE_KEYRETRY_KEYS', '2'))
NVU_ZOMBIE_KEYRETRY_BUDGET_S = float(os.environ.get('NVU_ZOMBIE_KEYRETRY_BUDGET_S', '0'))

# ─── _stream_openai_passthrough (L1825) 改造 ───
# 函数开头 (L1837 zombie_detected = False 附近) 新增:
        _zombie_keyretry_left = NVU_ZOMBIE_KEYRETRY_KEYS
        _zombie_keyretry_next_k = -1
        _zombie_keyretry_budget_deadline = (
            time.time() + NVU_ZOMBIE_KEYRETRY_BUDGET_S
            if NVU_ZOMBIE_KEYRETRY_BUDGET_S > 0 else None
        )

# L2057-2070 zombie 命中块改造. 当前:
#   if (fr in ("stop","tool_calls") and not passthrough_saw_tool_calls
#           and passthrough_content_chars < NVU_ZOMBIE_EMPTY_CONTENT_CHARS
#           and metrics.get("total_input_chars",0) >= NVU_ZOMBIE_MIN_INPUT_CHARS):
#       zombie_detected = True
#       metrics["error_type"] = "zombie_empty_completion"
#       _log("NV-ZOMBIE-EMPTY", ...)
#
# 改造为:
                                        if (fr in ("stop", "tool_calls")
                                                and not passthrough_saw_tool_calls
                                                and passthrough_content_chars < NVU_ZOMBIE_EMPTY_CONTENT_CHARS
                                                and metrics.get("total_input_chars", 0) >= NVU_ZOMBIE_MIN_INPUT_CHARS):
                                            _can_zr_ps = (
                                                passthrough_content_chars == 0
                                                and passthrough_reasoning_chars == 0
                                                and not passthrough_saw_tool_calls
                                                and _zombie_keyretry_left > 0
                                            )
                                            if _can_zr_ps and not (_zombie_keyretry_budget_deadline
                                                                    and time.time() > _zombie_keyretry_budget_deadline):
                                                _zombie_keyretry_left -= 1
                                                if _zombie_keyretry_next_k < 0:
                                                    _orig_k = metrics.get("nv_key_idx", -1)
                                                    _zombie_keyretry_next_k = (
                                                        ((_orig_k + 1) % NVU_NUM_KEYS) if _orig_k >= 0 else 0
                                                    )
                                                _zr_k = _zombie_keyretry_next_k
                                                _log("NV-ZOMBIE-KEYRETRY-TRY",
                                                     f"({request_model}) ps zombie keyretry k{_zr_k+1} "
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
                                                    # 重置流式循环状态 (passthrough 无 converter)
                                                    sse_buffer = ""
                                                    passthrough_content_chars = 0
                                                    passthrough_reasoning_chars = 0
                                                    passthrough_saw_tool_calls = False
                                                    zombie_detected = False
                                                    try:
                                                        _poll_sock = conn.sock
                                                        if _poll_sock is None and resp is not None:
                                                            _poll_sock = resp.fp.raw._sock
                                                        if _poll_sock is not None:
                                                            _poll_sock.settimeout(NVU_STREAM_POLL_S)
                                                    except Exception:
                                                        _poll_sock = None
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
                                                         f"({request_model}) ps k{_zr.nv_key_idx+1} rescued, "
                                                         f"resuming stream (req={metrics.get('request_id','?')})")
                                                    continue
                                                else:
                                                    _log("NV-ZOMBIE-KEYRETRY-FAIL",
                                                         f"({request_model}) ps k{_zr_k+1} also zombie/fail, "
                                                         f"next (req={metrics.get('request_id','?')})")
                                                    _zombie_keyretry_next_k = (_zr_k + 1) % NVU_NUM_KEYS
                                                    continue
                                            else:
                                                # 不干净 (content>0/reasoning>0/saw_tool_calls) 或 耗尽 → 保持现状
                                                zombie_detected = True
                                                metrics["error_type"] = "zombie_empty_completion"
                                                _log("NV-ZOMBIE-EMPTY",
                                                     f"({request_model}) ps zombie (no keyretry: "
                                                     f"content={passthrough_content_chars}c "
                                                     f"reasoning={passthrough_reasoning_chars}c "
                                                     f"left={_zombie_keyretry_left}), "
                                                     f"aborting to content_filter (req={metrics.get('request_id','?')})")
# 原 `if zombie_detected: break` 保留 — 只在不可重试 (zombie_detected=True) 时 break.
