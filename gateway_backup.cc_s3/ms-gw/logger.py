#!/usr/bin/env python3
"""Structured logging for ms_gw: console + daily log + JSON metrics + error details.

R683: DB hook activated. _log_metrics now calls db.enqueue_metrics best-effort.
JSONL remains ground truth; DB is a convenience mirror for structured querying.
"""
import json
import os
import time
import datetime
import threading

from .config import LOG_DIR, LOG_RETENTION_DAYS

try:
    from . import db
    _DB_OK = True
except Exception:
    db = None
    _DB_OK = False

_log_lock = threading.Lock()
_metrics_lock = threading.Lock()
_error_detail_lock = threading.Lock()


def _cleanup_old_logs():
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
        print(f"[MS-LOG-CLEANUP] Warning: cleanup failed: {e}", flush=True)


_cleanup_old_logs()


def _log(level, msg):
    ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:10]
    line = f"[{ts}] [{level}] {msg}"
    print(line, flush=True)
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        date = datetime.date.today().isoformat()
        with _log_lock, open(os.path.join(LOG_DIR, f"ms_proxy.{date}.log"), "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def _log_metrics(entry):
    """Write structured JSON metrics to ms_metrics.{date}.jsonl + enqueue DB best-effort."""
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        date = datetime.date.today().isoformat()
        with _metrics_lock, open(os.path.join(LOG_DIR, f"ms_metrics.{date}.jsonl"), "a") as f:
            f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
    except Exception:
        pass
    # R683: best-effort DB mirror. Non-blocking; DB down → drops silently.
    if _DB_OK:
        try:
            db.enqueue_metrics(entry)
        except Exception:
            pass


def _log_error_detail(detail):
    """Write detailed error info to ms_error_detail.{date}.jsonl."""
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        date = datetime.date.today().isoformat()
        with _error_detail_lock, open(os.path.join(LOG_DIR, f"ms_error_detail.{date}.jsonl"), "a") as f:
            f.write(json.dumps(detail, ensure_ascii=False, default=str) + "\n")
    except Exception:
        pass
