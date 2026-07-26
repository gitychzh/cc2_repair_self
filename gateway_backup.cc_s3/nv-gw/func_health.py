"""Function health tracker for dynamic NVCF surge fallback (R551 / R_multi).

NVCF function 可用性动态轮换 (见 memory: nvcf-dynamic-surge-r550):
某个 function 在某时段 surge (empty_200/timeout), 另一时段恢复.
静态路由 (单 function_id) 下, 首选 function surge → 全挂.
本模块提供 per-function 滑动窗口成功率, 让 execute_request 据此动态选健康候选.

R_multi (2026-07-02): per-model → per-function 健康度.
  - 每个模型有多个候选 function (config.NVCF_PEXEC_MODELS[model]["function_ids"]).
  - 健康度按 function_id 分桶记录 (不是按 model).
  - select_healthy_function(model, candidates) 返回首个健康候选, surge 的自动跳过.

线程安全: nv_gw 多线程 handler 共享, 用 threading.Lock 保护.
不持久化: 进程重启清零 (冷启动期全部 function 视为健康=100%, 避免误判).
"""

import os
import threading
import time
from collections import deque

from .logger import _log

# 滑动窗口大小 (每 function 保留最近 N 次请求结果)
WINDOW_SIZE = 20
# 健康度阈值: 成功率 >= 此值才允许作为首选 function
HEALTH_THRESHOLD = float(os.environ.get("NVU_FALLBACK_HEALTH_THRESHOLD", "0.10"))
# 冷启动保护: 样本数 < 此值时视作健康 (避免新 function 因样本不足被排除)
MIN_SAMPLES = 5


class _FunctionHealth:
    """Per-function 滑动窗口健康度. key=function_id (UUID), 1=成功, 0=失败."""

    def __init__(self):
        self._lock = threading.Lock()
        self._windows = {}  # function_id -> deque([0/1, ...])

    def _win(self, func_id):
        with self._lock:
            if func_id not in self._windows:
                self._windows[func_id] = deque(maxlen=WINDOW_SIZE)
            return self._windows[func_id]

    def record(self, func_id, success):
        """Record a request result for a function_id. success=True if 200 and not empty_200."""
        w = self._win(func_id)
        with self._lock:
            w.append(1 if success else 0)

    def health(self, func_id):
        """Return success ratio [0,1]. Cold (few samples) → 1.0 (treat as healthy)."""
        with self._lock:
            w = self._windows.get(func_id)
            if not w or len(w) < MIN_SAMPLES:
                return 1.0
            return sum(w) / len(w)

    def is_healthy(self, func_id):
        return self.health(func_id) >= HEALTH_THRESHOLD

    def select_healthy(self, candidates):
        """Return the first healthy function_id from candidates (ordered list).

        遍历候选列表, 返回首个健康度达标的 function_id. 全部不健康时回退到 candidates[0]
        (首选), 让调用方仍能尝试 (避免无 function 可用); 调用方失败后会 record, 下次自动跳过.
        冷启动 (样本不足) 视为健康 → 返回 candidates[0].
        """
        if not candidates:
            return None
        for fid in candidates:
            if self.is_healthy(fid):
                return fid
        # 全部不健康 → 仍返回首选, 让调用方尝试 (失败后 record 进一步降低健康度)
        return candidates[0]

    def snapshot(self):
        """Return dict of all function health for logging/debug."""
        with self._lock:
            return {fid: round(sum(w) / len(w), 3) for fid, w in self._windows.items() if w}


# 进程级单例
_tracker = _FunctionHealth()


def record_result(func_id, success):
    """Record a request result. func_id=function_id used for this attempt."""
    _tracker.record(func_id, success)


def get_health(func_id):
    return _tracker.health(func_id)


def is_healthy(func_id):
    return _tracker.is_healthy(func_id)


def select_healthy_function(model, candidates):
    """Select first healthy function_id from candidates for a model.

    Args:
        model: internal model key (dsv4p_nv) — only for logging.
        candidates: ordered list of function_id strings.
    Returns: chosen function_id, or candidates[0] if all unhealthy.
    """
    chosen = _tracker.select_healthy(candidates)
    if chosen != (candidates[0] if candidates else None):
        _log("NV-FUNC-HEALTH", f"model={model} primary={candidates[0][:12]}... "
              f"unhealthy → switched to {chosen[:12] if chosen else 'NONE'}...")
    return chosen


def snapshot():
    return _tracker.snapshot()
