#!/usr/bin/env python3
"""JSON-line logger (stdout). 一行一 JSON, 便于 docker logs 抓取."""
import json
import os
import time
import threading
from datetime import datetime

_LOG_LOCK = threading.Lock()
_LOG_DIR = os.environ.get("LOG_DIR", "/app/logs")


def _ts():
    # 带微秒的本地时间, 与 nv_gw/ms_gw 日志风格一致
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%f")


def _log(tag, msg, **kwargs):
    rec = {"ts": _ts(), "tag": tag, "msg": msg}
    rec.update(kwargs)
    line = json.dumps(rec, ensure_ascii=False)
    with _LOG_LOCK:
        print(line, flush=True)
    # 同步写一份到文件 (便于事后排查, 容器日志轮转后仍可查)
    try:
        os.makedirs(_LOG_DIR, exist_ok=True)
        with open(os.path.join(_LOG_DIR, "adapter.jsonl"), "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass
