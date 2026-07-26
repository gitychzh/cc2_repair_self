#!/usr/bin/env python3
"""Structured logging: console + daily log files + JSON metrics + error details."""
import json
import os
import time
import datetime

from .config import LOG_DIR, LOG_RETENTION_DAYS, _log_lock, _metrics_lock, _error_detail_lock


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
                        print(f"[LOG-CLEANUP] Deleted old log: {fname}", flush=True)
                except OSError:
                    pass
    except Exception as e:
        print(f"[LOG-CLEANUP] Warning: cleanup failed: {e}", flush=True)


_cleanup_old_logs()


def _log(level, msg):
    ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:10]
    line = f"[{ts}] [{level}] {msg}"
    print(line, flush=True)
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        date = datetime.date.today().isoformat()
        with _log_lock, open(os.path.join(LOG_DIR, f"proxy.{date}.log"), "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def _log_metrics(entry):
    """Write structured JSON metrics to metrics.{date}.jsonl for optimization analysis."""
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        date = datetime.date.today().isoformat()
        with _metrics_lock, open(os.path.join(LOG_DIR, f"metrics.{date}.jsonl"), "a") as f:
            f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
    except Exception:
        pass


def _log_error_detail(detail):
    """Write detailed error info to error_detail.{date}.jsonl for root-cause analysis."""
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        date = datetime.date.today().isoformat()
        with _error_detail_lock, open(os.path.join(LOG_DIR, f"error_detail.{date}.jsonl"), "a") as f:
            f.write(json.dumps(detail, ensure_ascii=False, default=str) + "\n")
    except Exception:
        pass
