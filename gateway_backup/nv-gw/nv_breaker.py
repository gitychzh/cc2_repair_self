#!/usr/bin/env python3
"""R1648c: nv→ms fallback circuit breaker for nv_gw.

Mirrors cc4101/gateway/circuit.py (R824d). When the NVCF 5key×mode chain for
glm5_2_nv is in a sustained degraded state (all_keys_exhausted storm), every
request waits the full chain budget (~120s for 5 keys) before falling back to
ms_gw — wasting ~120s/req and hammering an already-sick NVCF. A circuit
breaker short-circuits the chain after N consecutive all_keys_exhausted
failures, routing straight to ms_gw for a cooldown, then re-probes nv once.

States:
  CLOSED   — nv chain healthy, tried first (normal flow).
  OPEN     — nv chain degraded, SKIPPED; ms_gw serves directly. Expires after
             NVU_MS_FALLBACK_SKIP_S into HALF_OPEN.
  HALF_OPEN— cooldown expired; is_ms_fallback_open() returns False so the next
             request probes the nv chain once. success → CLOSED, all_keys_exhausted
             → re-OPEN (cooldown re-armed).

Only all_keys_exhausted counts (tier-chain-level failure). Per-key SSL/timeout
errors that the chain recovers from do NOT trip the breaker — those are the
chain's job. client_4xx (request-level) never reaches here.
"""
import threading
import time
from collections import deque
import os

from .config import (
    NVU_MS_FALLBACK_FAIL_THRESHOLD,
    NVU_MS_FALLBACK_SKIP_S,
)

# R1771: time-windowed failure-rate semantics. Old "consecutive N failures" was
# reset to 0 by interspersed successes, so under glm5_2_nv's >80% success rate the
# _fail_count oscillated 0<->1 forever and the breaker NEVER tripped -> death loop.
# Now: keep recent failure timestamps in a deque (window W); record_nv_success does
# NOT wipe history (only HALF_OPEN probe success does); trip OPEN when window count
# >= threshold. NVU_MS_FALLBACK_FAIL_THRESHOLD lowered 15->5 via env in compose.
NVU_BREAKER_WINDOW_S = float(os.environ.get('NVU_BREAKER_WINDOW_S', '300'))

_lock = threading.Lock()
_fail_count = 0          # derived from window deque length (kept for state-machine compat)
_open_until = 0.0        # monotonic deadline; 0 = CLOSED. 0 < expired = HALF_OPEN.
_fail_timestamps = deque()  # R1771: monotonic timestamps of failures within window


def is_ms_fallback_open():
    """True iff the nv chain should be SKIPPED right now (circuit OPEN, within
    cooldown). Returns False when CLOSED or HALF_OPEN (probe allowed)."""
    with _lock:
        if _open_until == 0.0:
            return False
        return time.monotonic() < _open_until


def record_nv_success():
    """Call when an nv-chain attempt succeeds (chain returned real resp).
    Closes the circuit (CLOSED). R1771: success NO LONGER wipes failure history —
    that was the death-loop root cause (interspersed successes reset _fail_count to
    0 so the breaker never tripped). Only a HALF_OPEN probe success fully clears the
    window. On CLOSED success we just leave the deque; old failures expire by time."""
    global _fail_count, _open_until
    with _lock:
        # do NOT clear _fail_timestamps here
        _open_until = 0.0
        _fail_count = len(_fail_timestamps)


def record_nv_failure():
    """Call when the nv chain fails at chain-level (all_keys_exhausted) OR (R1719/R1771)
    a mid-stream soft-fail (zombie/no_content_gap/total_deadline/first_byte_timeout) on
    glm5_2_nv. R1771: time-windowed failure-rate semantics. Push timestamp, prune older
    than NVU_BREAKER_WINDOW_S, trip OPEN when window count >= threshold. Interspersed
    successes no longer reset the count, so a sporadically-failing degraded chain will
    eventually trip — fixing the (CLOSED,1,0) oscillation that kept the breaker shut.
    HALF_OPEN / OPEN: a failure re-arms the cooldown immediately (probe failed)."""
    global _fail_count, _open_until
    with _lock:
        now = time.monotonic()
        cutoff = now - NVU_BREAKER_WINDOW_S
        while _fail_timestamps and _fail_timestamps[0] < cutoff:
            _fail_timestamps.popleft()
        _fail_timestamps.append(now)
        _fail_count = len(_fail_timestamps)
        if _open_until != 0.0:
            # already OPEN or HALF_OPEN (expired) — re-arm cooldown
            _open_until = now + NVU_MS_FALLBACK_SKIP_S
            _fail_timestamps.clear()
            _fail_count = NVU_MS_FALLBACK_FAIL_THRESHOLD
            return
        if _fail_count >= NVU_MS_FALLBACK_FAIL_THRESHOLD:
            _open_until = now + NVU_MS_FALLBACK_SKIP_S
            _fail_timestamps.clear()
            _fail_count = NVU_MS_FALLBACK_FAIL_THRESHOLD


def breaker_state():
    """Debug snapshot: (state, fail_count, seconds_left)."""
    with _lock:
        now = time.monotonic()
        if _open_until == 0.0:
            return "CLOSED", _fail_count, 0
        if now >= _open_until:
            return "HALF_OPEN", _fail_count, 0
        return "OPEN", _fail_count, int(_open_until - now)
