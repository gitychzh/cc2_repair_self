#!/usr/bin/env python3
"""PostgreSQL persistence for cc4101 metrics — R684.

Mirrors nv_gw/gateway/db.py and ms_gw/gateway/db.py design (async queue +
daemon thread + batch INSERT). Best-effort: DB down → queue fills → entries
dropped. JSONL (logger.py) remains ground truth.

Schema: cc_requests table. Created by postgres/cc4101-schema.sql (idempotent).
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

# ─── Configuration (env-driven) ───────────────────────────────────────────
DB_ENABLED = os.environ.get("CC4101_DB_ENABLED", "0") == "1"
DB_HOST = os.environ.get("CC4101_DB_HOST", "logs_db")
DB_PORT = int(os.environ.get("CC4101_DB_PORT", "5432"))
DB_USER = os.environ.get("CC4101_DB_USER", "litellm")
DB_PASSWORD = os.environ.get("CC4101_DB_PASSWORD", "")
DB_NAME = os.environ.get("CC4101_DB_NAME", "hermes_logs")

FLUSH_INTERVAL_S = float(os.environ.get("CC4101_DB_FLUSH_INTERVAL_S", "2"))
FLUSH_BATCH = int(os.environ.get("CC4101_DB_FLUSH_BATCH", "50"))
QUEUE_MAX = int(os.environ.get("CC4101_DB_QUEUE_MAX", "2000"))

HOST_MACHINE = os.environ.get("CC4101_HOST_MACHINE") or os.environ.get("HOSTNAME") or "unknown"

# ─── Queue + worker ───────────────────────────────────────────────────────
_queue = queue.Queue(maxsize=QUEUE_MAX)
_worker_thread = None
_worker_stop = threading.Event()
_conn = None
_conn_lock = threading.Lock()
_last_health_check = 0.0
_dropped_count = 0            # R690: count metrics dropped on queue full
_dropped_lock = threading.Lock()


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
                print(f"[CC4101-DB] connect failed: {e}", flush=True)
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


def _build_request_row(m):
    ts = m.get("timestamp")
    ts_dt = None
    if ts:
        try:
            ts_dt = datetime.datetime.fromisoformat(ts)
        except Exception:
            ts_dt = None
    return (
        m.get("request_id"),
        ts_dt,
        HOST_MACHINE,
        m.get("request_model"),
        m.get("mapped_model"),
        m.get("upstream_used"),
        m.get("fallback_triggered", False),
        m.get("is_stream"),
        m.get("total_input_chars", 0),
        m.get("num_messages"),
        m.get("num_tools"),
        m.get("ttfb_ms"),
        m.get("duration_ms", 0),
        m.get("status", 0),
        m.get("finish_reason"),
        m.get("input_tokens", 0),
        m.get("output_tokens", 0),
        m.get("error_type"),
        m.get("error_message"),
        m.get("primary_error_type"),
        m.get("primary_elapsed_ms"),
    )


_INSERT_SQL = """INSERT INTO cc_requests
    (request_id, ts, host_machine, request_model, mapped_model, upstream_used,
     fallback_triggered, is_stream, total_input_chars, num_messages, num_tools,
     ttfb_ms, duration_ms, status, finish_reason, input_tokens, output_tokens,
     error_type, error_message, primary_error_type, primary_elapsed_ms)
    VALUES %s
    ON CONFLICT (request_id) DO UPDATE SET
      status=EXCLUDED.status,
      duration_ms=EXCLUDED.duration_ms,
      mapped_model=EXCLUDED.mapped_model,
      upstream_used=EXCLUDED.upstream_used,
      fallback_triggered=EXCLUDED.fallback_triggered,
      ttfb_ms=EXCLUDED.ttfb_ms,
      finish_reason=EXCLUDED.finish_reason,
      input_tokens=EXCLUDED.input_tokens,
      output_tokens=EXCLUDED.output_tokens,
      error_type=EXCLUDED.error_type,
      error_message=EXCLUDED.error_message,
      primary_error_type=EXCLUDED.primary_error_type,
      primary_elapsed_ms=EXCLUDED.primary_elapsed_ms"""


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
            print(f"[CC4101-DB] flush failed ({len(batch)} rows dropped): {e}", flush=True)
            _last_health_check = now


def enqueue_metrics(metrics):
    if not DB_ENABLED or not _HAS_PSYCOPG:
        return
    try:
        _queue.put_nowait(dict(metrics))
    except queue.Full:
        # R690 cc2 red-team: was silently `pass` — a full queue hid data loss.
        # Still best-effort (don't block the request path), but count drops so
        # the operator can see DB backpressure in the log.
        global _dropped_count
        with _dropped_lock:
            _dropped_count += 1
            if _dropped_count % 50 == 1:
                print(f"[CC4101-DB] metrics queue full — dropped {_dropped_count} entries total", flush=True)


def dropped_count():
    """Return number of metrics entries dropped due to queue full (for /health)."""
    with _dropped_lock:
        return _dropped_count


def start_worker():
    global _worker_thread
    if not DB_ENABLED or not _HAS_PSYCOPG:
        return
    if _worker_thread is not None and _worker_thread.is_alive():
        return
    _worker_stop.clear()
    _worker_thread = threading.Thread(target=_worker_loop, name="cc4101-db-writer", daemon=True)
    _worker_thread.start()


def stop_worker():
    global _worker_thread
    _worker_stop.set()
    # R690 cc2 red-team: atexit fires during interpreter shutdown. The worker
    # may be mid-flush; we drain the queue ourselves, flush, then join the
    # worker so it can't write to a half-torn-down psycopg2 connection.
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
    t = _worker_thread
    if t is not None and t.is_alive() and t is not threading.current_thread():
        try:
            t.join(timeout=5)
        except Exception:
            pass


start_worker()

import atexit
atexit.register(stop_worker)
