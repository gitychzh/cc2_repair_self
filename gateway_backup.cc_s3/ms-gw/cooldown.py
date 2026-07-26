#!/usr/bin/env python3
"""Per-(variant, key) cooldown state machine for ms_gw.

Tracks cooldown for (variant_idx, key_idx) pairs with exponential backoff
(capped 30s). When all keys of a variant are cooling, the variant itself
is cooled (VARIANT_COOLDOWN_S). When all variants exhausted, the model
is cooled for ALL_EXHAUSTED_COOLDOWN_S.

MS 不返回 429 — cooldown 在这里由 empty_200/choices:null/error body 触发
(见 upstream.py 的检测逻辑), 不是 HTTP status code.

Public API:
  is_key_cooling(model, variant_idx, key_idx) -> bool
  mark_key_cooling(model, variant_idx, key_idx, duration_s=None)
  reset_key(model, variant_idx, key_idx)         # success → reset backoff
  is_variant_cooling(model, variant_idx) -> bool
  mark_variant_cooling(model, variant_idx, duration_s=None)
  is_all_exhausted_cooling(model) -> bool
  mark_all_exhausted(model, duration_s=None)
"""
import os
import threading
import time

KEY_COOLDOWN_S = float(os.environ.get("KEY_COOLDOWN_S", "60"))
VARIANT_COOLDOWN_S = float(os.environ.get("VARIANT_COOLDOWN_S", "30"))
ALL_EXHAUSTED_COOLDOWN_S = float(os.environ.get("ALL_EXHAUSTED_COOLDOWN_S", "30"))

_key_cooldown_map = {}     # (model, variant_idx, key_idx) -> monotonic deadline
_key_cooldown_lock = threading.Lock()

_key_fail_count = {}       # (model, variant_idx, key_idx) -> consecutive fail count
_key_fail_lock = threading.Lock()

_variant_cooldown_map = {} # (model, variant_idx) -> monotonic deadline
_variant_cooldown_lock = threading.Lock()

_all_exhausted_map = {}    # model -> monotonic deadline
_all_exhausted_lock = threading.Lock()


def is_key_cooling(model, variant_idx, key_idx):
    with _key_cooldown_lock:
        deadline = _key_cooldown_map.get((model, variant_idx, key_idx), 0)
        return deadline > time.monotonic()


def mark_key_cooling(model, variant_idx, key_idx, duration_s=None):
    """Mark a key as cooling. Exponential backoff, capped at 30s."""
    with _key_fail_lock:
        k = (model, variant_idx, key_idx)
        _key_fail_count[k] = _key_fail_count.get(k, 0) + 1
        consecutive = _key_fail_count[k]
    import math
    if duration_s is None:
        effective_duration = min(KEY_COOLDOWN_S * (2 ** (consecutive - 1)), KEY_COOLDOWN_S * 4)  # R844 F12: cap was 30, made KEY_COOLDOWN_S(60) ineffective
    else:
        effective_duration = duration_s
    with _key_cooldown_lock:
        _key_cooldown_map[(model, variant_idx, key_idx)] = time.monotonic() + effective_duration


def reset_key(model, variant_idx, key_idx):
    """Reset consecutive fail count when a key succeeds."""
    with _key_fail_lock:
        _key_fail_count.pop((model, variant_idx, key_idx), None)


def is_variant_cooling(model, variant_idx):
    with _variant_cooldown_lock:
        deadline = _variant_cooldown_map.get((model, variant_idx), 0)
        return deadline > time.monotonic()


def mark_variant_cooling(model, variant_idx, duration_s=None):
    d = duration_s if duration_s is not None else VARIANT_COOLDOWN_S
    with _variant_cooldown_lock:
        _variant_cooldown_map[(model, variant_idx)] = time.monotonic() + d


def is_all_exhausted_cooling(model):
    with _all_exhausted_lock:
        deadline = _all_exhausted_map.get(model, 0)
        return deadline > time.monotonic()


def mark_all_exhausted(model, duration_s=None):
    d = duration_s if duration_s is not None else ALL_EXHAUSTED_COOLDOWN_S
    with _all_exhausted_lock:
        _all_exhausted_map[model] = time.monotonic() + d


def snapshot():
    """Return cooldown snapshot for /health."""
    now = time.monotonic()
    with _key_cooldown_lock:
        keys_cooling = [f"{m}:v{v}k{k}" for (m, v, k), d in _key_cooldown_map.items() if d > now]
    with _variant_cooldown_lock:
        variants_cooling = [f"{m}:v{v}" for (m, v), d in _variant_cooldown_map.items() if d > now]
    with _all_exhausted_lock:
        models_exhausted = [m for m, d in _all_exhausted_map.items() if d > now]
    return {
        "keys_cooling": keys_cooling,
        "variants_cooling": variants_cooling,
        "models_all_exhausted": models_exhausted,
    }
