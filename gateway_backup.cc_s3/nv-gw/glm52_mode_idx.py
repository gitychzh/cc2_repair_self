#!/usr/bin/env python3
"""R839: persistent current_mode_idx state machine for glm5_2_nv per-key-mode dynamic chain.

"当前生效 mode" 是一个跨请求持久化的动态指针 (NOT per-key 静态绑定):
  - 当前 key 用当前 mode 发请求;
  - 故障 → 换下一个 key + mode 递进到下一档 (mode_idx += 1, capped at len-1);
  - 稳住 → 保持当前 mode (mode_idx 不变), 下一个 key 继续用这个 mode;
  - mode 只往前递进不回退 (避免反复撞已知不稳的 mode).

state persists to NV_GLM52_MODE_IDX_FILE (LOG_DIR/glm52_mode_idx.json) so the
"收敛到的最稳档" survives restarts. 后端整体恢复后由定时测速脚本重排
NV_GLM52_MODE_CHAIN 顺序实现软重置 (不需要手动清 idx 文件).

Public API (re-exported by config.py):
  glm52_current_mode_idx() -> int      read persistent current mode idx (0-based)
  glm52_save_mode_idx(idx)             persist idx (called on success AND on full-fail)
  glm52_reset_mode_idx()               reset to 0 (manual rollback / forced re-probe)
"""
import atexit
import json
import os
import signal as _signal
import sys
import threading
import time

from .config import NV_GLM52_MODE_IDX_FILE

_glm52_idx_lock = threading.Lock()
_glm52_idx_cache = {"idx": 0}


def _save_glm52_idx_locked():
    try:
        tmp = "%s.tmp.%d.%d" % (NV_GLM52_MODE_IDX_FILE, os.getpid(), threading.get_ident())
        with open(tmp, "w") as f:
            json.dump(_glm52_idx_cache, f)
        os.replace(tmp, NV_GLM52_MODE_IDX_FILE)
    except Exception as e:
        print(f"[NV-GLM52-IDX] WARN could not save: {e}", file=sys.stderr, flush=True)


def _load_glm52_idx():
    try:
        with open(NV_GLM52_MODE_IDX_FILE, "r") as f:
            raw = f.read().strip()
        if not raw:
            return
        saved = json.loads(raw)
        if isinstance(saved, dict) and isinstance(saved.get("idx"), int) and saved["idx"] >= 0:
            _glm52_idx_cache["idx"] = saved["idx"]
            print(f"[NV-GLM52-IDX] restored from {NV_GLM52_MODE_IDX_FILE}: idx={saved['idx']}", file=sys.stderr, flush=True)
    except FileNotFoundError:
        pass
    except (json.JSONDecodeError, ValueError) as e:
        print(f"[NV-GLM52-IDX] file corrupt ({e}); starting fresh at idx=0", file=sys.stderr, flush=True)
    except Exception as e:
        print(f"[NV-GLM52-IDX] WARN could not load: {e}", file=sys.stderr, flush=True)


_load_glm52_idx()


def glm52_current_mode_idx():
    """Read persistent current_mode_idx (0-based). Initial 0 = mode1 (pexec_direct 当前最优)."""
    with _glm52_idx_lock:
        return _glm52_idx_cache["idx"]


def glm52_save_mode_idx(idx):
    """Persist idx. Called on success (keep mode) AND on full-fail (next req starts at last mode)."""
    with _glm52_idx_lock:
        _glm52_idx_cache["idx"] = int(idx) if int(idx) >= 0 else 0
        _save_glm52_idx_locked()


def glm52_reset_mode_idx():
    """Reset to 0. Manual rollback / forced re-probe of mode1."""
    with _glm52_idx_lock:
        _glm52_idx_cache["idx"] = 0
        _save_glm52_idx_locked()


def _flush_and_exit(signum, _frame):
    _save_glm52_idx_locked()
    raise SystemExit(128 + signum)


atexit.register(_save_glm52_idx_locked)
_signal.signal(_signal.SIGTERM, _flush_and_exit)
_signal.signal(_signal.SIGINT, _flush_and_exit)
