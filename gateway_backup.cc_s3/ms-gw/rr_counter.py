#!/usr/bin/env python3
"""Per-model persistent round-robin counter for ms_gw.

Drives the 2D (variant, key) selection: N → (variant_idx=(N//NUM_KEYS)%NUM_VARIANTS,
key_idx=N%NUM_KEYS). N persists to rr_counter.json so rotation survives restarts.

Design (抄 nv_40006_uni/rr_counter.py, 简化为单 model):
  - _next_ms_key(model) → int: advance N by 1, return key_idx = (N % NUM_KEYS)
    NOTE: caller computes variant_idx from the same N.
  - 持久化: tmp + os.replace 原子写, atexit + SIGTERM/SIGINT flush.
  - SIGKILL/OOM: atexit 不触发, 可能丢 1-2 偏移 — 不影响正确性 (n+1 仍连续).
"""
import atexit
import json
import os
import signal as _signal
import sys
import threading
import time

from .config import LOG_DIR, NUM_KEYS, _MODEL_RR_KEYS

_RR_COUNTER_FILE = os.path.join(LOG_DIR, "rr_counter.json")
_rr_counter = {}
_rr_lock = threading.Lock()


def _save_rr_counter() -> None:
    """Persist counters to disk atomically."""
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        tmp = "%s.tmp.%d.%d" % (_RR_COUNTER_FILE, os.getpid(), threading.get_ident())
        with open(tmp, "w") as f:
            json.dump(_rr_counter, f)
        os.replace(tmp, _RR_COUNTER_FILE)
    except Exception as e:
        print(f"[MS-RR] WARN could not save: {e}", file=sys.stderr, flush=True)


def _load_rr_counter() -> None:
    """Restore counters from disk at startup."""
    try:
        with open(_RR_COUNTER_FILE, "r") as f:
            raw = f.read().strip()
        if not raw:
            return
        saved = json.loads(raw)
        if isinstance(saved, dict):
            for k, v in saved.items():
                if isinstance(k, str) and isinstance(v, (int, float)) and v >= 0:
                    _rr_counter[k] = int(v)
        print(f"[MS-RR] restored from {_RR_COUNTER_FILE}: {_rr_counter}",
              file=sys.stderr, flush=True)
    except FileNotFoundError:
        pass
    except (json.JSONDecodeError, ValueError) as e:
        print(f"[MS-RR] file corrupt ({e}); starting fresh", file=sys.stderr, flush=True)
    except Exception as e:
        print(f"[MS-RR] WARN could not load: {e}", file=sys.stderr, flush=True)


_load_rr_counter()


def _next_ms_n(model: str) -> int:
    """Advance and return the current N for this model.

    Returns the N value to use for this request (caller computes:
      variant_idx = (N // NUM_KEYS) % NUM_VARIANTS
      key_idx     = N % NUM_KEYS
    )
    Counter N is advanced by 1 each call (persisted immediately).
    """
    rr_key = _MODEL_RR_KEYS.get(model, "ms_glm5_2")
    with _rr_lock:
        n = _rr_counter.get(rr_key, 0)
        _rr_counter[rr_key] = n + 1
        _save_rr_counter()
        return n


def _get_rr_counter_snapshot() -> dict:
    """Return a copy of the counter state (for /health)."""
    with _rr_lock:
        return dict(_rr_counter)


# Signal handlers for clean shutdown
def _flush_and_exit(signum, _frame):
    _save_rr_counter()
    raise SystemExit(128 + signum)


atexit.register(_save_rr_counter)
_signal.signal(_signal.SIGTERM, _flush_and_exit)
_signal.signal(_signal.SIGINT, _flush_and_exit)
