#!/usr/bin/env python3
"""R1673: big-input fast-fail breaker for nv_gw.

独立于 nv_breaker (R1648c 管"全 key 挂"). 本模块管"超大 input 系统性 hang":
NVCF glm5.2 对 ~250k+ chars (~8万 token) 的超大 input 会系统性 200-then-hang
(pexec 拖满 timeout 返 empty-200, integrate 200-then-hang), 每次 ~115s, CC
死循环重试同一个 283k 请求达 1h+ (DB 8 条同 input_chars 全 502).

数据锚点 (HM2 近6h):
  <250k 各档 SR 71-100%, 250-300k 桶 SR 骤降至 29.2% (24 请求 17 hang).
  283274 这个精确值 10 次全失败, max 115s.

机制: input>250k 且连续 N 次 NVCF hang 类失败 (stream_first_byte_timeout /
stream_no_content_gap / empty_200 / all_keys_exhausted) → OPEN, cooldown 内对
超大 input 直走 ms_gw fallback (复用 R1648c _ms_fallback_request), 不走 nv 链
省 ~115s/次. 成功一次 → CLOSED. 只对 glm5_2_nv (其他模型无 ms 对应).

与 nv_breaker 互补: nv_breaker 看"全 key 挂"(整体健康), big_input_breaker 看
"特定 input 段系统性坏"(按 input 维度). 两者可同时 OPEN, 互不干扰.
"""
import threading
import time
import os

NVU_BIG_INPUT_THRESHOLD = int(os.environ.get("NVU_BIG_INPUT_THRESHOLD", "250000"))
NVU_BIG_INPUT_FAIL_N = int(os.environ.get("NVU_BIG_INPUT_FAIL_N", "3"))
NVU_BIG_INPUT_COOLDOWN_S = int(os.environ.get("NVU_BIG_INPUT_COOLDOWN_S", "180"))
NVU_BIG_INPUT_MODELS = {m.strip() for m in
                        os.environ.get("NVU_BIG_INPUT_MODELS", "glm5_2_nv").split(",") if m.strip()}

# hang 类失败 (与 R1648c nv_breaker 的 all_keys_exhausted 不同: 这里按 input 维度,
# 任何让超大 input 卡住的 NVCF 失败都算)
_HANG_ERRORS = {
    "stream_first_byte_timeout",
    "stream_no_content_gap",
    "empty_200",
    "all_keys_exhausted",
    # R1673b: execute_request 返 success 但 handlers 层判 zombie (200+极少内容+stop)
    # 也是 NVCF 对超大 input 系统性坏的一种 (200-then-nothing 变体). 283k 实测多走此路.
    "zombie_empty_completion",
}

_lock = threading.Lock()
_fail_count = 0          # 连续超大 input hang 失败
_open_until = 0.0        # 0 = CLOSED; >0 未过期 = OPEN


def is_big_input(input_chars):
    """input 是否落入"超大"段 (>NVU_BIG_INPUT_THRESHOLD)."""
    return input_chars and input_chars > NVU_BIG_INPUT_THRESHOLD


def is_big_input_open():
    """True iff 大-input breaker OPEN (在 cooldown 内): 超大 input 直走 ms, 跳过 nv 链."""
    with _lock:
        if _open_until == 0.0:
            return False
        return time.monotonic() < _open_until


def record_big_input_failure(error_type):
    """超大 input 请求 nv 链 hang 失败 → 累计; 达 N 次 → OPEN cooldown."""
    if error_type not in _HANG_ERRORS:
        return
    global _fail_count, _open_until
    with _lock:
        now = time.monotonic()
        _fail_count += 1
        if _open_until != 0.0:
            # 已 OPEN/HALF_OPEN — re-arm
            _open_until = now + NVU_BIG_INPUT_COOLDOWN_S
            if _fail_count < NVU_BIG_INPUT_FAIL_N:
                _fail_count = NVU_BIG_INPUT_FAIL_N
            return
        if _fail_count >= NVU_BIG_INPUT_FAIL_N:
            _open_until = now + NVU_BIG_INPUT_COOLDOWN_S


def record_big_input_success():
    """超大 input 请求 nv 链成功 → CLOSED 重置 (HALF_OPEN probe 成功也调此)."""
    global _fail_count, _open_until
    with _lock:
        _fail_count = 0
        _open_until = 0.0


def big_input_breaker_state():
    """调试快照: (state, fail_count, seconds_left). 注意: docker exec 起新进程,
    看到的是 fresh 状态, 不是 live nv_gw 进程的真实状态 (同 R1648c nv_breaker 坑)."""
    with _lock:
        now = time.monotonic()
        if _open_until == 0.0:
            return "CLOSED", _fail_count, 0
        if now >= _open_until:
            return "HALF_OPEN", _fail_count, 0
        return "OPEN", _fail_count, int(_open_until - now)
