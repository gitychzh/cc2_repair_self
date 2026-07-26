#!/usr/bin/env python3
"""Per-tier persistent round-robin counter state machine.

Extracted from config.py (Reng modularization). Logic is byte-for-byte
equivalent to the original; no behavioral change. State persists to
rr_counter.json (bind-mounted) so key rotation survives restarts.

unify-nv (2026-06-30): tier key 从 deepseek_hm_nv 改为 dsv4p_nv; rr_counter.json
的 key 从 hm_nv_deepseek 改为 nv_dsv4p. 旧 key 由 _OLD_RR_KEY_MAP 自动迁移,
计数器值保留不归零.

Public API (re-exported by config.py for backward compatibility):
  _next_nv_key(tier_model) -> int   advance & return next key index
  _save_rr_counter()               flush counter to disk (atexit/signal)
"""
import atexit
import json
import os
import signal as _signal
import sys
import threading
import time

from .config import LOG_DIR, NVU_NUM_KEYS

# ─── Per-tier persistent round-robin counter ───────────────────────────────
_RR_COUNTER_FILE = os.path.join(LOG_DIR, "rr_counter.json")
_vk_rr_counter = {}
_vk_rr_lock = threading.Lock()

# 3model (2026-07-01): 三模型各自独立 RR counter key.
#   kimi_nv → nv_kimi, dsv4p_nv → nv_dsv4p.
# R704: 已下架 tier 的 counter key 移除.
_TIER_RR_KEYS = {
    "kimi_nv": "nv_kimi",
    "dsv4p_nv": "nv_dsv4p",
    "glm5_2_nv": "nv_glm5_2",  # R1621c: 独立 counter (原共用 nv_dsv4p 被干扰致 key 顺序跳位)
}

# 旧 rr_counter.json key 自动迁移到新 key (计数器值保留, 不归零)
# 3model: legacy kimi keys 不再迁移到 dsv4p (kimi 现在是独立 tier), 迁到 nv_kimi.
_OLD_RR_KEY_MAP = {
    "nv_deepseek": "nv_dsv4p",
    "hm_nv_deepseek": "nv_dsv4p",  # unify-nv 前的 key, 迁移到 nv_dsv4p
    "nv_dsv4p": "nv_dsv4p",
    "nv_kimi": "nv_kimi",          # 3model: kimi 独立 tier
    "hm_nv_kimi": "nv_kimi",
}

def _log_migration(msg: str) -> None:
    """Log counter migration events."""
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        date = time.strftime("%Y-%m-%d")
        with open(os.path.join(LOG_DIR, f"nv_proxy.{date}.log"), "a") as f:
            ts = time.strftime("%H:%M:%S")
            f.write(f"[{ts}] [MIGRATE] {msg}\n")
    except Exception:
        pass

def _save_rr_counter() -> None:
    """Persist counters to disk atomically."""
    try:
        tmp = "%s.tmp.%d.%d" % (_RR_COUNTER_FILE, os.getpid(), threading.get_ident())
        with open(tmp, "w") as f:
            json.dump(_vk_rr_counter, f)
        os.replace(tmp, _RR_COUNTER_FILE)
    except Exception as e:
        print(f"[NV-RR] WARN could not save: {e}", file=sys.stderr, flush=True)

def _load_rr_counter() -> None:
    """Restore counters from disk at startup, migrating old key names."""
    try:
        with open(_RR_COUNTER_FILE, "r") as f:
            raw = f.read().strip()
        if not raw:
            return
        saved = json.loads(raw)
        if isinstance(saved, dict):
            migrated = False
            for k, v in saved.items():
                if isinstance(k, str) and isinstance(v, int) and v >= 0:
                    new_key = _OLD_RR_KEY_MAP.get(k, k)
                    if new_key != k:
                        _vk_rr_counter[new_key] = v
                        migrated = True
                    else:
                        _vk_rr_counter[k] = v
            if migrated:
                _log_migration(f"Migrated old RR keys → nv_dsv4p: {saved} → {_vk_rr_counter}")
                _save_rr_counter()
            print(f"[NV-RR] restored from {_RR_COUNTER_FILE}: {_vk_rr_counter}", file=sys.stderr, flush=True)
    except FileNotFoundError:
        pass
    except (json.JSONDecodeError, ValueError) as e:
        print(f"[NV-RR] file corrupt ({e}); starting fresh", file=sys.stderr, flush=True)
    except Exception as e:
        print(f"[NV-RR] WARN could not load: {e}", file=sys.stderr, flush=True)

# Restore on import
_load_rr_counter()

def _peek_nv_key(tier_model: str) -> int:
    """R838b: peek current RR position WITHOUT advancing (read-only). 用于 dispatch 决定链路."""
    rr_key = _TIER_RR_KEYS.get(tier_model, "nv_dsv4p")
    with _vk_rr_lock:
        counter = _vk_rr_counter.get(rr_key, 0)
        return counter % NVU_NUM_KEYS


def _next_nv_key(tier_model: str) -> int:
    """Per-tier sequential round-robin: each tier tracks its own key position."""
    rr_key = _TIER_RR_KEYS.get(tier_model, "nv_dsv4p")
    with _vk_rr_lock:
        counter = _vk_rr_counter.get(rr_key, 0)
        key_idx = counter % NVU_NUM_KEYS
        _vk_rr_counter[rr_key] = counter + 1
        _save_rr_counter()
        return key_idx

# Signal handlers for clean shutdown
def _flush_and_exit(signum, _frame):
    _save_rr_counter()
    raise SystemExit(128 + signum)

atexit.register(_save_rr_counter)
_signal.signal(_signal.SIGTERM, _flush_and_exit)
_signal.signal(_signal.SIGINT, _flush_and_exit)
