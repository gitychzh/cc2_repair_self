#!/usr/bin/env python3
"""Upstream request executor for NV proxy (nv_gw) — 三 agent 通用.

Reng (HM1 self-change, authorized): modularized for long-term maintainability.
NVCF connection layer → gateway/nvcf_conn.py; pexec request
construction/validation → gateway/pexec.py. This file now holds the core
tier-key loop (_try_tier_keys) and three-tier fallback orchestration
(execute_request). Logic is byte-for-byte equivalent to the pre-refactor
version.

Rproxy (HM1 self-change, authorized): per-key direct/proxy routing is driven
purely by NVU_PROXY_URL<n> env (empty=direct, non-empty=mihomo SOCKS5).
k2/k4 direct, k1/k3/k5 via mihomo on HM1. _make_nvcf_proxy_conn (in nvcf_conn.py)
handles the empty→direct branch internally, so the unified call below routes
both paths.

R38.10: deepseek bypasses DEGRADING integrate API → NVCF pexec orion (ACTIVE).
R38.8:  Connection refused fast-break + startup retry.
R38.6:  sock.settimeout BEFORE getresponse, Connection:close.

Default tier: deepseek (primary) + kimi (fallback)
If all 5 keys fail → fallback to next tier.
If all tiers also all-fail → ABORT-NO-FALLBACK.

Chain: nv_gw → NVCF pexec (deepseek/kimi only). K1/K2 direct, K3-K5 via mihomo SOCKS5 → NV API
"""
import json
import os
import http.client
import socket
import threading
import time
import datetime

from .config import (
    NVU_KEYS, NVU_NUM_KEYS, NVU_PROXY_URLS,
    NV_MODEL_IDS, NV_MODEL_TIERS, DEFAULT_NV_MODEL, detect_nv_model,
    get_tier_index,
    NVCF_PEXEC_MODELS, NVCF_BASE_URL,
    UPSTREAM_TIMEOUT, TIER_TIMEOUT_BUDGET_S, NVU_FORCE_STREAM_UPGRADE_TIMEOUT,
    _next_nv_key,
    throttle_outbound,
    is_key_cooling, mark_key_cooling, reset_key429_count, KEY_COOLDOWN_S,
    TIER_COOLDOWN_S,
    is_key_auth_failed, mark_key_auth_failed,
    _peek_nv_key,
    is_tier_degraded, mark_tier_degraded,
    NV_INTEGRATE_ENABLED, NV_INTEGRATE_HOST, NV_INTEGRATE_PATH,
    NV_INTEGRATE_KEY_COOLDOWN_S, NV_INTEGRATE_PATH_COOLDOWN_S, NV_INTEGRATE_MODELS,
    NV_INTEGRATE_PROXY_URLS,
    NV_KEY_INTEGRATE_PROXY_URLS, NV_KEY_INTEGRATE_EGRESS_IPS,
    nv_key_integrate_keys_for,
    egress_info_for_integrate_key,
    egress_info_for_key,
    NV_INTEGRATE_EGRESS_IPS,
    NV_GLM52_MODE_CHAIN, NV_GLM52_SINGLE_US_PROXY, NV_GLM52_RR_US_PROXIES,
    NVU_GLM52_EXP_BACKOFF, NVU_GLM52_EXP_BACKOFF_STEPS, NVU_GLM52_EXP_BACKOFF_CAP,  # R1928 指数退避 (R1933 补 import 修 NameError: 半成品裸名未入 import 列表, R1932 restart 显形)
    KEY_MODE_BINDING, NV_GLM52_KEY_PROXY_MAP,
    glm52_current_mode_idx, glm52_save_mode_idx, glm52_reset_mode_idx,
    # R1648c: nv→ms fallback (5key 全坏兜底, 仅 glm5_2_nv)
    NVU_MS_FALLBACK_ENABLED, NVU_MS_FALLBACK_URL, NVU_MS_FALLBACK_TOKEN,
    NVU_MS_FALLBACK_MODEL, NVU_MS_FALLBACK_TIMEOUT, NVU_MS_FALLBACK_MODELS,
)
from .logger import _log, _log_metrics, _log_error_detail
from .nvcf_conn import _make_nvcf_proxy_conn
from .pexec import _build_pexec_body, _check_empty_200
from . import func_health
from . import nv_breaker  # R1648c: nv→ms fallback circuit breaker
from . import big_input_breaker  # R1695: 超大 input 系统性 hang 快速失败 breaker


class UpstreamResult:
    """Result from NVCF pexec upstream request execution."""
    def __init__(self):
        self.success = False
        # Success fields
        self.resp = None
        self.conn = None
        self.tier_model = ""
        self.nv_key_idx = 0
        self.nv_model_label = ""
        self.is_stream = False
        # R784: per-key egress info for DB long-term IP-diversity analysis
        self.egress_route = ""
        self.egress_ip = ""
        self.key_cycle_attempts = []
        self.upstream_type = "nvcf_pexec"
        self.tier_attempts = []
        self.fallback_tiers_used = []
        # R_multi: 本次 tier 选中的 function_id (用于上层 func_health.record_result)
        self.function_id = ""
        # Error fields
        self.all_keys_exhausted = False
        self.all_429 = False
        self.empty_200 = False
        self.elapsed_ms = 0
        self.final_error_json = None
        self.final_resp_status = 0


# ─── R572: Integrate direct path (5-key 首选, pexec 降为 fallback) ──────────
# 实测 integrate.api.nvidia.com/v1/chat/completions 比 pexec 快 2-3x 且无 surge,
# 但单 key 有 ~6-12/min 的 per-key RPM 限流 (冷却 1-2min). 策略:
#   5 key 独立 rr 轮换 (不与 pexec 的 _next_nv_key 共用 counter) →
#   遇 429 标该 key 冷却 (NV_INTEGRATE_KEY_COOLDOWN_S) 立即跳下一 key →
#   全限流 → 标整条 path 冷却 (NV_INTEGRATE_PATH_COOLDOWN_S) 返回 all_keys_exhausted,
#   由 execute_request 回退到 pexec tier.
# 思考参数复用 NVCF_PEXEC_MODELS[model]["inject"] (integrate 与 pexec 74f02205 触发方式一致).
_integrate_rr_counter = 0  # 模块级独立 rr, 不持久化 (重启从 0 开始, 无害)
_integrate_rr_lock = threading.Lock()

# R858: rr_us 模式跨请求持久 RR 计数器. 修 BUG6: 旧 rr_us 用 per-request attempt_idx
# 致每请求首 attempt 永远取 pool[0]=7894, 7894 压倒性过载(实测 13:1)致 SSL 断流高发.
_glm52_rr_us_counter = 0
_glm52_rr_us_lock = threading.Lock()
_integrate_path_cooldown_until = 0.0  # 整条 integrate path 冷却截止 (全 key 429 时触发)


def _integrate_is_path_cooling():
    return time.monotonic() < _integrate_path_cooldown_until


def _integrate_mark_path_cooling(duration_s):
    global _integrate_path_cooldown_until
    _integrate_path_cooldown_until = time.monotonic() + duration_s


def _integrate_tier_name(tier_model):
    """虚拟 tier 名, 隔离 cooldown 状态 (不与 pexec 同 model 的 cooldown 混)."""
    return f"{tier_model}_integrate"


def _try_integrate_keys(oai_body, tier_model, request_id, metrics, t_start,
                        is_stream, prior_cycle_attempts, upstream_timeout_override=None,
                        key_filter=None):
    """Try all 5 keys via integrate.api.nvidia.com direct path, starting from independent RR.

    镜像 _try_tier_keys 结构但走 integrate /v1/chat/completions 路径.
    - 成功 (200 非空): 返回 success
    - 429: 标该 key 冷却 (NV_INTEGRATE_KEY_COOLDOWN_S), 立即跳下一 key
    - 连接错误/timeout: 跳下一 key (不 fast-break, integrate 偶发抖动)
    - 全 key 失败: 返回 all_keys_exhausted, 由 execute_request 回退 pexec
    """
    global _integrate_rr_counter
    result = UpstreamResult()
    result.is_stream = is_stream
    result.tier_model = tier_model
    result.upstream_type = "nv_integrate"
    result.function_id = "integrate"  # func_health 不追踪 integrate (无 function id)
    key_cycle_attempts = list(prior_cycle_attempts)

    nv_model_id = NV_MODEL_IDS[tier_model]
    nvcf_config = NVCF_PEXEC_MODELS[tier_model]
    integ_tier = _integrate_tier_name(tier_model)

    # 复用 _build_pexec_body: 它做 strip_params + inject (thinking:{type:enabled} 等),
    # integrate 路径接受同样的 body 格式 (已实测 200 + rc 非空).
    integ_body = _build_pexec_body(oai_body, tier_model, nvcf_config)
    integ_data = json.dumps(integ_body).encode("utf-8")

    # R838: per-key 跨链路. key_filter 指定只试这些 key(如 [4]=K5), 不做全 5 key 轮转.
    # 无 key_filter → 沿用全 key RR (NV_INTEGRATE_MODELS per-model 行为).
    if key_filter is not None:
        _iter_keys = [k for k in key_filter if 0 <= k < NVU_NUM_KEYS]
        start_key_idx = _iter_keys[0] if _iter_keys else 0
        _log("NV-INTEGRATE", f"Starting integrate tier={tier_model} model={nv_model_id} "
                             f"key_filter={[k+1 for k in _iter_keys]} path={NV_INTEGRATE_PATH}")
    else:
        with _integrate_rr_lock:
            start_key_idx = _integrate_rr_counter % NVU_NUM_KEYS
            _integrate_rr_counter += 1
        _log("NV-INTEGRATE", f"Starting integrate tier={tier_model} model={nv_model_id} "
                             f"start_key=k{start_key_idx+1} path={NV_INTEGRATE_PATH}")

    CONNECT_RESERVE_S = float(os.environ.get("NVU_CONNECT_RESERVE_S", "5"))
    MIN_ATTEMPT_TIMEOUT = 5
    consecutive_pexec_timeout = 0
    consecutive_empty_200 = 0  # R577: 连续 empty_200 计数, 触达阈值则 break
    PEXEC_TIMEOUT_FASTBREAK = int(os.environ.get('NVU_PEXEC_TIMEOUT_FASTBREAK', '3'))
    EMPTY_200_FASTBREAK = int(os.environ.get("NVU_EMPTY_200_FASTBREAK", "1"))

    tier_budget_start = time.time()

    # R814: tier-level DEGRADED short-circuit (same as pexec path).
    if is_tier_degraded(tier_model):
        _log("NV-INTEGRATE-TIER-DEGRADED-SKIP", f"tier={tier_model} in DEGRADED cooldown, short-circuit → tier fail")
        result.all_keys_exhausted = True
        result.final_error_json = {"error": {"type": "nvcf_tier_degraded", "message": f"NVCF function for tier {tier_model} is DEGRADED (short-circuited)"}}
        result.final_resp_status = 400
        result.key_cycle_attempts = key_cycle_attempts
        result.elapsed_ms = int((time.time() - t_start) * 1000)
        return result
    _filter_keys = [k for k in (key_filter if key_filter is not None else []) if 0 <= k < NVU_NUM_KEYS]
    _n_iter = len(_filter_keys) if _filter_keys else (NVU_NUM_KEYS + 2)
    for attempt_idx in range(_n_iter):
        key_idx = (_filter_keys[attempt_idx] if _filter_keys
                   else (start_key_idx + attempt_idx) % NVU_NUM_KEYS)
        t_attempt_start = time.time()

        elapsed_in_tier = time.time() - tier_budget_start
        if elapsed_in_tier >= TIER_TIMEOUT_BUDGET_S:
            _log("NV-INTEGRATE-BUDGET", f"tier={tier_model} budget {TIER_TIMEOUT_BUDGET_S}s "
                                        f"exceeded after {elapsed_in_tier:.1f}s, breaking")
            break

        remaining_budget = TIER_TIMEOUT_BUDGET_S - elapsed_in_tier
        if remaining_budget < MIN_ATTEMPT_TIMEOUT:
            break
        per_attempt_timeout = max(MIN_ATTEMPT_TIMEOUT,
                                  min(upstream_timeout_override if upstream_timeout_override else UPSTREAM_TIMEOUT,
                                      remaining_budget - CONNECT_RESERVE_S))

        # 跳过冷却中的 key (per-key 429 冷却)
        # R764: skip if cooling (429) OR auth-failed (cross-tier per-key)
        if is_key_cooling(integ_tier, key_idx) or is_key_auth_failed(key_idx):
            _log("NV-INTEGRATE", f"tier={tier_model} k{key_idx+1} cooling/auth-failed, skipping")
            if attempt_idx >= NVU_NUM_KEYS and all(is_key_cooling(integ_tier, k) or is_key_auth_failed(k) for k in range(NVU_NUM_KEYS)):
                _log("NV-INTEGRATE", f"tier={tier_model} all integrate keys in cooldown/auth-failed, breaking")
                break
            continue

        if NVU_NUM_KEYS == 0 or key_idx >= len(NVU_KEYS):
            continue

        nv_key = NVU_KEYS[key_idx]
        # R827: integrate 走专用美国代理(per-key轮换, 地理限制), 不复用 pexec 的 NVU_PROXY_URLS.
        # R838: key_filter 模式优先用 NV_KEY_INTEGRATE_PROXY_URLS (对齐 key_filter 顺序),
        #       否则按 key_idx 轮换 NV_INTEGRATE_PROXY_URLS, 再否则回退 pexec 的 NVU_PROXY_URLS.
        if key_filter is not None and NV_KEY_INTEGRATE_PROXY_URLS:
            _ki_in_filter = _filter_keys.index(key_idx) if key_idx in _filter_keys else 0
            proxy_url = (NV_KEY_INTEGRATE_PROXY_URLS[_ki_in_filter]
                        if _ki_in_filter < len(NV_KEY_INTEGRATE_PROXY_URLS)
                        else (NV_INTEGRATE_PROXY_URLS[key_idx % len(NV_INTEGRATE_PROXY_URLS)] if NV_INTEGRATE_PROXY_URLS else ""))
        elif NV_INTEGRATE_PROXY_URLS:
            proxy_url = NV_INTEGRATE_PROXY_URLS[key_idx % len(NV_INTEGRATE_PROXY_URLS)]
        else:
            proxy_url = NVU_PROXY_URLS[key_idx] if key_idx < len(NVU_PROXY_URLS) else ""
        is_direct = (not proxy_url) or (proxy_url.strip() == "")

        # throttle: 第一次出站前节流 (复用全局 throttle, 分摊 per-key 压力)
        if attempt_idx == 0:
            throttle_outbound()

        _log("NV-INTEGRATE", f"tier={tier_model} attempt {attempt_idx+1}/{NVU_NUM_KEYS + 2}: "
                             f"k{key_idx+1} → integrate {nv_model_id} {'DIRECT' if is_direct else 'via ' + proxy_url}")

        # 复用 R295 header camouflage (与 pexec 一致, 风格统一)
        hdr_extra = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "application/json, text/plain, */*",
            "X-Requested-With": "XMLHttpRequest",
            "Origin": "https://build.nvidia.com",
            "Referer": "https://build.nvidia.com/explore/discover",
        }
        headers_out = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {nv_key}",
            "Content-Length": str(len(integ_data)),
            "Connection": "close",
            **hdr_extra,
        }

        try:
            t_connect_start = time.time()
            conn = _make_nvcf_proxy_conn(proxy_url, nvcf_host=NV_INTEGRATE_HOST, timeout=per_attempt_timeout)
            connect_elapsed = time.time() - t_connect_start
            post_connect_remaining = TIER_TIMEOUT_BUDGET_S - (time.time() - tier_budget_start)
            if post_connect_remaining < MIN_ATTEMPT_TIMEOUT:
                _log("NV-INTEGRATE-BUDGET", f"tier={tier_model} k{key_idx+1} after connect "
                                            f"({connect_elapsed:.1f}s) remaining {post_connect_remaining:.1f}s, aborting")
                try: conn.close()
                except Exception: pass
                break
            read_timeout = min(per_attempt_timeout, post_connect_remaining)
            conn.request("POST", NV_INTEGRATE_PATH, body=integ_data, headers=headers_out)
            if conn.sock:
                conn.sock.settimeout(read_timeout)
            resp = conn.getresponse()

            if resp.status >= 400:
                error_body = resp.read()
                try: error_json = json.loads(error_body)
                except Exception: error_json = {"error": error_body.decode("utf-8", errors="replace")}
                conn.close()
                err_str = json.dumps(error_json)

                # R762: 401/403 (per-key auth failed) → cycle next key (同 pexec 修复).
                should_cycle = resp.status in (401, 403, 429, 408, 500, 502, 503, 504, 202)
                if should_cycle:
                    cycle_reason = ("401_integrate_auth_failed" if resp.status == 401 else
                                    "403_integrate_auth_failed" if resp.status == 403 else
                                    "429_integrate_rate_limit" if resp.status == 429 else
                                    "408_integrate_timeout" if resp.status == 408 else
                                    "500_integrate_error" if resp.status == 500 else
                                    "502_integrate_error" if resp.status == 502 else
                                    "503_integrate_error" if resp.status == 503 else
                                    "504_integrate_gateway_timeout" if resp.status == 504 else "202_integrate_async_hang")
                    key_cycle_attempts.append({
                        "tier": tier_model,
                        "nv_key_idx": key_idx,
                        "litellm_model": f"integrate_{nv_model_id}_k{key_idx+1}",
                        "error_body": err_str[:500],
                        "error_type": cycle_reason,
                        "upstream_type": "nv_integrate",
                        "function_id": "integrate",
                    })
                    if resp.status in (401, 403):
                        # R764: auth-fail 是 per-key (跨 tier), 用 mark_key_auth_failed 全 tier 跳过.
                        mark_key_cooling(integ_tier, key_idx, duration_s=NV_INTEGRATE_KEY_COOLDOWN_S)
                        mark_key_auth_failed(key_idx)
                        _log("NV-INTEGRATE-AUTH-FAIL", f"tier={tier_model} k{key_idx+1} {resp.status} auth failed, "
                               f"marked cooling + auth-fail (cross-tier), cycling")
                    elif resp.status == 429:
                        mark_key_cooling(integ_tier, key_idx, duration_s=NV_INTEGRATE_KEY_COOLDOWN_S)
                        _log("NV-INTEGRATE-COOLDOWN", f"tier={tier_model} k{key_idx+1} marked cooling {NV_INTEGRATE_KEY_COOLDOWN_S}s after 429")
                    _log("NV-INTEGRATE-CYCLE", f"tier={tier_model} k{key_idx+1} → {resp.status} ({cycle_reason}), cycling")
                    consecutive_pexec_timeout = 0
                    continue

                # Non-cycling error → report (与 pexec 一致, R762 加日志)
                _log("NV-INTEGRATE-NONCYCLE-ERR", f"tier={tier_model} k{key_idx+1} resp.status={resp.status} "
                      f"non-cycling, aborting tier. body={err_str[:200]}")
                # R814: same DEGRADED tier-level short-circuit as pexec path.
                if resp.status == 400 and "DEGRADED" in err_str.upper():
                    _cd = mark_tier_degraded(tier_model)
                    _log("NV-INTEGRATE-TIER-DEGRADED", f"tier={tier_model} marked DEGRADED cooldown {_cd:.0f}s")
                result.final_error_json = error_json
                result.final_resp_status = resp.status
                result.key_cycle_attempts = key_cycle_attempts
                result.elapsed_ms = int((time.time() - t_start) * 1000)
                return result

            # 200 — check empty
            is_empty = _check_empty_200(resp, key_idx, tier_model, is_stream)
            if is_empty:
                key_cycle_attempts.append({
                    "tier": tier_model,
                    "nv_key_idx": key_idx,
                    "litellm_model": f"integrate_{nv_model_id}_k{key_idx+1}",
                    "error_type": "empty_200",
                    "upstream_type": "nv_integrate",
                    "function_id": "integrate",
                })
                # R824: 同 pexec 路径, empty200 标该 key 冷却. NV_INTEGRATE_KEY_COOLDOWN_S=0 时等于不冷却(env 配置).
                mark_key_cooling(integ_tier, key_idx, duration_s=NV_INTEGRATE_KEY_COOLDOWN_S)
                _log("NV-INTEGRATE-EMPTY", f"tier={tier_model} k{key_idx+1} empty 200, marked cooling {NV_INTEGRATE_KEY_COOLDOWN_S}s, cycling")
                # R577: EMPTY_200_FASTBREAK 语义从 boolean 改为连续次数阈值.
                #   0 = 禁用 (全 cycle, 偶发 empty 可换 key 救回但 surge 期 143s 卡死)
                #   1 = 每次 empty 都 break (激进, 丢失偶发救回)
                #   N≥2 = 连续 N 次 empty 才 break (平衡: 偶发 1-2 次仍 cycle 救回, surge N+ 次快速 break)
                consecutive_empty_200 += 1
                if EMPTY_200_FASTBREAK > 0 and consecutive_empty_200 >= EMPTY_200_FASTBREAK:
                    _log("NV-INTEGRATE-EMPTY-FASTBREAK", f"tier={tier_model} {consecutive_empty_200} consecutive empty_200 ≥ threshold {EMPTY_200_FASTBREAK}, fast-break")
                    break
                consecutive_pexec_timeout = 0
                try: conn.close()
                except Exception: pass
                continue

            # Valid success
            consecutive_pexec_timeout = 0
            consecutive_empty_200 = 0  # R577: 成功重置连续 empty 计数
            result.success = True
            result.resp = resp
            result.conn = conn
            result.tier_model = tier_model
            result.nv_key_idx = key_idx
            # R838: 用实际请求的 proxy_url 算 egress (key_filter 模式下可能是 NV_KEY_INTEGRATE_PROXY_URLS, 非 key_idx 轮换).
            _eg_port = proxy_url.strip().rsplit(":", 1)[-1] if proxy_url and ":" in proxy_url else "direct"
            result.egress_route = f"integrate-mihomo-{_eg_port}" if not is_direct else "integrate-direct"
            # egress IP: key_filter 模式优先 NV_KEY_INTEGRATE_EGRESS_IPS, 否则 egress_info_for_integrate_key.
            if key_filter is not None and NV_KEY_INTEGRATE_EGRESS_IPS and key_idx in _filter_keys:
                _fi = _filter_keys.index(key_idx)
                result.egress_ip = NV_KEY_INTEGRATE_EGRESS_IPS[_fi] if _fi < len(NV_KEY_INTEGRATE_EGRESS_IPS) else ""
            else:
                _, result.egress_ip = egress_info_for_integrate_key(key_idx)
            result.nv_model_label = f"integrate_{nv_model_id}_k{key_idx+1}"
            result.key_cycle_attempts = key_cycle_attempts
            result.fallback_tiers_used = [tier_model]
            result.upstream_type = "nv_integrate"
            reset_key429_count(integ_tier, key_idx)
            metrics["upstream_type"] = "nv_integrate"
            metrics["tier_model"] = tier_model
            metrics["nv_key_idx"] = key_idx
            metrics["litellm_model"] = result.nv_model_label
            if key_cycle_attempts:
                metrics["key_cycle_429s_before_success"] = len(key_cycle_attempts)
                _log("NV-INTEGRATE-SUCCESS", f"tier={tier_model} k{key_idx+1} succeeded after "
                                              f"{len(key_cycle_attempts)} cycle attempts")
            else:
                _log("NV-INTEGRATE-SUCCESS", f"tier={tier_model} k{key_idx+1} succeeded on first attempt")
            return result

        except socket.timeout as e:
            attempt_elapsed_ms = int((time.time() - t_attempt_start) * 1000)
            _log("NV-INTEGRATE-TIMEOUT", f"tier={tier_model} k{key_idx+1} integrate timeout: "
                                          f"attempt={attempt_elapsed_ms}ms")
            key_cycle_attempts.append({
                "tier": tier_model,
                "nv_key_idx": key_idx,
                "litellm_model": f"integrate_{nv_model_id}_k{key_idx+1}",
                "error_type": "IntegrateTimeout",
                "elapsed_ms": attempt_elapsed_ms,
                "upstream_type": "nv_integrate",
                "function_id": "integrate",
            })
            consecutive_pexec_timeout += 1
            if consecutive_pexec_timeout >= PEXEC_TIMEOUT_FASTBREAK:
                _log("NV-INTEGRATE-FASTBREAK", f"tier={tier_model} {consecutive_pexec_timeout} "
                                               f"consecutive timeouts -> fast-break")
                break
            continue

        except (ConnectionRefusedError, http.client.RemoteDisconnected) as e:
            attempt_elapsed_ms = int((time.time() - t_attempt_start) * 1000)
            _log("NV-INTEGRATE-CONN", f"tier={tier_model} k{key_idx+1} connection error: {e}")
            key_cycle_attempts.append({
                "tier": tier_model,
                "nv_key_idx": key_idx,
                "litellm_model": f"integrate_{nv_model_id}_k{key_idx+1}",
                "error_type": f"Integrate{type(e).__name__}",
                "elapsed_ms": attempt_elapsed_ms,
                "upstream_type": "nv_integrate",
                "function_id": "integrate",
            })
            continue

        except Exception as e:
            error_class = type(e).__name__
            elapsed_ms = int((time.time() - t_attempt_start) * 1000)
            _log("NV-INTEGRATE-ERR", f"tier={tier_model} k{key_idx+1} {error_class}: {e}")
            is_ssl_err = (error_class == "SSLEOFError" or error_class == "SSLError" or
                          error_class == "SSLZeroReturnError")
            if is_ssl_err:
                _log("NV-INTEGRATE-SSL-CYCLE", f"tier={tier_model} k{key_idx+1} SSL error ({elapsed_ms}ms) — cycle")
                continue
            key_cycle_attempts.append({
                "tier": tier_model,
                "nv_key_idx": key_idx,
                "litellm_model": f"integrate_{nv_model_id}_k{key_idx+1}",
                "error": str(e)[:200],
                "error_type": f"Integrate{error_class}",
                "elapsed_ms": elapsed_ms,
                "upstream_type": "nv_integrate",
                "function_id": "integrate",
            })
            continue

    # ─── All integrate keys exhausted ───
    tier_attempts = [a for a in key_cycle_attempts if a.get("tier") == tier_model]
    all_429 = all(a.get("error_type") == "429_integrate_rate_limit" for a in tier_attempts) if tier_attempts else False

    result.all_keys_exhausted = True
    result.all_429 = all_429
    result.empty_200 = False
    result.key_cycle_attempts = key_cycle_attempts
    result.elapsed_ms = int((time.time() - t_start) * 1000)

    fail_summary = (f"429={sum(1 for a in tier_attempts if a.get('error_type')=='429_integrate_rate_limit')}, "
                    f"empty200={sum(1 for a in tier_attempts if a.get('error_type')=='empty_200')}, "
                    f"timeout={sum(1 for a in tier_attempts if 'Timeout' in a.get('error_type',''))}, "
                    f"other={sum(1 for a in tier_attempts if a.get('error_type') not in ('429_integrate_rate_limit','empty_200') and 'Timeout' not in a.get('error_type',''))}")
    _log("NV-INTEGRATE-FAIL", f"tier={tier_model} all integrate keys failed: {fail_summary}, "
                               f"elapsed={result.elapsed_ms}ms")

    # 全 key 429 → 标整条 integrate path 冷却, 强制走 pexec
    if all_429:
        _integrate_mark_path_cooling(NV_INTEGRATE_PATH_COOLDOWN_S)
        _log("NV-INTEGRATE-PATH-COOLDOWN", f"tier={tier_model} all integrate keys 429. "
                                            f"Marking integrate path cooling {NV_INTEGRATE_PATH_COOLDOWN_S}s")

    _log_error_detail({
        "request_id": request_id,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00"),
        "error_subcategory": f"integrate_{tier_model}_all_keys_failed",
        "tier_model": tier_model,
        "tier_attempts": tier_attempts,
        "all_429": all_429,
        "elapsed_ms": result.elapsed_ms,
    })

    return result


# ─── R2224: peek 内部换 key 重试包装 (撤 40007 第一步) ─────────────────
# R1716 peek barrier 软挂时 (首字节超时/零内容/空流), 旧逻辑直接切外部 ms_gw.
# 本函数: 不污染 RR counter, 显式指定 start_key, 只试 1 个 key, 返回 UpstreamResult.
# 调用方 (handlers._stream_openai_to_anth peek 软挂分支) 拿到 resp/conn 后需对新流
# 重新跑 peek barrier 确认健康才 commit message_start (ChatGPT: commit-point 边界).
# 与 execute_request 的全量 5-key 轮转隔离 (ChatGPT: 独立 peek-retry 小循环, 不进全量轮转).
def _peek_retry_next_key(oai_body, tier_model, request_id, metrics, t_start,
                         is_stream, prior_cycle_attempts, start_key_idx,
                         upstream_timeout_override=None):
    """Try ONE specific NVCF key (no RR advance) for peek-retry. Returns UpstreamResult."""
    return _try_tier_keys(oai_body, tier_model, request_id, metrics, t_start,
                         is_stream, prior_cycle_attempts,
                         upstream_timeout_override=upstream_timeout_override,
                         start_key_idx_override=start_key_idx,
                         max_attempts_override=1)


def _try_tier_keys(oai_body, tier_model, request_id, metrics, t_start,
                   is_stream, prior_cycle_attempts, upstream_timeout_override=None,
                   start_key_idx_override=None, max_attempts_override=None):
    """Try all 5 keys within one tier via NVCF pexec, starting from current RR position.

    R38.12: ALL models use NVCF pexec. No LiteLLM branch.
    On 429/500/502: cycle to next key within same tier.
    On empty 200: cycle to next key within same tier.
    On other error: report immediately (no cycling).
    Connection refused fast-break: 2+ consecutive → break to next tier.
    Tier timeout budget: stop if cumulative time exceeds budget.

    Returns: UpstreamResult
    """
    result = UpstreamResult()
    result.is_stream = is_stream
    result.tier_model = tier_model
    # R_multi: 记录本次选中的 function_id, 供上层 func_health.record_result 使用
    result.function_id = ""
    key_cycle_attempts = list(prior_cycle_attempts)


    nv_model_id = NV_MODEL_IDS[tier_model]
    nvcf_config = NVCF_PEXEC_MODELS[tier_model]
    nvcf_host = NVCF_BASE_URL
    # R_multi: 从候选列表 function_ids 中按健康度选首选. surge 中的 function 自动跳过.
    _candidates = nvcf_config.get("function_ids") or [nvcf_config.get("function_id")]
    function_id = func_health.select_healthy_function(tier_model, _candidates)
    result.function_id = function_id
    nvcf_path = f"/v2/nvcf/pexec/functions/{function_id}"

    _log("NV-TIER", f"Starting tier={tier_model} model={nv_model_id} "
                    f"func={function_id[:12]}... (position from rr_counter)")

    # Build request body with per-model param stripping
    pexec_body = _build_pexec_body(oai_body, tier_model, nvcf_config)

    # Get starting key from per-tier persistent counter
    # R2224: peek-retry 传入 start_key_idx_override 时用它 (不 advance RR counter,
    # 避免 peek 软挂换 key 污染全局轮转). 否则走原 _next_nv_key advance 逻辑.
    if start_key_idx_override is not None:
        start_key_idx = start_key_idx_override % NVU_NUM_KEYS
        _log("NV-PEEK-RETRY", f"tier={tier_model} peek-retry: explicit start_key=k{start_key_idx+1} "
                             f"(no RR advance, override)")
    else:
        start_key_idx = _next_nv_key(tier_model)

    # R797: per-tier budget override. NVCF ai-glm-5_2 (3b9748d8) DEGRADING — 全 key
    # 直连 504/400 ~62s, 全局 TIER_TIMEOUT_BUDGET_S=180 让 glm5_2_nv 烧满 3 key 才 fail,
    # 把 cc4101/cx4102/opclaw4103 卡死 ~180s. 给 glm5_2_nv 短 budget (env, 默认 70s) 让它
    # 1-2 key 后即 all_tiers_exhausted → agent 尽快落 ms_gw. dsv4p_nv/kimi_nv 不受影响
    # (无 env 覆盖 → 用全局 TIER_TIMEOUT_BUDGET_S). NVCF 恢复后删 env 即回滚.
    _tier_budget_env = os.environ.get(f"NVU_TIER_BUDGET_{tier_model.upper()}")
    tier_budget_s = float(_tier_budget_env) if _tier_budget_env else TIER_TIMEOUT_BUDGET_S

    tier_budget_start = time.time()
    consecutive_conn_err = 0
    CONN_ERR_FAST_BREAK = 2
    # R347 (HM1-C): consecutive NVCFPexecTimeout fast-fail. After N consecutive pexec
    # timeouts in the same tier, break early instead of cycling remaining keys — saves
    # ~30-50s on doomed ATE requests. Default N=3 (per CC directive: front-3 keys all
    # NVCFPexecTimeout). Env-tunable for rollback. Rescue cases (k4/k5 save after 3+ timeouts)
    # are rare (2/231=0.87% in R347 baseline) — accepted per stability>success tradeoff eval.
    consecutive_pexec_timeout = 0
    PEXEC_TIMEOUT_FASTBREAK = int(os.environ.get('NVU_PEXEC_TIMEOUT_FASTBREAK', '3'))

    EMPTY_200_FASTBREAK = int(os.environ.get("NVU_EMPTY_200_FASTBREAK", "1"))
    consecutive_empty_200 = 0  # R577: 连续 empty_200 计数 (同 _try_integrate_keys)
    # R814: tier-level DEGRADED short-circuit. If NVCF function for this tier recently
    # returned 400 DEGRADED (all keys will 400), skip the whole key loop and return fail
    # immediately so the caller falls back to ms_gw instead of burning 0.6-1s/request
    # re-probing a known-dead NVCF function (data: glm5_2_nv 14/14 502 DEGRADED/60min).
    if is_tier_degraded(tier_model):
        _log("NV-TIER-DEGRADED-SKIP", f"tier={tier_model} in DEGRADED cooldown, short-circuit (skip key loop) → tier fail")
        result.all_keys_exhausted = True
        result.final_error_json = {"error": {"type": "nvcf_tier_degraded", "message": f"NVCF function for tier {tier_model} is DEGRADED (short-circuited)"}}
        result.final_resp_status = 400
        result.key_cycle_attempts = key_cycle_attempts
        result.elapsed_ms = int((time.time() - t_start) * 1000)
        return result
    _max_attempts = max_attempts_override if max_attempts_override is not None else (NVU_NUM_KEYS + 2)
    for attempt_idx in range(_max_attempts):
        key_idx = (start_key_idx + attempt_idx) % NVU_NUM_KEYS
        t_attempt_start = time.time()  # R38.14: per-attempt start time for accurate logging

        # Tier timeout budget check (before each attempt)
        elapsed_in_tier = time.time() - tier_budget_start
        if elapsed_in_tier >= tier_budget_s:
            _log("NV-TIER-BUDGET", f"tier={tier_model} budget {tier_budget_s}s "
                                    f"exceeded after {elapsed_in_tier:.1f}s, breaking")
            break

        # R38.14: per-attempt timeout respects remaining budget
        # R40 A2: reserve CONNECT_RESERVE_S for SOCKS5 connect+SSL handshake (2-5s observed).
        #   Pre-R40 bug: per_attempt_timeout = min(45, remaining) ignored connect time, so
        #   attempt 1 spent 45s(read)+3s(connect)=48s but budget thought only 45s elapsed;
        #   attempt 2 then got remaining=15s, spent 3s(connect)+15s(read)=18s → total 66s,
        #   ~74s with throttle/overhead, blowing past the 60s budget and showing as 74.2s
        #   in the 502 error. Reserve keeps the read timeout within true remaining budget.
        CONNECT_RESERVE_S = float(os.environ.get("NVU_CONNECT_RESERVE_S", "5"))
        remaining_budget = tier_budget_s - elapsed_in_tier
        MIN_ATTEMPT_TIMEOUT = 5  # R45: 10→5 — 10s 下限在 budget 被前次 timeout 吃掉后误杀后续 key (NVCF 实测 p50=3s); 5s 仍保留 dooming-attempt 保护 # Don't attempt if less than 10s budget remains (doomed attempt)
        if remaining_budget < MIN_ATTEMPT_TIMEOUT:
            _log("NV-TIER-BUDGET", f"tier={tier_model} budget {tier_budget_s}s "
                                    f"remaining {remaining_budget:.1f}s < {MIN_ATTEMPT_TIMEOUT}s minimum, breaking")
            break
        # Read timeout = min(UPSTREAM_TIMEOUT, remaining - CONNECT_RESERVE) so connect+read together stay in budget
        per_attempt_timeout = max(MIN_ATTEMPT_TIMEOUT,
                                  min(upstream_timeout_override if upstream_timeout_override else UPSTREAM_TIMEOUT, remaining_budget - CONNECT_RESERVE_S))

        # Skip keys in 429 cooldown OR auth-failed (R764: per-key cross-tier)
        if is_key_cooling(tier_model, key_idx) or is_key_auth_failed(key_idx):
            _log("NV-KEY", f"tier={tier_model} k{key_idx+1} is in cooldown/auth-failed, skipping")
            if attempt_idx >= NVU_NUM_KEYS and all(is_key_cooling(tier_model, k) or is_key_auth_failed(k) for k in range(NVU_NUM_KEYS)):
                _log("NV-TIER", f"tier={tier_model} all keys in cooldown/auth-failed, breaking")
                break
            continue

        # ─── NVCF pexec request ───
        if NVU_NUM_KEYS == 0 or key_idx >= len(NVU_KEYS):
            _log("NV-PEXEC-ERR", f"tier={tier_model} k{key_idx+1} no NV key/proxy configured")
            key_cycle_attempts.append({
                "tier": tier_model,
                "nv_key_idx": key_idx,
                "error_type": "nvcf_pexec_no_key",
                "upstream_type": "nvcf_pexec",
                "function_id": function_id,
            })
            continue

        nv_key = NVU_KEYS[key_idx]
        # ─ Rproxy: per-key proxy strategy driven by NVU_PROXY_URL<n> env ─
        # empty proxy_url → DIRECT (k2/k4 on HM1); non-empty → mihomo SOCKS5 (k1/k3/k5).
        # _make_nvcf_proxy_conn handles the empty→direct branch internally.
        proxy_url = NVU_PROXY_URLS[key_idx] if key_idx < len(NVU_PROXY_URLS) else ""
        is_direct = (not proxy_url) or (proxy_url.strip() == "")

        # Build per-attempt request (model field already set in pexec_body)
        pexec_data = json.dumps(pexec_body).encode("utf-8")

        _log("NV-KEY", f"tier={tier_model} attempt {attempt_idx+1}/{NVU_NUM_KEYS + 2}: "
                       f"k{key_idx+1} → NVCF pexec {function_id[:12]}... {'DIRECT' if is_direct else 'via ' + proxy_url}")

        # R295-port (HM1 self-change, authorized): HTTP header camouflage for NVCF
        # fingerprint bypass. Ported from HM2 R295. HM2 applies it to key_idx in (0,4)
        # (k1/k5, which are the mihomo-proxied keys on HM2). On HM1 the user elected to
        # apply camouflage to ALL keys (k1-k5) for maximum disguise — so this is
        # unconditional, no key_idx guard. Mirrors HM2's exact 6 headers:
        # User-Agent (browser), Origin/Referer (build.nvidia.com source),
        # X-Requested-With, Accept-Language, Accept.
        hdr_extra = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "application/json, text/plain, */*",
            "X-Requested-With": "XMLHttpRequest",
            "Origin": "https://build.nvidia.com",
            "Referer": "https://build.nvidia.com/explore/discover",
        }
        headers_out = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {nv_key}",
            "Content-Length": str(len(pexec_data)),
            "Connection": "close",
            **hdr_extra,
        }

        try:
            # Throttle before making connection (SOCKS5 connect is a real outbound)
            if attempt_idx == 0:
                throttle_outbound()
            t_connect_start = time.time()
            # Rproxy: _make_nvcf_proxy_conn routes DIRECT when proxy_url empty, else mihomo.
            conn = _make_nvcf_proxy_conn(proxy_url, nvcf_host=nvcf_host, timeout=per_attempt_timeout)
            connect_elapsed = time.time() - t_connect_start
            # R40 A2: re-check budget AFTER connect — connect time wasn't counted when
            # computing per_attempt_timeout above, so a slow connect may have eaten the budget.
            post_connect_remaining = tier_budget_s - (time.time() - tier_budget_start)
            if post_connect_remaining < MIN_ATTEMPT_TIMEOUT:
                _log("NV-TIER-BUDGET", f"tier={tier_model} k{key_idx+1} after connect "
                                        f"({connect_elapsed:.1f}s) remaining {post_connect_remaining:.1f}s "
                                        f"< {MIN_ATTEMPT_TIMEOUT}s, aborting attempt")
                try:
                    conn.close()
                except Exception:
                    pass
                key_cycle_attempts.append({
                    "tier": tier_model,
                    "nv_key_idx": key_idx,
                    "litellm_model": f"nvcf_{NV_MODEL_IDS[tier_model]}_k{key_idx+1}",
                    "error_type": "budget_exhausted_after_connect",
                    "elapsed_ms": int(connect_elapsed * 1000),
                    "upstream_type": "nvcf_pexec",
                    "function_id": function_id,
                })
                break
            # Read timeout = whatever remains in the budget, capped by per_attempt_timeout
            read_timeout = min(per_attempt_timeout, post_connect_remaining)
            conn.request("POST", nvcf_path, body=pexec_data, headers=headers_out)
            # R38.6 CRITICAL FIX: sock.settimeout() BEFORE getresponse()
            # R40 A2: use read_timeout (post-connect remaining) instead of per_attempt_timeout
            if conn.sock:
                conn.sock.settimeout(read_timeout)
            resp = conn.getresponse()

            if resp.status >= 400:
                error_body = resp.read()
                try:
                    error_json = json.loads(error_body)
                except Exception:
                    error_json = {"error": error_body.decode("utf-8", errors="replace")}
                conn.close()
                err_str = json.dumps(error_json)

                consecutive_conn_err = 0

                # R762: 401/403 (per-key auth failed) → cycle next key (NOT abort).
                #   根因: k3 NVAPI key 失效返回 403 Forbidden, 命中 Non-cycling 分支直接 return,
                #   放弃整 request, 不 cycle k4/k5 (它们 200 OK). 1 key 失效=整 502, peer-fb 兜底.
                #   401/403 是 per-key 授权问题, 不是 request 问题, 应 cycle 到下一 key.
                #   标 KEY_COOLDOWN_S 避免反复试失效 key (浪费 ~1s/次).
                should_cycle = resp.status in (401, 403, 429, 408, 500, 502, 503, 504, 202)
                if should_cycle:
                    cycle_reason = "401_nv_auth_failed" if resp.status == 401 else \
                                   "403_nv_auth_failed" if resp.status == 403 else \
                                   "429_nv_rate_limit" if resp.status == 429 else \
                                   "408_nvcf_timeout" if resp.status == 408 else \
                                   "500_nv_error" if resp.status == 500 else \
                                   "502_nv_error" if resp.status == 502 else \
                                   "503_nv_error" if resp.status == 503 else \
                                   "504_nv_gateway_timeout" if resp.status == 504 else "202_nv_async_hang"
                    key_cycle_attempts.append({
                        "tier": tier_model,
                        "nv_key_idx": key_idx,
                        "litellm_model": f"nvcf_{NV_MODEL_IDS[tier_model]}_k{key_idx+1}",
                        "error_body": err_str[:500],
                        "error_type": cycle_reason,
                        "upstream_type": "nvcf_pexec",
                        "function_id": function_id,
                    })
                    if resp.status in (401, 403):
                        # R764: auth-fail 是 per-key (跨 tier), 用 mark_key_auth_failed 全 tier 跳过.
                        mark_key_cooling(tier_model, key_idx)
                        mark_key_auth_failed(key_idx)
                        _log("NV-AUTH-FAIL", f"tier={tier_model} k{key_idx+1} {resp.status} auth failed, "
                                              f"marked cooling + auth-fail (cross-tier), cycling to next key")
                    elif resp.status == 429:
                        mark_key_cooling(tier_model, key_idx)
                        _log("NV-COOLDOWN", f"tier={tier_model} k{key_idx+1} marked cooling after 429")
                        # R2259obs: pexec 429 响应头观测. 目的=确认 NVCF pexec 429 限流维度
                        # (按 model/account 全局, 还是按 IP). 抓 x-ratelimit-* / retry-after.
                        # ChatGPT 决策 C 步: 抓 1-2 窗口后定 B(pexec retry key_rotate) 还是 D(降级).
                        try:
                            _rh = dict(resp.headers) if resp.headers else {}
                            _rl_keys = {k: v for k, v in _rh.items() if "ratelimit" in k.lower() or "retry-after" in k.lower() or "x-ratelimit" in k.lower()}
                            _eg = egress_info_for_key(key_idx) if "egress_info_for_key" in globals() else (None, None)
                            _log("NV-PEXEC-429-HDR", f"tier={tier_model} k{key_idx+1} 429 resp headers: ratelimit/retry={_rl_keys or "(none)"} all={list(_rh.keys())[:12]} egress={_eg}")
                        except Exception as _e:
                            _log("NV-PEXEC-429-HDR", f"tier={tier_model} k{key_idx+1} header probe failed: {_e}")
                    _log("NV-CYCLE", f"tier={tier_model} k{key_idx+1} \u2192 "
                                     f"{resp.status} ({cycle_reason}), cycling to next key")
                    consecutive_pexec_timeout = 0  # R347: reset (429/500/502/401/403 != timeout)
                    continue

                # Non-cycling error → report (R762: 加日志, 避免静默失败)
                _log("NV-NONCYCLE-ERR", f"tier={tier_model} k{key_idx+1} resp.status={resp.status} "
                                          f"non-cycling, aborting tier (no key cycle). body={err_str[:200]}")
                # R814: NVCF function DEGRADED is tier-level (all keys will 400). Mark tier
                # degraded so subsequent requests short-circuit at tier entry instead of
                # re-hitting NVCF every request (data: glm5_2_nv 14/14 502 DEGRADED in 60min).
                if resp.status == 400 and "DEGRADED" in err_str.upper():
                    _cd = mark_tier_degraded(tier_model)
                    _log("NV-TIER-DEGRADED", f"tier={tier_model} marked DEGRADED cooldown {_cd:.0f}s (400 DEGRADED non-cycling)")
                result.final_error_json = error_json
                result.final_resp_status = resp.status
                result.key_cycle_attempts = key_cycle_attempts
                result.elapsed_ms = int((time.time() - t_start) * 1000)
                return result

            # ─── 200 response — check for empty ───
            is_empty = _check_empty_200(resp, key_idx, tier_model, is_stream)

            if is_empty:
                key_cycle_attempts.append({
                    "tier": tier_model,
                    "nv_key_idx": key_idx,
                    "litellm_model": f"nvcf_{NV_MODEL_IDS[tier_model]}_k{key_idx+1}",
                    "error_type": "empty_200",
                    "upstream_type": "nvcf_pexec",
                    "function_id": function_id,
                })
                # R824: empty200 标该 key 短冷却 (KEY_COOLDOWN_S=25s). 实测 k1 反复 empty200(60s空)
                # 而 k2-k5 同请求秒回, 说明是 NVCF 对该 key 的服务端降级, 不是请求问题.
                # 标冷却后 is_key_cooling 会跳过 k1, 后续请求直接从 k2 起, 不再每次撞 k1 拖 60s.
                # 25s 自动解除, NVCF 恢复后可重试. 与 429/401/403 cooldown 对称.
                mark_key_cooling(tier_model, key_idx)
                _log("NV-EMPTY-CYCLE", f"tier={tier_model} k{key_idx+1} empty 200, marked cooling {KEY_COOLDOWN_S}s, cycling")
                # R577: 同 _try_integrate_keys, EMPTY_200_FASTBREAK 语义改为连续次数阈值
                consecutive_empty_200 += 1
                if EMPTY_200_FASTBREAK > 0 and consecutive_empty_200 >= EMPTY_200_FASTBREAK:
                    _log("NV-EMPTY-FASTBREAK", f"tier={tier_model} {consecutive_empty_200} consecutive empty_200 ≥ threshold {EMPTY_200_FASTBREAK}, fast-break (saved remaining keys)")
                    break
                consecutive_pexec_timeout = 0  # R347: reset (empty_200 != timeout)
                try:
                    conn.close()
                except Exception:
                    pass
                continue

            # ─── Valid success response ───
            consecutive_conn_err = 0
            consecutive_pexec_timeout = 0  # R347: reset on success
            consecutive_empty_200 = 0  # R577: reset on success
            result.success = True
            result.resp = resp
            result.conn = conn
            result.tier_model = tier_model
            result.nv_key_idx = key_idx
            result.egress_route, result.egress_ip = egress_info_for_key(key_idx)
            result.nv_model_label = f"nvcf_{NV_MODEL_IDS[tier_model]}_k{key_idx+1}"
            result.key_cycle_attempts = key_cycle_attempts
            result.fallback_tiers_used = [tier_model]
            result.upstream_type = "nvcf_pexec"
            reset_key429_count(tier_model, key_idx)
            metrics["upstream_type"] = "nvcf_pexec"
            metrics["tier_model"] = tier_model
            metrics["nv_key_idx"] = key_idx
            metrics["litellm_model"] = result.nv_model_label
            if key_cycle_attempts:
                metrics["key_cycle_429s_before_success"] = len(key_cycle_attempts)
                metrics["key_cycle_details"] = key_cycle_attempts
                _log("NV-SUCCESS", f"tier={tier_model} k{key_idx+1} succeeded after "
                                    f"{len(key_cycle_attempts)} cycle attempts")
            else:
                _log("NV-SUCCESS", f"tier={tier_model} k{key_idx+1} succeeded on first attempt")
            return result

        except socket.timeout as e:
            # R38.14: use per-attempt elapsed, not request-level t_start
            attempt_elapsed_ms = int((time.time() - t_attempt_start) * 1000)
            total_elapsed_ms = int((time.time() - t_start) * 1000)
            _log("NV-TIMEOUT", f"tier={tier_model} k{key_idx+1} NVCF pexec timeout: "
                               f"attempt={attempt_elapsed_ms}ms total={total_elapsed_ms}ms")
            key_cycle_attempts.append({
                "tier": tier_model,
                "nv_key_idx": key_idx,
                "litellm_model": f"nvcf_{NV_MODEL_IDS[tier_model]}_k{key_idx+1}",
                "error_type": "NVCFPexecTimeout",
                "elapsed_ms": attempt_elapsed_ms,  # R38.14: per-attempt elapsed, not total
                "upstream_type": "nvcf_pexec",
                "function_id": function_id,
            })
            consecutive_pexec_timeout += 1  # R347 (HM1-C): track consecutive pexec timeouts
            if consecutive_pexec_timeout >= PEXEC_TIMEOUT_FASTBREAK:
                _log("NV-PEXEC-FASTBREAK", f"tier={tier_model} {consecutive_pexec_timeout} consecutive "
                                          f"NVCFPexecTimeout -> fast-break (saved remaining keys)")
                break
            continue

        except (ConnectionRefusedError, http.client.RemoteDisconnected) as e:
            attempt_elapsed_ms = int((time.time() - t_attempt_start) * 1000)  # R38.14
            _log("NV-CONN", f"tier={tier_model} k{key_idx+1} connection error: {e}")
            consecutive_conn_err += 1
            key_cycle_attempts.append({
                "tier": tier_model,
                "nv_key_idx": key_idx,
                "litellm_model": f"nvcf_{NV_MODEL_IDS[tier_model]}_k{key_idx+1}",
                "error_type": f"NVCFPexec{type(e).__name__}",
                "elapsed_ms": attempt_elapsed_ms,
                "upstream_type": "nvcf_pexec",
                "function_id": function_id,
            })
            if consecutive_conn_err >= CONN_ERR_FAST_BREAK:
                _log("NV-CONN-BREAK", f"tier={tier_model} {consecutive_conn_err} consecutive "
                                       f"connection errors → fast-break")
                break
            continue

        except Exception as e:
            error_class = type(e).__name__
            elapsed_ms = int((time.time() - t_attempt_start) * 1000)  # R38.14: per-attempt
            _log("NV-ERR", f"tier={tier_model} k{key_idx+1} {error_class}: {e}")

            # R1: SSLEOFError/SSLError/SSLZeroReturnError — mihomo/NVCF SSL hiccup (read-stage EOF
            # after NVCF侧 reset, 已观测单次吃 31s budget).
            # F-fix (2026-07-01, cc2 三轮仲裁): 不重试同 key, 直接 cycle 下一 key.
            #   原逻辑 sleep 3s + continue (注释"retry SAME key"实为下一 key, 注释错误).
            #   sleep 3s 纯浪费 tier budget; 同 mihomo 出口(k3/k4 都走 7896)持续 SSL error,
            #   重试同出口必败还倒贴 sleep. 切 DIRECT key(k2/k5)可能秒成功, 既省 sleep 又换出口.
            #   把 budget 留给后续 key, 也顺带给单 tier 内更多 key 重试机会.
            is_ssl_err = (error_class == "SSLEOFError" or error_class == "SSLError" or
                         error_class == "SSLZeroReturnError")
            if is_ssl_err:
                _log("NV-SSL-CYCLE", f"tier={tier_model} k{key_idx+1} SSL error ({elapsed_ms}ms) — "
                                     f"cycle to next key (no same-key retry, F-fix saves budget)")
                continue  # cycle to next key — 不 sleep, 不重试同 key

            if "gaierror" in error_class.lower() or "socket" in error_class.lower():
                consecutive_conn_err += 1
                if consecutive_conn_err >= CONN_ERR_FAST_BREAK:
                    _log("NV-CONN-BREAK", f"tier={tier_model} {consecutive_conn_err} consecutive "
                                           f"DNS/socket errors → fast-break")
                    key_cycle_attempts.append({
                        "tier": tier_model,
                        "nv_key_idx": key_idx,
                        "litellm_model": f"nvcf_{NV_MODEL_IDS[tier_model]}_k{key_idx+1}",
                        "error": str(e)[:200],
                        "error_type": f"NVCFPexec{error_class}",
                        "elapsed_ms": elapsed_ms,
                        "upstream_type": "nvcf_pexec",
                        "function_id": function_id,
                    })
                    break
            key_cycle_attempts.append({
                "tier": tier_model,
                "nv_key_idx": key_idx,
                "litellm_model": f"nvcf_{NV_MODEL_IDS[tier_model]}_k{key_idx+1}",
                "error": str(e)[:200],
                "error_type": f"NVCFPexec{error_class}",
                "elapsed_ms": elapsed_ms,
                "upstream_type": "nvcf_pexec",
                "function_id": function_id,
            })
            continue

    # ─── All keys in this tier exhausted ───
    tier_attempts = [a for a in key_cycle_attempts if a.get("tier") == tier_model]
    all_429 = all(a.get("error_type") == "429_nv_rate_limit" for a in tier_attempts)
    all_empty = all(a.get("error_type") == "empty_200" for a in tier_attempts)

    result.all_keys_exhausted = True
    result.all_429 = all_429
    result.empty_200 = all_empty
    result.key_cycle_attempts = key_cycle_attempts
    result.elapsed_ms = int((time.time() - t_start) * 1000)

    fail_summary = f"429={sum(1 for a in tier_attempts if a.get('error_type')=='429_nv_rate_limit')}, " \
                   f"empty200={sum(1 for a in tier_attempts if a.get('error_type')=='empty_200')}, " \
                   f"timeout={sum(1 for a in tier_attempts if 'Timeout' in a.get('error_type',''))}, " \
                   f"other={sum(1 for a in tier_attempts if a.get('error_type') not in ('429_nv_rate_limit','empty_200') and 'Timeout' not in a.get('error_type',''))}"
    _log("NV-TIER-FAIL", f"tier={tier_model} all {NVU_NUM_KEYS} keys failed: {fail_summary}, "
                          f"elapsed={result.elapsed_ms}ms")

    if all_429:
        for k in range(NVU_NUM_KEYS):
            mark_key_cooling(tier_model, k, duration_s=int(TIER_COOLDOWN_S))
        _log("NV-GLOBAL-COOLDOWN", f"tier={tier_model} all keys 429. Marking all cooling {TIER_COOLDOWN_S:.0f}s (TIER_COOLDOWN)")

    _log_error_detail({
        "request_id": request_id,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00"),
        "error_subcategory": f"tier_{tier_model}_all_keys_failed",
        "tier_model": tier_model,
        "tier_attempts": tier_attempts,
        "all_429": all_429,
        "all_empty_200": all_empty,
        "elapsed_ms": result.elapsed_ms,
    })

    return result


# ─── R839: glm5_2_nv per-key-mode 动态切换链 (5 模式递进) ─────────────────
# "当前生效 mode" 是跨请求持久化的动态指针 (NOT per-key 静态绑定). 见 [[glm52-5mode-candidates]].
# mode_idx 由 glm52_mode_idx.py 持久化 (LOG_DIR/glm52_mode_idx.json), 初始 0 = mode1.
# 逻辑: 当前 key 用当前 mode 发 → 成功则保持 mode (不递进) + 持久化 + return;
#        故障 → mode 递进到下一档 + 换下一个 key; 全 key+全 mode 失败 → all_keys_exhausted.
# mode 只往前递进不回退. 单 IP 模式用 NV_GLM52_SINGLE_US_PROXY (7894→193 两机共有);
# rr_us 模式按 attempt 轮换 NV_GLM52_RR_US_PROXIES (5 美国代理, fallback NV_INTEGRATE_PROXY_URLS).
def _glm52_resolve_proxy(ip_strategy, attempt_idx, key_idx=None):
    """Resolve proxy_url for a given ip_strategy. R839. R1621: key_idx 绑定优先."""
    # R1621: per-key 固定 proxy (key↔IP 一对一). 命中则直接返回, 不走 RR.
    if key_idx is not None and key_idx in NV_GLM52_KEY_PROXY_MAP:
        return NV_GLM52_KEY_PROXY_MAP[key_idx]
    if ip_strategy == "direct":
        return ""
    if ip_strategy == "single_us":
        single = NV_GLM52_SINGLE_US_PROXY
        if single:
            return single
        # fallback: first of NV_INTEGRATE_PROXY_URLS (7894→193 on both hosts)
        return NV_INTEGRATE_PROXY_URLS[0] if NV_INTEGRATE_PROXY_URLS else ""
    if ip_strategy == "rr_us":
        pool = NV_GLM52_RR_US_PROXIES if NV_GLM52_RR_US_PROXIES else NV_INTEGRATE_PROXY_URLS
        if not pool:
            return ""
        # R858 BUG6: 跨请求持久 RR(分散负载, 不集中 7894) + 同请求内 fault 重试偏移(attempt_idx).
        # 旧代码 pool[attempt_idx % len] 用 per-request 序号, 每请求从 0 起, 首次 attempt 永远 7894.
        global _glm52_rr_us_counter
        with _glm52_rr_us_lock:
            _rr_idx = _glm52_rr_us_counter
            _glm52_rr_us_counter += 1
        return pool[(_rr_idx + attempt_idx) % len(pool)]
    return ""


def _glm52_single_attempt(oai_body, tier_model, request_id, metrics, t_start,
                           is_stream, key_idx, mode_name, channel, proxy_url,
                           all_attempts, upstream_timeout_override, attempt_idx=0):
    """Issue ONE NVCF request: fixed key_idx + fixed mode-driven proxy_url. R839.

    Mirrors the per-attempt block of _try_tier_keys / _try_integrate_keys but:
      - key_idx is FIXED (caller controls which key via RR + mode progression)
      - proxy_url is driven by the current mode (direct / single_us / rr_us)
      - channel in {pexec, integrate} picks endpoint (NVCF pexec vs integrate.api)
    Returns UpstreamResult (success=True + resp/conn on 200-non-empty; else
    failure with key_cycle_attempts appended + appropriate cooldown marking).
    """
    result = UpstreamResult()
    result.is_stream = is_stream
    result.tier_model = tier_model
    result.upstream_type = "nvcf_pexec" if channel == "pexec" else "nv_integrate"
    result.function_id = "integrate" if channel == "integrate" else ""

    nv_model_id = NV_MODEL_IDS[tier_model]
    nvcf_config = NVCF_PEXEC_MODELS[tier_model]
    nv_key = NVU_KEYS[key_idx]

    # Body: reuse _build_pexec_body (strip + inject). Same body for pexec/integrate (R572 已验).
    req_body = _build_pexec_body(oai_body, tier_model, nvcf_config)
    req_data = json.dumps(req_body).encode("utf-8")

    is_direct = (not proxy_url) or (proxy_url.strip() == "")
    if channel == "pexec":
        # func_health 选首选 function (intra-model), surge 的自动跳过.
        _candidates = nvcf_config.get("function_ids") or [nvcf_config.get("function_id")]
        function_id = func_health.select_healthy_function(tier_model, _candidates)
        result.function_id = function_id
        nvcf_host = NVCF_BASE_URL
        nvcf_path = f"/v2/nvcf/pexec/functions/{function_id}"
    else:
        nvcf_host = NV_INTEGRATE_HOST
        nvcf_path = NV_INTEGRATE_PATH
        function_id = "integrate"

    # R839 per-mode budget: 每个 mode 单次 attempt 有自己的 budget, 避免一个慢 mode 吃光整链.
    # 用 NVU_TIER_BUDGET_GLM5_2_NV (env, 当前 70s) 作为整链上限, 单 attempt timeout 复用
    # UPSTREAM_TIMEOUT / override. CONNECT_RESERVE_S 预留 connect+SSL 时间.
    chain_budget_s = float(os.environ.get(f"NVU_TIER_BUDGET_{tier_model.upper()}", "70"))
    # R1418: chain budget 按 input 缩放. 实测 353K 请求单次 timeout 67s, 4 档容错需 ~270s,
    # 固定 120s 在第 2 档就耗尽 -> all_tiers_exhausted (16:09:26 353K 请求 240s 全跑穿仍失败).
    # 大请求给 300s 容 4 档容错; 小请求仍用 env 值 (120s) 不变.
    _chain_ic = len(json.dumps(oai_body)) if oai_body else 0
    if _chain_ic > 350000:
        chain_budget_s = max(chain_budget_s, 300.0)
    elif _chain_ic > 200000:
        chain_budget_s = max(chain_budget_s, 240.0)
    elapsed_in_chain = time.time() - t_start
    remaining_budget = chain_budget_s - elapsed_in_chain
    CONNECT_RESERVE_S = float(os.environ.get("NVU_CONNECT_RESERVE_S", "5"))
    MIN_ATTEMPT_TIMEOUT = 5
    if remaining_budget < MIN_ATTEMPT_TIMEOUT:
        _log("NV-GLM52-BUDGET", f"tier={tier_model} mode={mode_name} k{key_idx+1} chain budget "
                                 f"{chain_budget_s}s remaining {remaining_budget:.1f}s < {MIN_ATTEMPT_TIMEOUT}s, abort chain")
        result.all_keys_exhausted = True
        result.final_error_json = {"error": {"type": "glm52_chain_budget_exhausted",
                                              "message": f"chain budget {chain_budget_s}s exhausted",
                                              "mode": mode_name}}
        result.final_resp_status = 408
        result.key_cycle_attempts = all_attempts
        result.elapsed_ms = int((time.time() - t_start) * 1000)
        return result
    # R1927: per-key 指数退避 (监督者 21:00/21:15 方案 step2.1-a). 开关 NVU_GLM52_EXP_BACKOFF=1 且
    # 无 upstream_timeout_override 时, per-attempt timeout 按 attempt_idx 指数递增 (60/120/240, 封顶 240),
    # 让 NVCF "慢但活" 的请求有时间等到首字节 (实测 114 成功 ttfb 58-148s, 旧 66s UPSTREAM_TIMEOUT 提前杀掉).
    # attempt_idx>=len(STEPS) 取 CAP=240 (后 4 轮封顶, 保留 7 轮循环上界 容 NVU_NUM_KEYS=5+2).
    _exp_base_timeout = UPSTREAM_TIMEOUT
    if NVU_GLM52_EXP_BACKOFF and not upstream_timeout_override:
        if 0 <= attempt_idx < len(NVU_GLM52_EXP_BACKOFF_STEPS):
            _exp_base_timeout = NVU_GLM52_EXP_BACKOFF_STEPS[attempt_idx]
        else:
            _exp_base_timeout = NVU_GLM52_EXP_BACKOFF_CAP
    per_attempt_timeout = max(MIN_ATTEMPT_TIMEOUT,
                             min(upstream_timeout_override if upstream_timeout_override else _exp_base_timeout,
                                 remaining_budget - CONNECT_RESERVE_S))

    # R295 header camouflage (与 _try_tier_keys/_try_integrate_keys 完全一致)
    hdr_extra = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "application/json, text/plain, */*",
        "X-Requested-With": "XMLHttpRequest",
        "Origin": "https://build.nvidia.com",
        "Referer": "https://build.nvidia.com/explore/discover",
    }
    headers_out = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {nv_key}",
        "Content-Length": str(len(req_data)),
        "Connection": "close",
        **hdr_extra,
    }

    _log("NV-GLM52-ATTEMPT", f"tier={tier_model} mode={mode_name} k{key_idx+1} channel={channel} "
                             f"{'DIRECT' if is_direct else 'via ' + proxy_url} timeout={per_attempt_timeout:.0f}s")

    attempt = {
        "tier": tier_model,
        "nv_key_idx": key_idx,
        "litellm_model": f"{channel}_{nv_model_id}_k{key_idx+1}",
        "mode": mode_name,
        "channel": channel,
        "proxy": proxy_url if proxy_url else "direct",
        "upstream_type": result.upstream_type,
        "function_id": function_id,
    }

    try:
        throttle_outbound()
        t_attempt_start = time.time()
        conn = _make_nvcf_proxy_conn(proxy_url, nvcf_host=nvcf_host, timeout=per_attempt_timeout)
        connect_elapsed = time.time() - t_attempt_start
        post_connect_remaining = chain_budget_s - (time.time() - t_start)
        if post_connect_remaining < MIN_ATTEMPT_TIMEOUT:
            _log("NV-GLM52-BUDGET", f"tier={tier_model} mode={mode_name} k{key_idx+1} after connect "
                                    f"({connect_elapsed:.1f}s) remaining {post_connect_remaining:.1f}s, abort")
            try: conn.close()
            except Exception: pass
            attempt["error_type"] = "budget_exhausted_after_connect"
            attempt["elapsed_ms"] = int(connect_elapsed * 1000)
            all_attempts.append(attempt)
            result.all_keys_exhausted = True
            result.key_cycle_attempts = all_attempts
            result.elapsed_ms = int((time.time() - t_start) * 1000)
            return result
        read_timeout = min(per_attempt_timeout, post_connect_remaining)
        conn.request("POST", nvcf_path, body=req_data, headers=headers_out)
        if conn.sock:
            conn.sock.settimeout(read_timeout)
        resp = conn.getresponse()

        if resp.status >= 400:
            error_body = resp.read()
            try: error_json = json.loads(error_body)
            except Exception: error_json = {"error": error_body.decode("utf-8", errors="replace")}
            conn.close()
            err_str = json.dumps(error_json)
            should_cycle = resp.status in (401, 403, 429, 408, 500, 502, 503, 504, 202)
            attempt["error_body"] = err_str[:500]
            if resp.status in (401, 403):
                integ_tier = _integrate_tier_name(tier_model) if channel == "integrate" else tier_model
                mark_key_cooling(integ_tier if channel == "integrate" else tier_model, key_idx,
                                 duration_s=NV_INTEGRATE_KEY_COOLDOWN_S if channel == "integrate" else KEY_COOLDOWN_S)
                mark_key_auth_failed(key_idx)
                attempt["error_type"] = f"{channel}_auth_failed_{resp.status}"
                _log("NV-GLM52-AUTH-FAIL", f"tier={tier_model} mode={mode_name} k{key_idx+1} {resp.status} auth failed, cycling")
            elif resp.status == 429:
                integ_tier = _integrate_tier_name(tier_model) if channel == "integrate" else tier_model
                mark_key_cooling(integ_tier if channel == "integrate" else tier_model, key_idx,
                                 duration_s=NV_INTEGRATE_KEY_COOLDOWN_S if channel == "integrate" else KEY_COOLDOWN_S)
                attempt["error_type"] = f"{channel}_429"
                _log("NV-GLM52-COOLDOWN", f"tier={tier_model} mode={mode_name} k{key_idx+1} 429, cooling")
            elif should_cycle:
                attempt["error_type"] = f"{channel}_{resp.status}"
            else:
                # Non-cycling (e.g. 400 DEGRADED) — tier-level, mark degraded
                if resp.status == 400 and "DEGRADED" in err_str.upper():
                    _cd = mark_tier_degraded(tier_model)
                    _log("NV-GLM52-TIER-DEGRADED", f"tier={tier_model} marked DEGRADED cooldown {_cd:.0f}s")
                attempt["error_type"] = f"{channel}_noncycle_{resp.status}"
                all_attempts.append(attempt)
                result.final_error_json = error_json
                result.final_resp_status = resp.status
                result.key_cycle_attempts = all_attempts
                result.elapsed_ms = int((time.time() - t_start) * 1000)
                # Non-cycling = 不换 key 也不递进 mode? 还是递进? 用户: 故障即递进 mode.
                # DEGRADED 是 tier 级故障 (同 model 全 key 都会 400), 递进 mode 也无效但符合
                # "故障即递进" 规则且 all_attempts 已记录, 上层会落 _try_tier_keys 兜底.
                return result  # 故障 → 上层递进 mode
            all_attempts.append(attempt)
            result.key_cycle_attempts = all_attempts
            result.elapsed_ms = int((time.time() - t_start) * 1000)
            return result  # 故障 → 上层递进 mode + 换 key

        # 200 — check empty
        is_empty = _check_empty_200(resp, key_idx, tier_model, is_stream)
        if is_empty:
            attempt["error_type"] = f"{channel}_empty_200"
            all_attempts.append(attempt)
            integ_tier = _integrate_tier_name(tier_model) if channel == "integrate" else tier_model
            mark_key_cooling(integ_tier if channel == "integrate" else tier_model, key_idx,
                             duration_s=NV_INTEGRATE_KEY_COOLDOWN_S if channel == "integrate" else KEY_COOLDOWN_S)
            _log("NV-GLM52-EMPTY", f"tier={tier_model} mode={mode_name} k{key_idx+1} empty 200, cooling, mode→advance")
            try: conn.close()
            except Exception: pass
            result.key_cycle_attempts = all_attempts
            result.elapsed_ms = int((time.time() - t_start) * 1000)
            return result  # empty = 故障 → 上层递进 mode

        # ─── Valid success ───
        result.success = True
        result.resp = resp
        result.conn = conn
        result.nv_key_idx = key_idx
        result.nv_model_label = f"{channel}_{nv_model_id}_k{key_idx+1}"
        # R839: 记录成功 attempt (含 mode) 到 key_cycle_attempts, 供 DB key_cycle_details 查 mode.
        _succ_attempt = dict(attempt)
        _succ_attempt["error_type"] = f"{channel}_success"
        _succ_attempt["elapsed_ms"] = int((time.time() - t_attempt_start) * 1000)
        all_attempts.append(_succ_attempt)
        result.key_cycle_attempts = all_attempts
        result.fallback_tiers_used = [tier_model]
        # egress info: pexec direct/mihomo 用 egress_info_for_key; integrate 用实际 proxy_url 算.
        if channel == "pexec":
            result.egress_route, result.egress_ip = egress_info_for_key(key_idx)
            # 但 mode 驱动的 proxy 可能与 NVU_PROXY_URLS[key_idx] 不同 (R839 新增美国代理出口),
            # 覆盖: mode 非 direct 时用 proxy_url 推导 route + NV_INTEGRATE_EGRESS_IPS 兜底.
            if not is_direct:
                _port = proxy_url.strip().rsplit(":", 1)[-1] if ":" in proxy_url else "?"
                result.egress_route = f"glm52-mihomo-{_port}"
                # 查 NV_INTEGRATE_EGRESS_IPS (与 NV_INTEGRATE_PROXY_URLS 顺序对齐)
                if NV_INTEGRATE_PROXY_URLS:
                    try:
                        _pi = NV_INTEGRATE_PROXY_URLS.index(proxy_url)
                        result.egress_ip = NV_INTEGRATE_EGRESS_IPS[_pi] if _pi < len(NV_INTEGRATE_EGRESS_IPS) else ""
                    except ValueError:
                        result.egress_ip = ""
        else:
            _port = proxy_url.strip().rsplit(":", 1)[-1] if proxy_url and ":" in proxy_url else "direct"
            result.egress_route = f"glm52-integrate-mihomo-{_port}" if not is_direct else "glm52-integrate-direct"
            if not is_direct and NV_INTEGRATE_PROXY_URLS:
                try:
                    _pi = NV_INTEGRATE_PROXY_URLS.index(proxy_url)
                    result.egress_ip = NV_INTEGRATE_EGRESS_IPS[_pi] if _pi < len(NV_INTEGRATE_EGRESS_IPS) else ""
                except ValueError:
                    result.egress_ip = ""
            elif is_direct:
                _, result.egress_ip = egress_info_for_integrate_key(key_idx)
        reset_key429_count(_integrate_tier_name(tier_model) if channel == "integrate" else tier_model, key_idx)
        metrics["upstream_type"] = result.upstream_type
        metrics["tier_model"] = tier_model
        metrics["nv_key_idx"] = key_idx
        metrics["litellm_model"] = result.nv_model_label
        metrics["glm52_mode"] = mode_name
        metrics["egress_route"] = result.egress_route
        metrics["egress_ip"] = result.egress_ip
        if all_attempts:
            metrics["key_cycle_429s_before_success"] = len(all_attempts)
            metrics["key_cycle_details"] = all_attempts
        _log("NV-GLM52-SUCCESS", f"tier={tier_model} mode={mode_name} k{key_idx+1} succeeded "
                                  f"(mode stabilized, next req keeps this mode)")
        return result

    except socket.timeout as e:
        attempt_elapsed_ms = int((time.time() - t_attempt_start) * 1000)
        attempt["error_type"] = f"{channel}_timeout"
        attempt["elapsed_ms"] = attempt_elapsed_ms
        all_attempts.append(attempt)
        _log("NV-GLM52-TIMEOUT", f"req={request_id} tier={tier_model} mode={mode_name} k{key_idx+1} timeout: {attempt_elapsed_ms}ms → mode→advance")
        result.key_cycle_attempts = all_attempts
        result.elapsed_ms = int((time.time() - t_start) * 1000)
        return result
    except (ConnectionRefusedError, http.client.RemoteDisconnected) as e:
        attempt_elapsed_ms = int((time.time() - t_attempt_start) * 1000)
        attempt["error_type"] = f"{channel}_conn_{type(e).__name__}"
        attempt["elapsed_ms"] = attempt_elapsed_ms
        all_attempts.append(attempt)
        _log("NV-GLM52-CONN", f"req={request_id} tier={tier_model} mode={mode_name} k{key_idx+1} conn err: {e} → mode→advance")
        result.key_cycle_attempts = all_attempts
        result.elapsed_ms = int((time.time() - t_start) * 1000)
        return result
    except Exception as e:
        error_class = type(e).__name__
        elapsed_ms = int((time.time() - t_attempt_start) * 1000)
        attempt["error_type"] = f"{channel}_{error_class}"
        attempt["error"] = str(e)[:200]
        attempt["elapsed_ms"] = elapsed_ms
        all_attempts.append(attempt)
        is_ssl = error_class in ("SSLEOFError", "SSLError", "SSLZeroReturnError")
        _log("NV-GLM52-ERR", f"req={request_id} tier={tier_model} mode={mode_name} k{key_idx+1} {error_class}: {e} → mode→advance")
        result.key_cycle_attempts = all_attempts
        result.elapsed_ms = int((time.time() - t_start) * 1000)
        return result


def _glm52_eof_summary(all_attempts, request_id):
    """R1730: 单请求内 SSLEOFError 各 channel 分布摘要. 纯日志, 无行为变更.

    间歇性 socks5 出口抽风期, 单请求要熬过多次 EOF cycle 才命中健康 channel.
    本摘要聚合本次 chain 所有 attempt 里 SSL 类失败涉及的 proxy(端口),
    让诊断一眼看出是"全端口间歇抽风"(各 port 均匀 EOF, 不宜做熔断)还是
    "某固定坏 channel"(某 port EOF 独高, 可考虑 channel 级短熔断).
    仅在 chain 失败路径调用 (成功 path 无 EOF 风暴, 不打省噪音).
    """
    eof_counts = {}  # proxy_port -> count
    n_eof = 0
    for a in (all_attempts or []):
        et = a.get("error_type", "")
        if et.endswith(("SSLEOFError", "SSLError", "SSLZeroReturnError")):
            n_eof += 1
            proxy = a.get("proxy", "direct")
            port = proxy.rsplit(":", 1)[-1] if ":" in proxy else proxy
            eof_counts[port] = eof_counts.get(port, 0) + 1
    if n_eof:
        dist = " ".join(f":{p}={c}" for p, c in sorted(eof_counts.items()))
        _log("NV-GLM52-EOF-SUMMARY", f"req={request_id} ssl_eof={n_eof} cycles dist {dist}")


def _try_glm52_mode_chain(oai_body, tier_model, request_id, metrics, t_start,
                          is_stream, all_attempts, upstream_timeout_override):
    """R839: glm5_2_nv per-key-mode 动态递进. mode 是持久化指针, 故障→递进, 稳住→保持.

    modes = NV_GLM52_MODE_CHAIN (list of (mode_name, channel, ip_strategy), len 5).
    最多试 NVU_NUM_KEYS + 2 轮 (5 key + 容错). 每 attempt: 当前 key + 当前 mode.
      - success → 持久化 mode_idx (保持, 不递进) + return success
      - fault → mode_idx = min(idx+1, len-1) + 换下一个 key
    全 key+全 mode 失败 → all_keys_exhausted, 持久化最后 mode_idx (下次从最后 mode 起步).
    """
    modes = NV_GLM52_MODE_CHAIN
    result = UpstreamResult()
    result.is_stream = is_stream
    result.tier_model = tier_model
    if not modes:
        result.all_keys_exhausted = True
        result.final_error_json = {"error": {"type": "glm52_mode_chain_empty",
                                              "message": "NV_GLM52_MODE_CHAIN not configured"}}
        result.key_cycle_attempts = all_attempts
        result.elapsed_ms = int((time.time() - t_start) * 1000)
        return result

    mode_idx = glm52_current_mode_idx()
    if mode_idx >= len(modes):
        mode_idx = 0  # 持久化值越界 (config 变了) → 回到 mode1
    start_key = _peek_nv_key(tier_model)  # R1621c: 只 peek 不 advance (修双 advance bug)
    _log("NV-GLM52-CHAIN", f"tier={tier_model} start_mode_idx={mode_idx} (={modes[mode_idx][0]}) "
                           f"start_key=k{start_key+1} modes={[m[0] for m in modes]}")

    # R1621b: 反��调度模型 — key RR 轮流 k1~k5, 每 key 走自己绑定的 mode (非故障才 fallback).
    # 查表: KEY_MODE_BINDING[key_idx] → mode_name → (channel, ip_strategy).
    # 某 key 失败→cooldown 该 key→advance RR→下一 key 走它自己的 mode. 全 5 key 失败才 all_keys_exhausted.
    _mode_lookup = {m[0]: m for m in modes}  # mode_name -> (mode_name, channel, ip_strategy)
    for attempt in range(NVU_NUM_KEYS + 2):
        key_idx = (start_key + attempt) % NVU_NUM_KEYS
        # R1621b: 每 key 查自己绑定的 mode; 未绑定则用 mode_idx 指针兜底 (向后兼容).
        _bound_mode_name = KEY_MODE_BINDING.get(key_idx)
        if _bound_mode_name and _bound_mode_name in _mode_lookup:
            mode_name, channel, ip_strategy = _mode_lookup[_bound_mode_name]
        else:
            mode_name, channel, ip_strategy = modes[mode_idx]
        # 跳过冷却/auth-fail 的 key (换下一 key, 每 key 走自己 mode)
        _integ_tier = _integrate_tier_name(tier_model) if channel == "integrate" else None
        _ck_tier = _integ_tier if channel == "integrate" else tier_model
        if is_key_cooling(_ck_tier, key_idx) or is_key_auth_failed(key_idx):
            _log("NV-GLM52-KEY-SKIP", f"tier={tier_model} mode={mode_name} k{key_idx+1} cooling/auth-failed, next key")
            continue

        proxy_url = _glm52_resolve_proxy(ip_strategy, attempt, key_idx)
        r = _glm52_single_attempt(oai_body, tier_model, request_id, metrics, t_start,
                                   is_stream, key_idx, mode_name, channel, proxy_url,
                                   list(all_attempts), upstream_timeout_override)
        all_attempts = r.key_cycle_attempts

        if r.success and not r.empty_200:
            # 稳住 → 保持当前 mode (不递进), 持久化供下次请求起步
            glm52_save_mode_idx(mode_idx)
            r.fallback_tiers_used = [tier_model]
            metrics["tier_model"] = r.tier_model
            metrics["fallback_tiers_used"] = r.fallback_tiers_used
            metrics["glm52_mode"] = mode_name
            metrics["nv_key_idx"] = key_idx
            if r.function_id:
                metrics["function_id"] = r.function_id
            func_health.record_result(r.function_id, True)
            # R1621c: 成功才 advance (start_key 只 peek). 下个请求从下一 key 起 = 干净 k1->k2->k3->k4->k5 轮流.
            _next_nv_key(tier_model)
            return r

        # budget-abort (chain 预算耗尽): 不递进, 直接全链失败
        if r.all_keys_exhausted and r.final_error_json and \
           r.final_error_json.get("error", {}).get("type") == "glm52_chain_budget_exhausted":
            result.all_keys_exhausted = True
            result.final_error_json = r.final_error_json
            result.final_resp_status = r.final_resp_status
            result.key_cycle_attempts = all_attempts
            result.elapsed_ms = int((time.time() - t_start) * 1000)
            glm52_save_mode_idx(mode_idx)  # 下次从当前 mode 起步
            _glm52_eof_summary(all_attempts, request_id)  # R1730 失败路径 EOF 诊断摘要
            return result

        # R1621b: 故障 → cooldown 该 key + 换下一 key (走它自己 mode). 不递进 mode 指针.
        func_health.record_result(r.function_id, False)
        _log("NV-GLM52-KEY-FAULT", f"tier={tier_model} k{key_idx+1} mode={mode_name} fault → next key (RR advance)")

    # 全 key+全 mode 失败
    _log("NV-GLM52-CHAIN-FAIL", f"tier={tier_model} all {NVU_NUM_KEYS} keys + modes exhausted, "
                                f"last_mode={modes[mode_idx][0]}")
    _glm52_eof_summary(all_attempts, request_id)  # R1730 失败路径 EOF 诊断摘要
    result.all_keys_exhausted = True
    result.final_error_json = {"error": {"type": "glm52_chain_all_keys_exhausted",
                                          "message": f"all keys + all modes failed for {tier_model}",
                                          "last_mode": modes[mode_idx][0]}}
    result.final_resp_status = 502
    result.key_cycle_attempts = all_attempts
    result.elapsed_ms = int((time.time() - t_start) * 1000)
    # R844: 全 key+全 mode 失败 → 复位 idx=0 (而非保持最后失败 mode).
    # 之前保持最后 mode (如 idx=3 integrate_us_single) 致下个请求继续撞同一坏 mode/IP
    # (7894 坏 IP, 76 次 zombie). mode0=pexec_us_rr 多 IP 轮换更可能分散命中好 IP.
    # 后端整体恢复由 speedtest cron 重排 chain 实现软重置; 硬故障期复位 0 是逃逸阀.
    glm52_reset_mode_idx()
    _log("NV-GLM52-CHAIN-RESET", f"tier={tier_model} all modes failed → reset mode_idx to 0 (next req from {modes[0][0]})")
    return result


# ─── R1648c: nv→ms fallback (5key 全坏兜底) ──────────────────────────────
# NVCF 5key×mode 链全挂 (all_keys_exhausted) 后, POST ms_gw (ModelScope glm5_2_ms)
# 返回 openai SSE 流. 对调用方透明: 返回的 UpstreamResult.resp 指向 ms_gw 流, handler
# 层的 stream/collect 逻辑原样处理 (openai 路径透传; /v1/messages 路径经 oai_to_anth 转).
# 与 cc4101 R1643 的 _try_fallback 同形, 但下沉到 nv_gw (R1648 框架: cc4101 退化为纯透传后
# 转换+fallback 全在 40006). ms_gw 吃 openai, 故 oai_body 的 model 字段需深拷贝换 glm5_2_ms.
def _ms_fallback_request(oai_body, mapped_model, request_id, metrics, t_start):
    """One ms_gw attempt after nv chain all_keys_exhausted.

    Returns (success: bool, result: UpstreamResult | None). On success, result
    has .resp/.conn pointing at ms_gw's openai SSE stream and .success=True.
    On failure, returns (False, None) — caller keeps the nv final_result.
    成败都不改 breaker (breaker 只记 nv 链 all_keys_exhausted, 不记 ms 成败).
    """
    if not (NVU_MS_FALLBACK_ENABLED and NVU_MS_FALLBACK_URL
            and mapped_model in NVU_MS_FALLBACK_MODELS):
        return False, None
    t_fb_start = time.time()
    # R1643 同坑: oai_body["model"] 是 nv 的 glm5_2_nv, ms_gw 会 404 "model not found".
    # 深拷贝换 model, 不改原 oai_body (避免污染后续重试).
    import copy as _copy
    fb_body = _copy.copy(oai_body)
    fb_body["model"] = NVU_MS_FALLBACK_MODEL
    # ms_gw 吃 openai (非 anthropic); 上游流式标志沿用 oai_body 已设的 stream=True.
    body_bytes = json.dumps(fb_body, ensure_ascii=False).encode("utf-8")
    # parse ms_gw URL
    try:
        from urllib.parse import urlparse
        p = urlparse(NVU_MS_FALLBACK_URL)
        host = p.hostname
        port = p.port or 40007
        ms_path = p.path or "/v1/chat/completions"
    except Exception as e:
        _log("NV-MS-FB", f"bad NVU_MS_FALLBACK_URL={NVU_MS_FALLBACK_URL}: {e}")
        return False, None
    fwd_headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {NVU_MS_FALLBACK_TOKEN}",
        "Content-Length": str(len(body_bytes)),
    }
    # preserve caller hint if present
    _xc = metrics.get("caller")
    if _xc:
        fwd_headers["X-Caller"] = _xc
    ms_conn = None
    try:
        ms_conn = http.client.HTTPConnection(host, port, timeout=NVU_MS_FALLBACK_TIMEOUT)
        ms_conn.request("POST", ms_path, body=body_bytes, headers=fwd_headers)
        resp = ms_conn.getresponse()
    except Exception as e:
        elapsed_ms = int((time.time() - t_fb_start) * 1000)
        _log("NV-MS-FB", f"ms_gw connect/request failed after {elapsed_ms}ms: "
                        f"{type(e).__name__}: {e}")
        if ms_conn:
            try: ms_conn.close()
            except Exception: pass
        metrics["ms_fallback_error"] = f"connect_{type(e).__name__}"
        metrics["ms_fallback_ms"] = elapsed_ms
        return False, None
    # ms_gw returned error status (502/429) → don't use; caller returns nv 502
    if resp.status >= 500 or resp.status == 429:
        elapsed_ms = int((time.time() - t_fb_start) * 1000)
        try: resp.read()
        except Exception: pass
        try: ms_conn.close()
        except Exception: pass
        _log("NV-MS-FB", f"ms_gw returned {resp.status} after {elapsed_ms}ms, "
                        f"not relaying, returning nv 502")
        metrics["ms_fallback_error"] = f"ms_http_{resp.status}"
        metrics["ms_fallback_ms"] = elapsed_ms
        return False, None
    # success — wrap as UpstreamResult so handler's existing stream/collect path works
    r = UpstreamResult()
    r.success = True
    r.resp = resp
    r.conn = ms_conn
    r.tier_model = NVU_MS_FALLBACK_MODEL
    r.nv_key_idx = -1  # sentinel: not an NV key
    r.nv_model_label = f"ms_fallback_{NVU_MS_FALLBACK_MODEL}"
    r.upstream_type = "ms_fallback"
    r.fallback_tiers_used = [mapped_model, NVU_MS_FALLBACK_MODEL]
    r.elapsed_ms = int((time.time() - t_start) * 1000)
    metrics["ms_fallback_used"] = True
    metrics["ms_fallback_ms"] = int((time.time() - t_fb_start) * 1000)
    metrics["ms_fallback_status"] = resp.status
    metrics["upstream_type"] = "ms_fallback"
    metrics["tier_model"] = NVU_MS_FALLBACK_MODEL
    metrics["fallback_occurred"] = True
    metrics["fallback_from"] = mapped_model
    metrics["fallback_to"] = NVU_MS_FALLBACK_MODEL
    _log("NV-MS-FB-OK", f"ms_gw fallback success for {mapped_model} after "
                       f"{metrics['ms_fallback_ms']}ms (req={request_id}), "
                       f"relaying openai SSE via UpstreamResult")
    return True, r


def execute_request(handler, oai_body, mapped_model, request_id, metrics, t_start, upstream_timeout_override=None):
    """Execute NVCF pexec request with three-tier fallback (R38.12, R40 ring fallback).

    ALL models use NVCF pexec direct path. No LiteLLM routing.
    - mapped_model determines starting tier (default: dsv4p_nv)
    - R40 CRITICAL FIX: ring fallback — tier_order = TIERS[start:] + TIERS[:start]
      This guarantees ANY tier (including the last) has 2 fallback tiers.
      Pre-R40 bug: TIERS[start_idx:] slice — when start_tier was the LAST tier
      (e.g. the last model in R38.9 tier order), the slice had only 1 element,
      so a failure at that tier returned 502 with NO fallback attempted.
      Symptom: "Tiers tried: [dsv4p_nv: 2×mixed]" 74.2s, agent stuck.
    - Each tier tries 5 keys with per-tier persistent RR counter
    - On tier all-fail: fallback to next tier in ring order (wraps around)
    - All tiers fail: ABORT-NO-FALLBACK
    - R38.8: If all tiers fail with ONLY connection errors, wait 5s and retry once.
    """
    start_tier_idx = get_tier_index(mapped_model)
    is_stream = oai_body.get("stream", False)

    # ─── R1648c: nv breaker OPEN → 直走 ms_gw (跳过 nv 链省 ~120s 预算) ───
    # 仅 glm5_2_nv. 连续 N=15 次 all_keys_exhausted 后 breaker OPEN, 冷却 SKIP_S=30s 内
    # 跳过 nv 链直走 ms_gw (省每条等 nv 跑满 5key×mode chain ~120s). HALF_OPEN (冷却过期) 时
    # is_ms_fallback_open() 返 False → 放行 nv 链探活一次 (成功→record_nv_success 重置 CLOSED,
    # 失败→record_nv_failure 重 OPEN). 落在 tier_order 设置前, 命中即 return.
    if (NVU_MS_FALLBACK_ENABLED and NVU_MS_FALLBACK_URL
            and mapped_model in NVU_MS_FALLBACK_MODELS
            and nv_breaker.is_ms_fallback_open()):
        _log("NV-MS-FB-BREAKER-OPEN", f"breaker OPEN for {mapped_model} (req={request_id}), "
                                     f"skipping nv chain, serving ms_gw directly "
                                     f"(state={nv_breaker.breaker_state()})")
        ok, ms_result = _ms_fallback_request(oai_body, mapped_model, request_id, metrics, t_start)
        if ok and ms_result is not None:
            return ms_result
        # breaker OPEN 但 ms 也失败 — 仍 return nv final_result? 这里没 nv final_result,
        # 落回 nv 链试一次 (HALF_OPEN 探活语义: 本该探 nv, ms 失败则继续走 nv 链).
        _log("NV-MS-FB-BREAKER-OPEN-MSFAIL", f"breaker OPEN but ms_gw failed (req={request_id}), "
                                            f"falling through to nv chain (HALF_OPEN probe)")

    # ─── R1673: 超大 input big-input breaker OPEN → 直走 ms_gw (跳过 nv ~115s hang 死循环) ───
    # 与 R1648c nv_breaker 互补: nv_breaker 看"全 key 挂"(整体健康), big_input_breaker 看
    # "特定 input 段系统性坏"(按 input 维度). 283k 超大 input NVCF glm5.2 系统性 200-then-hang,
    # 每次拖满 ~115s (pexec 62s + integrate 45s), CC 死循环重试同一 283k 请求达 1h+.
    # 连续 N=3 次超大 input hang 失败后 OPEN, cooldown 180s 内对超大 input 直走 ms_gw
    # (省 ~115s/次 → ~5s 拒到 ms). 仅 glm5_2_nv (其他模型无 ms 对应). ms 失败则落回 nv 链
    # (HALF_OPEN 探活语义). 成功一次 → CLOSED 重置.
    _bi_input = metrics.get("total_input_chars", 0) or 0
    if (NVU_MS_FALLBACK_ENABLED and NVU_MS_FALLBACK_URL
            and mapped_model in NVU_MS_FALLBACK_MODELS
            and big_input_breaker.is_big_input(_bi_input)
            and big_input_breaker.is_big_input_open()):
        _log("NV-BIGINPUT-FB-OPEN", f"big_input breaker OPEN for {mapped_model} "
                                   f"input={_bi_input}c (req={request_id}), skipping nv chain "
                                   f"(~115s hang), serving ms_gw directly "
                                   f"(state={big_input_breaker.big_input_breaker_state()})")
        ok, ms_result = _ms_fallback_request(oai_body, mapped_model, request_id, metrics, t_start)
        if ok and ms_result is not None:
            return ms_result
        _log("NV-BIGINPUT-FB-OPEN-MSFAIL", f"big_input breaker OPEN but ms_gw failed "
                                          f"(req={request_id}), falling through to nv chain")

    # R753: 删除跨 model fallback (FALLBACK_GRAPH). nv_gw 只做单 model 5 key 轮转.
    # 全挂返 5xx, 由 41xx 适配器切后端 (同模型跨后端, 保持模型一致性).
    # 保留: func_health.select_healthy_function (intra-model function 选择, 同 model 多 function_id).
    tier_order = [mapped_model]
    _log("NV-REQ", f"mapped_model={mapped_model} start_tier={mapped_model} "
                   f"stream={is_stream} tier_chain={tier_order} (no cross-model fallback, R753)")

    for retry_idx in range(2):
        all_attempts = []
        all_tier_summaries = []
        fallback_tiers_used = []

        for tier_idx, tier_model in enumerate(tier_order):
            is_first_tier = (tier_idx == 0)
            prev_tier = tier_order[tier_idx - 1] if not is_first_tier else None

            # Skip tier if all keys in cooldown
            all_cooling = all(is_key_cooling(tier_model, k) for k in range(NVU_NUM_KEYS))
            if all_cooling:
                _log("NV-TIER-SKIP", f"tier={tier_model} all keys in cooldown, skipping")
                # R40 A3: cooldown is neither 429 nor empty-200 — don't misclassify.
                all_tier_summaries.append({
                    "tier": tier_model,
                    "all_429": False,
                    "all_empty_200": False,
                    "all_cooldown": True,
                    "num_attempts": 0,
                    "elapsed_ms": 0,
                    "skipped": True,
                })
                if not is_first_tier:
                    _log("NV-FALLBACK", f"Tier {prev_tier} all-failed → "
                                        f"falling back to {tier_model} (skipped, cooldown)")
                continue

            if not is_first_tier:
                _log("NV-FALLBACK", f"Tier {prev_tier} all-failed → "
                                    f"falling back to {tier_model}")

            # R1913 阶段1.5: 每轮 tier 迭代重置 chain 失败标志, 仅当本分支 chain 失败才 True.
            _chain_failed = False

            # R839: glm5_2_nv per-key-mode 动态切换链 (5 模式递进). mode 是持久化指针,
            # 故障→递进+换key, 稳住→保持. 与 R838b/R572 互斥: 仅 glm5_2_nv + 配置了
            # NV_GLM52_MODE_CHAIN 时触发, 命中即 return, 不命中落到 R838b/R572/pexec 原逻辑.
            # NV-GLM52-R839-BRANCH
            if (is_first_tier and tier_model == "glm5_2_nv" and NV_GLM52_MODE_CHAIN
                    and not _integrate_is_path_cooling()):
                chain_result = _try_glm52_mode_chain(oai_body, tier_model, request_id, metrics, t_start,
                                                       is_stream, all_attempts, upstream_timeout_override)
                if chain_result.success and not chain_result.empty_200:
                    chain_result.fallback_tiers_used = [tier_model]
                    metrics["tier_model"] = chain_result.tier_model
                    metrics["fallback_tiers_used"] = chain_result.fallback_tiers_used
                    metrics["glm52_mode"] = chain_result.nv_model_label  # placeholder, _try 内已写 mode
                    if chain_result.function_id:
                        metrics["function_id"] = chain_result.function_id
                    if retry_idx > 0:
                        _log("NV-STARTUP-RETRY-SUCCESS", f"Startup retry #{retry_idx} succeeded (glm52 mode chain)")
                        metrics["startup_retry"] = retry_idx
                    return chain_result
                # R1911 阶段1 (修 BUG-A): mode chain 全失败后 STAGE1_CHAIN_FAIL=直接 all_keys_exhausted,
                # 不再落 R838b/R572/pexec 兜底跑第二轮全 key pexec (chain 已覆盖全 5 key×全 mode,
                # 第二轮同 function 同出口 IP, 边际收益低却多吃整轮 tier_budget, 单请求烧 ~240s 才走 ms).
                # 监督者 2026-07-19 16:00 巡视定位 upstream.py:1554-1610: CHAIN-FALLBACK→pexec 兜底
                # 第二轮 budget 双吃 (两个函数各自 tier_budget_start 叠加). 阶段1 省这第二轮 ~120s.
                _log("NV-GLM52-CHAIN-FALLBACK", f"req={request_id} tier={tier_model} mode chain all-failed → STAGE1_CHAIN_FAIL skip pexec 2nd round, mark all_keys_exhausted")
                all_attempts = list(chain_result.key_cycle_attempts)
                _chain_failed = True

            # R838b: per-key 跨链路 — RR 自然分散. peek 当前 RR key (不 advance), 若该 key 在
            # NV_KEY_INTEGRATE_KEYS 则走 integrate (只试该 key), 否则走 pexec (RR 到该 key 起).
            # 这样 K1-4 pexec 与 K5 integrate 按 RR 比例自然分担流量, 实现数据多样性.
            # 与 R572 互斥: model 在 NV_INTEGRATE_MODELS 走全 key integrate; 否则走 per-key 分支.
            _r838_keys = nv_key_integrate_keys_for(tier_model)
            _peek_key = _peek_nv_key(tier_model) if (is_first_tier and _r838_keys) else -1
            if (is_first_tier and NV_INTEGRATE_ENABLED
                    and tier_model not in NV_INTEGRATE_MODELS
                    and _r838_keys and _peek_key in _r838_keys
                    and not _integrate_is_path_cooling()):
                _log("NV-R838B-LANE", f"tier={tier_model} RR peek=k{_peek_key+1} → integrate (per-key)")
                integ_result = _try_integrate_keys(oai_body, tier_model, request_id, metrics, t_start,
                                                    is_stream, all_attempts, upstream_timeout_override,
                                                    key_filter=[_peek_key])
                if integ_result.success and not integ_result.empty_200:
                    # integrate 命中后 advance RR (与 pexec 对齐, 保持轮转均匀)
                    _next_nv_key(tier_model)
                    integ_result.fallback_tiers_used = [tier_model]
                    metrics["tier_model"] = integ_result.tier_model
                    metrics["fallback_tiers_used"] = integ_result.fallback_tiers_used
                    if retry_idx > 0:
                        _log("NV-STARTUP-RETRY-SUCCESS", f"Startup retry #{retry_idx} succeeded (integrate per-key)")
                        metrics["startup_retry"] = retry_idx
                    return integ_result
                # per-key integrate 失败 → 落到下方 pexec _try_tier_keys 全 key 轮转 (含该 key pexec 兜底).
                _log("NV-INTEGRATE-PERKEY-FALLBACK", f"tier={tier_model} k{_peek_key+1} integrate failed → falling back to pexec")
                all_attempts = list(integ_result.key_cycle_attempts)
                # integrate 失败也 advance RR (避免下次仍 peek 到同一坏 key)
                _next_nv_key(tier_model)
            # R572: 首选 integrate 直连路径 (仅 first tier + NV_INTEGRATE_MODELS + path 未冷却).
            # integrate 全 key 失败/全 429 → 回退下方 pexec _try_tier_keys (同一 tier_model).
            elif (is_first_tier and NV_INTEGRATE_ENABLED and tier_model in NV_INTEGRATE_MODELS
                    and not _integrate_is_path_cooling()):
                integ_result = _try_integrate_keys(oai_body, tier_model, request_id, metrics, t_start,
                                                    is_stream, all_attempts, upstream_timeout_override)
                if integ_result.success and not integ_result.empty_200:
                    integ_result.fallback_tiers_used = [tier_model]
                    metrics["tier_model"] = integ_result.tier_model
                    metrics["fallback_tiers_used"] = integ_result.fallback_tiers_used
                    if retry_idx > 0:
                        _log("NV-STARTUP-RETRY-SUCCESS", f"Startup retry #{retry_idx} succeeded (integrate)")
                        metrics["startup_retry"] = retry_idx
                    # integrate 无 function_id, 不记 func_health (它只追踪 pexec function).
                    return integ_result
                # integrate 失败 → 累积 attempts, 落到 pexec _try_tier_keys 重试同一 model.
                _log("NV-INTEGRATE-FALLBACK", f"tier={tier_model} integrate all-failed → "
                                               f"falling back to pexec same model")
                all_attempts = list(integ_result.key_cycle_attempts)
                all_tier_summaries.append({
                    "tier": tier_model,
                    "path": "nv_integrate",
                    "all_429": integ_result.all_429,
                    "all_empty_200": integ_result.empty_200,
                    "num_attempts": len([a for a in integ_result.key_cycle_attempts
                                         if a.get("tier") == tier_model]),
                    "elapsed_ms": integ_result.elapsed_ms,
                    "fell_back_to_pexec": True,
                })

            # R1913 阶段1.5 (真正修 BUG-A, R1911 stage1 残废补全): chain 失败 (_chain_failed=True)
            # 时 STAGE1_CHAIN_FAIL → 直接跳过 _try_tier_keys 第二轮全 key pexec 兜底.
            # chain (_try_glm52_mode_chain) 已覆盖全 5 key×全 mode (integrate_us_rr+pexec_us_rr),
            # 第二轮同 function_id 同出口 IP 边际收益低却多吃整轮 tier_budget (~120s/req).
            # 补 R1911 的 _chain_failed 标记本意: chain 失败后构造 empty all_keys_exhausted
            # tier_result 走同一 all-tiers-exhausted 失败路径, 由 handlers 触发 ms_fb.
            # 仅 first_tier + glm5_2_nv + NV_GLM52_MODE_CHAIN branch 会设 _chain_failed.
            if _chain_failed:
                tier_result = UpstreamResult()
                tier_result.success = False
                tier_result.all_keys_exhausted = True
                tier_result.empty_200 = False
                tier_result.all_429 = False
                tier_result.key_cycle_attempts = list(all_attempts)
                tier_result.tier_attempts = []
                tier_result.elapsed_ms = 0
                tier_result.function_id = chain_result.function_id if chain_result.function_id else None
                _log("NV-GLM52-CHAIN-SKIP-PEXEC2", f"req={request_id} tier={tier_model} STAGE1_CHAIN_FAIL skip _try_tier_keys 2nd round (saves ~120s), go all_keys_exhausted -> ms_fb")
            else:
                tier_result = _try_tier_keys(oai_body, tier_model, request_id, metrics, t_start,
                                             is_stream, all_attempts, upstream_timeout_override)

            if tier_result.success and not tier_result.empty_200:
                tier_result.fallback_tiers_used = tier_order[:tier_idx + 1]
                if not is_first_tier:
                    _log("NV-FALLBACK-SUCCESS", f"Success on fallback tier {tier_model} "
                                                f"after primary {tier_order[0]} failed")
                    metrics["fallback_from"] = prev_tier
                    metrics["fallback_to"] = tier_model
                metrics["tier_model"] = tier_result.tier_model
                metrics["fallback_tiers_used"] = tier_result.fallback_tiers_used
                # R794: 透传 function_id 到 metrics 供 DB request 级记录 (验证 NVCF per-key/IP/functionID 限速)
                if tier_result.function_id:
                    metrics["function_id"] = tier_result.function_id
                if retry_idx > 0:
                    _log("NV-STARTUP-RETRY-SUCCESS", f"Startup retry #{retry_idx} succeeded")
                    metrics["startup_retry"] = retry_idx
                # R_multi: 按本次选中的 function_id 记录健康度 (不是按 model)
                func_health.record_result(tier_result.function_id, True)
                # R1673: 超大 input nv 链探活成功 → big_input breaker CLOSED 重置
                _bi_input = metrics.get("total_input_chars", 0) or 0
                if big_input_breaker.is_big_input(_bi_input):
                    big_input_breaker.record_big_input_success()
                    _log("NV-BIGINPUT-SUCCESS", f"big_input nv success for {mapped_model} "
                                                f"input={_bi_input}c (req={request_id}), "
                                                f"breaker→CLOSED")
                return tier_result

            # Tier all-failed: record and try next
            # R40 A4: simplified — single condition, no `or a not in all_attempts` dead code.
            tier_attempts = [a for a in tier_result.key_cycle_attempts
                             if a.get("tier") == tier_model]
            # R_multi: 按本次选中的 function_id 记录失败. all_keys_exhausted=该function本轮surge.
            func_health.record_result(tier_result.function_id, False)
            # R794: 失败也透传 function_id (验证限速需看失败 attempt 的 function_id)
            if tier_result.function_id:
                metrics["function_id"] = tier_result.function_id
            all_tier_summaries.append({
                "tier": tier_model,
                "all_429": tier_result.all_429,
                "all_empty_200": tier_result.empty_200,
                "all_cooldown": False,
                "num_attempts": len(tier_attempts),
                "elapsed_ms": tier_result.elapsed_ms,
            })
            all_attempts = list(tier_result.key_cycle_attempts)

            if tier_result.conn:
                try:
                    tier_result.conn.close()
                except Exception:
                    pass

        # ─── All tiers exhausted ───
        _log("NV-ALL-TIERS-FAIL", f"All {len(tier_order)} tiers failed "
                                   f"(ring tiers tried: {tier_order}), "
                                   f"elapsed={int((time.time() - t_start) * 1000)}ms, ABORT-NO-FALLBACK")

        has_429 = any(s.get("all_429") for s in all_tier_summaries)
        has_empty = any(s.get("all_empty_200") for s in all_tier_summaries)

        # Check if ALL failures were connection errors only
        all_conn_err = not has_429 and not has_empty and all(
            ("Conn" in a.get("error_type", "") or "gai" in a.get("error_type", "").lower() or
             "socket" in a.get("error_type", "").lower())
            for a in all_attempts
        ) and len(all_attempts) > 0

        if all_conn_err and retry_idx == 0:
            _log("NV-STARTUP-RETRY", f"All tiers failed with only connection errors. Waiting 5s...")
            time.sleep(5)
            continue

        break

    # Build final result
    has_429 = any(s.get("all_429") for s in all_tier_summaries)
    has_empty = any(s.get("all_empty_200") for s in all_tier_summaries)

    final_result = UpstreamResult()
    final_result.success = False
    final_result.all_keys_exhausted = True
    final_result.all_429 = has_429 and not has_empty
    final_result.empty_200 = has_empty
    final_result.key_cycle_attempts = all_attempts
    final_result.tier_attempts = all_tier_summaries
    final_result.fallback_tiers_used = tier_order
    final_result.elapsed_ms = int((time.time() - t_start) * 1000)
    final_result.final_resp_status = 429 if has_429 else 502

    _log_error_detail({
        "request_id": request_id,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00"),
        "error_subcategory": "all_tiers_failed",
        "start_tier": tier_order[0],
        "tiers_tried": tier_order,
        "tier_summaries": all_tier_summaries,
        "total_attempts": len(all_attempts),
        "elapsed_ms": final_result.elapsed_ms,
        "startup_retry_attempted": retry_idx > 0,
    })

    # R41: Do NOT call _log_metrics() here. The metrics dict passed into this
    # function (from handlers._handle_openai_nv) is written by handlers.py in
    # the `all_keys_exhausted` branch (handlers.py ~L142) with full DB-compatible
    # fields (request_id, timestamp, duration_ms, status, fallback_tiers_used...).
    # A second _log_metrics here previously emitted a *sparse* dict (only
    # request_id/error_subcategory/start_tier/tiers_tried/elapsed_ms) missing the
    # NOT NULL `ts`/`timestamp` and the `duration_ms`/`fallback_tiers_used` keys
    # that db._build_request_row reads. One sparse dict in a flush batch made the
    # whole batch INSERT fail and rollback → hermes_logs.nv_requests stayed empty
    # (~96 rows on 06-24, only 6 landed). error_detail file above is unaffected.
    # Removing this duplicate restores DB persistence without losing event signal.

    # ─── R1648c: nv→ms fallback (5key 全坏兜底, 仅 glm5_2_nv) ─────────────
    # nv 链 all_keys_exhausted 后, 若该 model 走 ms fallback 且非全 429 (429 是 key 级限流,
    # ms_gw 不增加 key 池, 切 ms 无意义, 让客户端退避): 试 POST ms_gw. 成 → 返 ms 成功 result
    # (resp 指向 ms_gw openai 流, handler 层原样 stream/collect, /v1/messages 再经 oai_to_anth 转).
    # 败 → 记 nv breaker failure (连续 N=15 次后 OPEN, 下次直走 ms 省 ~120s 链预算).
    # breaker 只记 nv 链失败, 不记 ms 成败 (ms 是兜底, 不参与 breaker 健康判定).
    if (NVU_MS_FALLBACK_ENABLED and NVU_MS_FALLBACK_URL
            and mapped_model in NVU_MS_FALLBACK_MODELS
            and not final_result.all_429):
        _log("NV-MS-FB-ATTEMPT", f"nv chain all_keys_exhausted for {mapped_model} "
                                f"(req={request_id}), attempting ms_gw fallback "
                                f"(breaker={nv_breaker.breaker_state()[0]})")
        ok, ms_result = _ms_fallback_request(oai_body, mapped_model, request_id, metrics, t_start)
        if ok and ms_result is not None:
            # nv 链探活成功路径 (经 ms 兜底拿到响应) — 不改 breaker 状态:
            # 真正的 nv 探活只在 HALF_OPEN 时 nv 链本身成功才 record_nv_success.
            # 这里是 ms 兜底成功, nv 仍失败, 仍记 failure (累积到 OPEN).
            nv_breaker.record_nv_failure()
            _log("NV-MS-FB-SERVED", f"ms_gw served {mapped_model} fallback (req={request_id}), "
                                    f"nv breaker recorded failure (state={nv_breaker.breaker_state()[0]})")
            return ms_result
        # ms 也失败 — 记 nv failure (累积到 OPEN), 返 nv final_result (502)
        nv_breaker.record_nv_failure()
        _log("NV-MS-FB-FAIL", f"ms_gw fallback also failed for {mapped_model} (req={request_id}), "
                             f"returning nv 502 (breaker={nv_breaker.breaker_state()[0]})")

    # ─── R1673: 超大 input nv 链 hang 失败 → 记 big_input breaker failure ───
    # 超大 input 的系统性 hang (stream_first_byte_timeout / stream_no_content_gap / empty_200 /
    # all_keys_exhausted) 累计; 达 N=3 → OPEN cooldown 180s, 下次超大 input 直走 ms 省 ~115s.
    # 全 429 是 key 级限流 (非 hang), 不计入 big_input breaker (走 nv_breaker 维度).
    _bi_input = metrics.get("total_input_chars", 0) or 0
    if (big_input_breaker.is_big_input(_bi_input)
            and mapped_model in NVU_MS_FALLBACK_MODELS
            and not final_result.all_429):
        if final_result.empty_200:
            _bi_err = "empty_200"
        else:
            _bi_err = "all_keys_exhausted"  # 涵盖 stream_first_byte_timeout / stream_no_content_gap
        big_input_breaker.record_big_input_failure(_bi_err)
        _log("NV-BIGINPUT-FAIL", f"big_input nv hang for {mapped_model} input={_bi_input}c "
                                 f"err={_bi_err} (req={request_id}), "
                                 f"breaker={big_input_breaker.big_input_breaker_state()}")

    return final_result
