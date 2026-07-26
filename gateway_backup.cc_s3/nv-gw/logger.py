#!/usr/bin/env python3
"""Structured logging for NV-unified proxy: console + daily log files + JSON metrics + error details."""
import json
import os
import time
import datetime

from .config import LOG_DIR, _log_lock, _metrics_lock, _error_detail_lock
from . import db  # R40: enqueue metrics to postgres (best-effort, async)

LOG_RETENTION_DAYS = int(os.environ.get("LOG_RETENTION_DAYS", "7"))


def _cleanup_old_logs():
    """Delete log files older than LOG_RETENTION_DAYS on startup."""
    try:
        if not os.path.isdir(LOG_DIR):
            return
        cutoff = time.time() - LOG_RETENTION_DAYS * 86400
        for fname in os.listdir(LOG_DIR):
            fpath = os.path.join(LOG_DIR, fname)
            if fname.endswith(".log") or fname.endswith(".jsonl"):
                try:
                    if os.path.getmtime(fpath) < cutoff:
                        os.remove(fpath)
                except OSError:
                    pass
    except Exception as e:
        print(f"[LOG-CLEANUP] Warning: cleanup failed: {e}", flush=True)

# Run cleanup once on module import
_cleanup_old_logs()


def _log(level, msg):
    ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:10]
    line = f"[{ts}] [{level}] {msg}"
    print(line, flush=True)
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        date = datetime.date.today().isoformat()
        with _log_lock, open(os.path.join(LOG_DIR, f"nv_proxy.{date}.log"), "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def _log_metrics(entry):
    """Write structured JSON metrics to nv_metrics.{date}.jsonl + enqueue to DB (R40)."""
    rid = entry.get("request_id") if isinstance(entry, dict) else None
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        date = datetime.date.today().isoformat()
        with _metrics_lock, open(os.path.join(LOG_DIR, f"nv_metrics.{date}.jsonl"), "a") as f:
            f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
    except Exception as e:
        # R845: make JSONL write failures visible (was silent `pass` — hid metrics gap root cause)
        print(f"[METRICS-ERR] jsonl write failed rid={rid}: {e!r}", flush=True)
    # R40: best-effort async postgres persistence (non-blocking, file log is ground truth)
    try:
        db.enqueue_metrics(entry)
    except Exception as e:
        # R845: make enqueue failures visible (was silent `pass`)
        print(f"[METRICS-ERR] db enqueue failed rid={rid}: {e!r}", flush=True)


def _log_error_detail(detail):
    """Write detailed error info to nv_error_detail.{date}.jsonl."""
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        date = datetime.date.today().isoformat()
        with _error_detail_lock, open(os.path.join(LOG_DIR, f"nv_error_detail.{date}.jsonl"), "a") as f:
            f.write(json.dumps(detail, ensure_ascii=False, default=str) + "\n")
    except Exception:
        pass


# ─── Roc2NN R2306 (openclaw2 Task 1, 方向 3) field-passage dump ──────────
# Temp observation-only probe: record the shape of the incoming anthropic
# /v1/messages body vs the converted OpenAI body, so openclaw2 can see which
# anthropic-only fields (cache_control / thinking / context_management /
# output_config / metadata) anth_to_oai drops or rewrites. No conversion logic
# is touched here — this only writes a JSONL summary. Caller-gated: callers
# pass caller=openclaw2 only so the file stays focused. Remove this block +
# the call site in handlers.py once Task 1 direction 3 is concluded.
_FIELD_PASSAGE_LOCK = os.environ.get("_ROC2_FIELD_PASSAGE_LOCK", "")
if not _FIELD_PASSAGE_LOCK:
    import threading
    _FIELD_PASSAGE_LOCK = threading.Lock()


def _anth_field_summary(anth_body):
    """Shape-only summary of an anthropic Messages request body — no full text."""
    summary = {}
    if not isinstance(anth_body, dict):
        return {"_not_dict": type(anth_body).__name__}
    summary["top_keys"] = sorted(anth_body.keys())

    # anthropic-only top-level fields of interest (透传/丢失 target)
    for fld in ("thinking", "context_management", "output_config",
                "metadata", "stop_sequences", "tool_choice", "cache_control"):
        if fld in anth_body:
            v = anth_body[fld]
            summary[f"top_{fld}"] = {
                "type": type(v).__name__,
                "value": v if not isinstance(v, (dict, list)) else None,
                "keys": sorted(v.keys()) if isinstance(v, dict) else None,
                "len": len(v) if isinstance(v, (list, str)) else None,
            }

    # system: str or list-of-blocks; flag cache_control presence
    sysb = anth_body.get("system")
    sys_info = {"type": type(sysb).__name__}
    if isinstance(sysb, str):
        sys_info["len"] = len(sysb)
        sys_info["has_cache_control"] = False
    elif isinstance(sysb, list):
        sys_info["block_types"] = sorted({b.get("type", "?") for b in sysb if isinstance(b, dict)})
        sys_info["cache_control_blocks"] = sum(
            1 for b in sysb if isinstance(b, dict) and "cache_control" in b)
        sys_info["cache_control_values"] = [
            b.get("cache_control") for b in sysb
            if isinstance(b, dict) and "cache_control" in b]
    summary["system"] = sys_info

    # messages: scan blocks for cache_control / thinking / tool_use / image
    msgs = anth_body.get("messages", [])
    m_info = {"num": len(msgs), "roles": [], "block_type_counts": {},
              "cache_control_blocks": 0, "thinking_blocks": 0,
              "tool_use_blocks": 0, "image_blocks": 0}
    for m in msgs:
        if not isinstance(m, dict):
            continue
        m_info["roles"].append(m.get("role", "?"))
        c = m.get("content")
        if isinstance(c, list):
            for b in c:
                if not isinstance(b, dict):
                    continue
                bt = b.get("type", "?")
                m_info["block_type_counts"][bt] = m_info["block_type_counts"].get(bt, 0) + 1
                if "cache_control" in b:
                    m_info["cache_control_blocks"] += 1
                if bt == "thinking":
                    m_info["thinking_blocks"] += 1
                if bt == "tool_use":
                    m_info["tool_use_blocks"] += 1
                if bt == "image":
                    m_info["image_blocks"] += 1
        elif isinstance(c, str):
            m_info["block_type_counts"]["_str"] = m_info["block_type_counts"].get("_str", 0) + 1
    summary["messages"] = m_info

    # tools: count + whether tool defs carry cache_control
    tools = anth_body.get("tools", [])
    summary["tools"] = {
        "num": len(tools) if isinstance(tools, list) else None,
        "with_cache_control": sum(1 for t in tools if isinstance(t, dict) and "cache_control" in t)
        if isinstance(tools, list) else None,
    }
    return summary


def _oai_field_summary(oai_body):
    """Shape-only summary of the converted OpenAI body."""
    summary = {}
    if not isinstance(oai_body, dict):
        return {"_not_dict": type(oai_body).__name__}
    summary["top_keys"] = sorted(oai_body.keys())
    summary["has_system"] = any(m.get("role") == "system" for m in oai_body.get("messages", [])
                                if isinstance(m, dict))
    summary["num_messages"] = len(oai_body.get("messages", []))
    summary["num_tools"] = len(oai_body.get("tools", []))
    # anthropic-only fields that should NEVER appear in a clean OAI body —
    # if they do, anth_to_oai leaked them through verbatim (NVCF may reject).
    for fld in ("cache_control", "thinking", "context_management",
                "output_config", "metadata"):
        hits = 0
        for m in oai_body.get("messages", []):
            if isinstance(m, dict) and fld in m:
                hits += 1
            c = m.get("content") if isinstance(m, dict) else None
            if isinstance(c, list):
                hits += sum(1 for b in c if isinstance(b, dict) and fld in b)
        if hits:
            summary[f"leaked_{fld}"] = hits
    return summary


def log_field_passage(caller, request_id, anth_body, oai_body):
    """Write one JSONL record: anthropic-in shape vs openai-out shape.
    Gated to caller=='openclaw2' by the call site; kept self-contained so it's
    trivial to remove (delete call site + this block) after Task 1 dir 3."""
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        date = datetime.datetime.today().isoformat()
        rec = {
            "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "req": request_id,
            "caller": caller,
            "anth": _anth_field_summary(anth_body),
            "oai": _oai_field_summary(oai_body),
        }
        with _FIELD_PASSAGE_LOCK:
            with open(os.path.join(LOG_DIR, f"hm_field_passage.{date}.jsonl"), "a") as f:
                f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
    except Exception:
        # observation probe must never break a request
        pass
