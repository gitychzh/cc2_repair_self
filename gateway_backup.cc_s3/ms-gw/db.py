#!/usr/bin/env python3
"""PostgreSQL persistence for ms_gw metrics — R683.

Mirrors nv_gw/gateway/db.py design (async queue + daemon thread + batch INSERT).
Best-effort: DB down → queue fills → entries dropped. JSONL (logger.py) remains
ground truth.

Schema: ms_requests table (host_machine + normalized_backend_model added vs
the legacy jsonl-importer schema). Created by postgres/hermes-logs-schema.sql.
"""
import os
import queue
import threading
import time
import datetime

try:
    import psycopg2
    from psycopg2.extras import execute_values
    _HAS_PSYCOPG = True
except ImportError:
    psycopg2 = None
    execute_values = None
    _HAS_PSYCOPG = False

# ─── Configuration (env-driven, per-machine) ──────────────────────────────
DB_ENABLED = os.environ.get("MSU_DB_ENABLED", "0") == "1"
DB_HOST = os.environ.get("MSU_DB_HOST", "logs_db")
DB_PORT = int(os.environ.get("MSU_DB_PORT", "5432"))
DB_USER = os.environ.get("MSU_DB_USER", "litellm")
DB_PASSWORD = os.environ.get("MSU_DB_PASSWORD", "")
DB_NAME = os.environ.get("MSU_DB_NAME", "hermes_logs")

FLUSH_INTERVAL_S = float(os.environ.get("MSU_DB_FLUSH_INTERVAL_S", "2"))
FLUSH_BATCH = int(os.environ.get("MSU_DB_FLUSH_BATCH", "50"))
QUEUE_MAX = int(os.environ.get("MSU_DB_QUEUE_MAX", "2000"))

HOST_MACHINE = os.environ.get("MSU_HOST_MACHINE") or os.environ.get("HOSTNAME") or "unknown"

# ─── Queue + worker ───────────────────────────────────────────────────────
_queue = queue.Queue(maxsize=QUEUE_MAX)
_worker_thread = None
_worker_stop = threading.Event()
_conn = None
_conn_lock = threading.Lock()
_last_health_check = 0.0


def _get_conn():
    global _conn
    if not _HAS_PSYCOPG or not DB_ENABLED:
        return None
    with _conn_lock:
        if _conn is not None:
            try:
                with _conn.cursor() as cur:
                    cur.execute("SELECT 1")
                return _conn
            except Exception:
                try:
                    _conn.close()
                except Exception:
                    pass
                _conn = None
        try:
            _conn = psycopg2.connect(
                host=DB_HOST, port=DB_PORT, user=DB_USER,
                password=DB_PASSWORD, dbname=DB_NAME,
                connect_timeout=5,
            )
            _conn.autocommit = False
            return _conn
        except Exception as e:
            now = time.time()
            global _last_health_check
            if now - _last_health_check > 60:
                print(f"[MS-DB] connect failed: {e}", flush=True)
                _last_health_check = now
            _conn = None
            return None


def _worker_loop():
    while not _worker_stop.is_set():
        try:
            batch = [_queue.get(timeout=FLUSH_INTERVAL_S)]
        except queue.Empty:
            continue
        while len(batch) < FLUSH_BATCH:
            try:
                batch.append(_queue.get_nowait())
            except queue.Empty:
                break
        _flush_batch(batch)


def _normalize_backend_model(bm):
    """Normalize the 10 ModelScope typo-variants to a canonical form for grouping.

    Variants are intentionally mixed-case (ZHIPUAI/GLm-5.2 etc.) for rotation;
    DB grouping uses the upper-cased form. Original preserved in backend_model.
    """
    if not bm:
        return None
    return bm.upper()


def _build_request_row(m):
    ts_ms = m.get("ts")
    ts = None
    if ts_ms is not None:
        try:
            ts = datetime.datetime.fromtimestamp(ts_ms / 1000.0, tz=datetime.timezone.utc)
        except Exception:
            ts = None
    return (
        m.get("request_id"),
        ts,
        ts_ms,
        HOST_MACHINE,
        m.get("caller"),
        m.get("agent_model"),
        m.get("backend"),
        m.get("backend_model"),
        _normalize_backend_model(m.get("backend_model")),
        m.get("is_stream"),
        m.get("variant_idx"),
        m.get("key_idx"),
        m.get("cycle_attempts_before_success"),
        m.get("status"),
        m.get("resp_status") or m.get("error_status"),
        m.get("duration_ms", 0),
        m.get("bytes_relayed"),
        m.get("error_type"),
        m.get("error_message"),
    )


_INSERT_SQL = """INSERT INTO ms_requests
    (request_id, ts, ts_ms, host_machine, caller, agent_model, backend,
     backend_model, normalized_backend_model, is_stream, variant_idx, key_idx,
     cycle_attempts, status, resp_status, duration_ms, bytes_relayed,
     error_type, error_message)
    VALUES %s
    ON CONFLICT (request_id) DO UPDATE SET
      status=EXCLUDED.status,
      duration_ms=EXCLUDED.duration_ms,
      error_type=EXCLUDED.error_type,
      error_message=EXCLUDED.error_message,
      backend_model=EXCLUDED.backend_model,
      normalized_backend_model=EXCLUDED.normalized_backend_model,
      variant_idx=EXCLUDED.variant_idx,
      key_idx=EXCLUDED.key_idx,
      resp_status=EXCLUDED.resp_status,
      bytes_relayed=EXCLUDED.bytes_relayed"""


def _flush_batch(batch):
    if not batch:
        return
    conn = _get_conn()
    if conn is None:
        return
    try:
        with conn.cursor() as cur:
            rows = [_build_request_row(m) for m in batch]
            execute_values(cur, _INSERT_SQL, rows, page_size=100)
        conn.commit()
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        now = time.time()
        global _last_health_check
        if now - _last_health_check > 60:
            print(f"[MS-DB] flush failed ({len(batch)} rows dropped): {e}", flush=True)
            _last_health_check = now


def enqueue_metrics(metrics):
    if not DB_ENABLED or not _HAS_PSYCOPG:
        return
    try:
        _queue.put_nowait(dict(metrics))
    except queue.Full:
        pass


def start_worker():
    global _worker_thread
    if not DB_ENABLED or not _HAS_PSYCOPG:
        return
    if _worker_thread is not None and _worker_thread.is_alive():
        return
    _worker_stop.clear()
    _worker_thread = threading.Thread(target=_worker_loop, name="ms-db-writer", daemon=True)
    _worker_thread.start()


def stop_worker():
    global _worker_thread
    _worker_stop.set()
    try:
        batch = []
        while len(batch) < FLUSH_BATCH:
            try:
                batch.append(_queue.get_nowait())
            except queue.Empty:
                break
        if batch:
            _flush_batch(batch)
    except Exception:
        pass


start_worker()

import atexit
atexit.register(stop_worker)
