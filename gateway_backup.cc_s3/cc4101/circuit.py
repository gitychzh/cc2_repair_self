"""R824d: primary circuit breaker for cc4101.

When nv_gw (primary) is in a sustained degraded state (e.g. glm5_2_nv NVCF
empty200 storm), every request waits PRIMARY_HEADER_TIMEOUT (~48s) before
falling back to ms_gw — wasting ~48s/req and hammering an already-sick
upstream. A circuit breaker short-circuits primary after N consecutive
retryable failures, routing straight to fallback for a cooldown, then
re-probes primary. client_4xx errors do NOT count (they are per-request, not
upstream-health signals).

States:
  CLOSED   — primary healthy, tried first (normal flow).
  OPEN     — primary degraded, SKIPPED; fallback serves directly. Expires after
             CC4101_PRIMARY_SKIP_S into HALF_OPEN.
  HALF_OPEN— cooldown expired; is_primary_open() returns False so the next
             request probes primary once. success → CLOSED, retryable failure
             → re-OPEN (cooldown re-armed).
"""
import threading
import time
from collections import deque
import os

from .config import (
    CC4101_PRIMARY_FAIL_THRESHOLD,
    CC4101_PRIMARY_SKIP_S,
)

# R1771: time-windowed failure-rate semantics (mirrors nv_gw nv_breaker). Old
# "consecutive N failures, success resets to 0" was the death-loop root cause: under
# glm5_2_nv's >80% success rate _fail_count oscillated 0<->1 forever and the breaker
# NEVER tripped. Now: keep recent failure timestamps in a deque (window W); success
# does NOT wipe history (only HALF_OPEN probe success does); trip OPEN when window
# count >= threshold. CC4101_PRIMARY_FAIL_THRESHOLD lowered 8->3 via env in compose.
CC4101_BREAKER_WINDOW_S = float(os.environ.get('CC4101_BREAKER_WINDOW_S', '300'))

_lock = threading.Lock()
_fail_count = 0          # derived from window deque length
_open_until = 0.0        # monotonic deadline; 0 = CLOSED. 0 < expired = HALF_OPEN.
_fail_timestamps = deque()  # R1771: monotonic timestamps of failures within window


def is_primary_open():
    """True iff primary should be SKIPPED right now (circuit OPEN, within cooldown).
    Returns False when CLOSED or HALF_OPEN (probe allowed)."""
    with _lock:
        if _open_until == 0.0:
            return False
        return time.monotonic() < _open_until


def record_primary_success():
    """Call when primary returns a real response. Closes the circuit (CLOSED).
    R1771: success NO LONGER wipes failure history — that was the death-loop root
    cause. Only HALF_OPEN probe success fully clears the window. On CLOSED success
    we just leave the deque; old failures expire by time."""
    global _fail_count, _open_until
    with _lock:
        # do NOT clear _fail_timestamps here
        _open_until = 0.0
        _fail_count = len(_fail_timestamps)


def record_primary_failure():
    """Call when primary fails at the connection level (stall/timeout/reset/EOF) OR
    (R1719/R1771) when passthrough detects nv_gw api_error SSE. R1771: time-windowed
    failure-rate semantics — push timestamp, prune older than window, trip OPEN when
    count >= threshold. Interspersed successes no longer reset the count, so a
    sporadically-failing primary eventually trips — fixing the death loop.
    HALF_OPEN / OPEN: a failure re-arms the cooldown immediately (probe failed)."""
    global _fail_count, _open_until
    with _lock:
        now = time.monotonic()
        cutoff = now - CC4101_BREAKER_WINDOW_S
        while _fail_timestamps and _fail_timestamps[0] < cutoff:
            _fail_timestamps.popleft()
        _fail_timestamps.append(now)
        _fail_count = len(_fail_timestamps)
        if _open_until != 0.0:
            # already OPEN or HALF_OPEN (expired) — re-arm cooldown
            _open_until = now + CC4101_PRIMARY_SKIP_S
            _fail_timestamps.clear()
            _fail_count = CC4101_PRIMARY_FAIL_THRESHOLD
            return
        if _fail_count >= CC4101_PRIMARY_FAIL_THRESHOLD:
            _open_until = now + CC4101_PRIMARY_SKIP_S
            _fail_timestamps.clear()
            _fail_count = CC4101_PRIMARY_FAIL_THRESHOLD


def circuit_state():
    """Debug snapshot: (state, fail_count, seconds_left)."""
    with _lock:
        now = time.monotonic()
        if _open_until == 0.0:
            return "CLOSED", _fail_count, 0
        if now >= _open_until:
            return "HALF_OPEN", _fail_count, 0
        return "OPEN", _fail_count, int(_open_until - now)
