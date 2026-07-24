#!/usr/bin/env python3
"""429 per-key cooldown state machine.

Extracted from config.py (Reng modularization). Logic is byte-for-byte
equivalent to the original; no behavioral change. Tracks per-(tier,key)
429 cooldown with exponential backoff (capped 30s) and an all-tier
cooldown for the TIER_COOLDOWN_S window when every key in a tier 429s.

Public API (re-exported by config.py for backward compatibility):
  is_key_cooling(tier_model, key_idx) -> bool
  mark_key_cooling(tier_model, key_idx, duration_s=None)
  reset_key429_count(tier_model, key_idx)
  KEY_COOLDOWN_S, TIER_COOLDOWN_S
"""
import os
import threading
import time

KEY_COOLDOWN_S = float(os.environ.get("KEY_COOLDOWN_S", "15.0"))
TIER_COOLDOWN_S = float(os.environ.get("TIER_COOLDOWN_S", "15"))  # R7: when all keys in a tier get 429, mark tier cooling for this duration

_key_cooldown_map = {}
_key_cooldown_lock = threading.Lock()

_key429_count = {}
_key429_lock = threading.Lock()

def is_key_cooling(tier_model, key_idx):
    """Check if a key is in cooldown (recently got 429)."""
    with _key_cooldown_lock:
        cooldown_until = _key_cooldown_map.get((tier_model, key_idx), 0)
        if cooldown_until > time.monotonic():
            return True
        return False

def mark_key_cooling(tier_model, key_idx, duration_s=None):
    """Mark a key as cooling after receiving 429. Exponential backoff, capped at 30s."""
    with _key429_lock:
        _key429_count[(tier_model, key_idx)] = _key429_count.get((tier_model, key_idx), 0) + 1
        consecutive = _key429_count[(tier_model, key_idx)]
    import math
    effective_duration = min(KEY_COOLDOWN_S * (2 ** (consecutive - 1)), 30) if duration_s is None else duration_s
    with _key_cooldown_lock:
        _key_cooldown_map[(tier_model, key_idx)] = time.monotonic() + effective_duration

def reset_key429_count(tier_model, key_idx):
    """Reset consecutive 429 count when a key succeeds."""
    with _key429_lock:
        _key429_count.pop((tier_model, key_idx), None)

# --- R764: per-key (cross-tier) auth-fail state ---
# 401/403 auth failed is NVAPI key-level failure (revoked/invalid), across ALL tiers/models.
# Pre-fix: mark_key_cooling(tier, key) is per-(tier,key) -> k3 cooldown in dsv4p_nv
#       does not affect glm5_2_nv, so each tier independently hits k3 403 (wastes ~1s each).
# Fix: separate per-key auth-fail map (cross-tier). One 403 -> skip that key in ALL tiers.
# Auth failures don't self-heal, so longer cooldown (default 600s=10min, env tunable).
KEY_AUTHFAIL_COOLDOWN_S = float(os.environ.get("KEY_AUTHFAIL_COOLDOWN_S", "600"))
_key_authfail_map = {}  # key_idx -> expiry (monotonic)
_key_authfail_lock = threading.Lock()


def is_key_auth_failed(key_idx):
    """Check if a key has auth-failed (401/403) recently, across ALL tiers."""
    with _key_authfail_lock:
        expiry = _key_authfail_map.get(key_idx, 0)
        if expiry > time.monotonic():
            return True
        return False


def mark_key_auth_failed(key_idx, duration_s=None):
    """Mark a key as auth-failed (401/403) across ALL tiers.

    Auth failure is per-key (NVAPI key revoked/invalid), not per-tier.
    Cooldown longer than 429 (default 600s) since auth failures don't self-heal.
    """
    effective = KEY_AUTHFAIL_COOLDOWN_S if duration_s is None else duration_s
    with _key_authfail_lock:
        _key_authfail_map[key_idx] = time.monotonic() + effective

# --- R814: tier-level DEGRADED short-circuit (R1421 port from HM2) ---
# NVCF function 3b9748d8 (glm5_2_nv) 周期性 DEGRADED, 返回 400 non-cycling.
# 现有 per-key cooldown 只抓 429, 抓不住 DEGRADED (tier 级故障, 所有 key 都 400).
# 每 request 都打 NVCF 试一遍才 502 (0.6-1s 无谓探测 + 给已坏 function 加压).
# Fix: 检测到 400 DEGRADED 后 mark tier degraded, 冷却期内 tier 入口直接 skip 不打 NVCF.
# glm5_2_nv mode chain (_glm52_single_attempt) 429/400 时用 mark_tier_degraded 标 tier.
TIER_DEGRADED_COOLDOWN_S = float(os.environ.get("NVU_TIER_DEGRADED_COOLDOWN_S", "60"))
_tier_degraded_map = {}  # tier_model -> expiry (monotonic)
_tier_degraded_lock = threading.Lock()


def mark_tier_degraded(tier_model, duration_s=None):
    """Mark a tier as DEGRADED (NVCF function degraded, all keys will 400). Tier-level, not per-key."""
    effective = TIER_DEGRADED_COOLDOWN_S if duration_s is None else float(duration_s)
    with _tier_degraded_lock:
        _tier_degraded_map[tier_model] = time.monotonic() + effective
    return effective


def is_tier_degraded(tier_model):
    """Check if a tier is in DEGRADED cooldown (recent NVCF 400 DEGRADED)."""
    with _tier_degraded_lock:
        expiry = _tier_degraded_map.get(tier_model, 0)
        if expiry > time.monotonic():
            return True
        # expired: clean up
        if tier_model in _tier_degraded_map:
            _tier_degraded_map.pop(tier_model, None)
        return False
