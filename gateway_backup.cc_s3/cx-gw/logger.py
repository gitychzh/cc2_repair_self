#!/usr/bin/env python3
"""简单 logger, 复用 nv_gw 风格 (stdout JSONL) + 错误落盘 (R761).

R761 新增: 错误/告警类 tag 同时写按日分割的 JSONL 文件
  {LOG_DIR}/hm_error_detail.YYYY-MM-DD.jsonl
格式与 nv_gw 的 hm_error_detail 对齐, 便于跨层 jq 分析.
落盘判定: tag 含 ERR / FAIL / CIRCUIT-OPEN / CONVERT (信息类 REQ/START/STOP 不落盘).
所有调用点零改动 — _log 签名不变, 自动分流.
"""
import os
import json
import datetime
import threading

LOG_DIR = os.environ.get("LOG_DIR", "/app/logs")

# 落盘的 tag 关键字 (信息类 REQ/START/STOP/STREAM-FINAL/FALLBACK-STREAM 不落盘)
_PERSIST_TAGS = ("ERR", "FAIL", "CIRCUIT-OPEN", "CONVERT")

# 文件写锁 (跨线程, uvicorn 多线程)
_file_lock = threading.Lock()


def _ts():
    return datetime.datetime.now().isoformat()


def _is_persist(tag):
    """错误/告警类才落盘."""
    if not tag:
        return False
    return any(k in tag for k in _PERSIST_TAGS)


def _date_str():
    return datetime.datetime.now().strftime("%Y-%m-%d")


def _log(tag, msg, **extra):
    """结构化日志: stdout JSONL + (错误类) 落盘 JSONL."""
    rec = {"ts": _ts(), "tag": tag, "msg": msg}
    if extra:
        rec.update(extra)
    line = json.dumps(rec, ensure_ascii=False)
    try:
        print(line, flush=True)
    except Exception:
        print(f'{{"ts":"{_ts()}","tag":"{tag}","msg":"{msg}"}}', flush=True)
    # 错误/告警类 → 同时落盘
    if _is_persist(tag):
        _persist_error_line(line)


def _persist_error_line(line):
    """错误详情写按日分割 JSONL 文件 (仿 nv_gw hm_error_detail.YYYY-MM-DD.jsonl)."""
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        path = os.path.join(LOG_DIR, f"hm_error_detail.{_date_str()}.jsonl")
        with _file_lock:
            with open(path, "a") as f:
                f.write(line + "\n")
    except Exception as e:
        # 落盘失败不能再走 _log (会递归), 直接 stdout
        print(f'{{"ts":"{_ts()}","tag":"LOG-ERR","msg":"failed to persist error: {e}"}}', flush=True)


def _log_error_detail(rec):
    """兼容旧接口: 直接写 JSONL 文件 (R761 前 _log 不落盘时用的专用函数).
    R761 后 _log 已对错误类自动落盘, 新代码用 _log 即可; 此函数保留给老调用点."""
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        path = os.path.join(LOG_DIR, "hm_error_detail.jsonl")
        line = json.dumps(rec, ensure_ascii=False)
        with _file_lock:
            with open(path, "a") as f:
                f.write(line + "\n")
    except Exception as e:
        print(f'{{"ts":"{_ts()}","tag":"LOG-ERR","msg":"failed to write error detail: {e}"}}', flush=True)
