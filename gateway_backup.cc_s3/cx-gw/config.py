#!/usr/bin/env python3
"""cx4102 配置. 全部 env-overridable, 无 key (cx4102 不持 key)."""
import os

# ─── Network ──────────────────────────────────────────────────────────────
LISTEN_HOST = os.environ.get("LISTEN_HOST", "0.0.0.0")
LISTEN_PORT = int(os.environ.get("LISTEN_PORT", "4102"))
PROXY_TIMEOUT = int(os.environ.get("PROXY_TIMEOUT", "300"))  # 整体请求超时 (用户暂定 300s)

# ─── 后端路由 (cx4102 自己不做 key 轮转, 转发到 nv_gw/ms_gw) ───────────────
PRIMARY_URL = os.environ.get("PRIMARY_URL", "http://nv_gw:40006/v1")
FALLBACK_URL = os.environ.get("FALLBACK_URL", "http://ms_gw:40007/v1")
PRIMARY_MODEL = os.environ.get("PRIMARY_MODEL", "glm5_2_nv")
FALLBACK_MODEL = os.environ.get("FALLBACK_MODEL", "glm5_2_ms")

# ─── fallback 触发条件 ─────────────────────────────────────────────────────
# primary 5xx / all_tiers_exhausted / 超时 → fallback
FALLBACK_TIMEOUT_S = float(os.environ.get("FALLBACK_TIMEOUT_S", "300"))  # 整体 socket 超时 上限
# primary 流式首响应超时 (响应头/首字节). 到点没拿到就切 fallback, 不等 FALLBACK_TIMEOUT_S
PRIMARY_STREAM_TIMEOUT_S = float(os.environ.get("PRIMARY_STREAM_TIMEOUT_S", "60"))
# 连续 N 次 fallback 触发 → 直接走 fallback 一段时间 (避免打爆 primary)
CIRCUIT_FAILURE_THRESHOLD = int(os.environ.get("CIRCUIT_FAILURE_THRESHOLD", "3"))
CIRCUIT_OPEN_S = int(os.environ.get("CIRCUIT_OPEN_S", "60"))  # circuit 打开 60s
# fallback 后多久回 primary 试探 (秒)
FALLBACK_RECOVER_S = int(os.environ.get("FALLBACK_RECOVER_S", "30"))

# ─── 鉴权 (cx4102 自己也加个 token, 与 nv_gw/ms_gw 的 token 解耦) ──────────
CX_GATEWAY_API_KEY = os.environ.get("CX_GATEWAY_API_KEY", "cx-gw-token")
AUTH_ENABLED = os.environ.get("AUTH_ENABLED", "1") == "1"

# ─── 上游 key (cx4102 用 nv-gw-token / ms-gw-token 访问后端) ───────────────
NV_GW_API_KEY = os.environ.get("NV_GW_API_KEY", "nv-gw-token")
MS_GW_API_KEY = os.environ.get("MS_GW_API_KEY", "ms-gw-token")

# ─── 日志 ──────────────────────────────────────────────────────────────────
LOG_DIR = os.environ.get("LOG_DIR", "/app/logs")

# ─── 提醒文案 (fallback 时插入 response, 不中断 agent 任务) ────────────────
FALLBACK_NOTICE = (
    "⚠️ [cx4102] nv_gw 全部 5 key 故障/超时, 已 fallback 到 ms_gw (glm5_2_ms). "
    "本轮继续, 下一轮将自动回 nv_gw. (cx4102 fallback)"
)
