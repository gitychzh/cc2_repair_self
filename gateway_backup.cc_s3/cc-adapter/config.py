#!/usr/bin/env python3
"""cc-adapter 配置. 全部 env-overridable. 不持 key (转发到 nv_gw/ms_gw).

一个镜像服务 3 个容器 (opclaw4103/hm4104/oc4105), 区别仅在 env:
  ADAPTER_NAME: 容器名 (日志/health 标识)
  PRIMARY_URL/PRIMARY_MODEL: 主后端 (nv_gw:40006)
  FALLBACK_URL/FALLBACK_MODEL: 备后端 (ms_gw:40007), oc4105 设 FALLBACK_ENABLED=0 禁用

R844: 超时分层对齐 cc4101. 三层超时:
  - connect (CC_CONNECT_TIMEOUT_S=10s): TCP 建连, 短, 抖动快断
  - header/TTFB (PRIMARY_HEADER_TIMEOUT=25s / FALLBACK_HEADER_TIMEOUT=30s): connect+getresponse, 短
  - body idle (UPSTREAM_IDLE_TIMEOUT=150s): 响应头后 chunk 间隔, 长, 容纳 thinking 静默期
  修复前 PRIMARY_STREAM_TIMEOUT_S=90s 同时管 TTFB+body idle, 致 connect 抖动卡 90s + thinking 静默>90s 误判.
"""
import os

# ─── Network ──────────────────────────────────────────────────────────────
LISTEN_HOST = os.environ.get("LISTEN_HOST", "0.0.0.0")
LISTEN_PORT = int(os.environ.get("LISTEN_PORT", "4103"))
PROXY_TIMEOUT = int(os.environ.get("PROXY_TIMEOUT", "300"))

# ─── 身份 ─────────────────────────────────────────────────────────────────
ADAPTER_NAME = os.environ.get("ADAPTER_NAME", "opclaw4103")
ADAPTER_ROLE = os.environ.get("ADAPTER_ROLE", "cc-adapter")  # chat-completions 透传 + fallback

# ─── 后端路由 (adapter 不做 key 轮转, 转发到 nv_gw/ms_gw) ───────────────
PRIMARY_URL = os.environ.get("PRIMARY_URL", "http://nv_gw:40006/v1")
FALLBACK_URL = os.environ.get("FALLBACK_URL", "http://ms_gw:40007/v1")
PRIMARY_MODEL = os.environ.get("PRIMARY_MODEL", "glm5_2_nv")
FALLBACK_MODEL = os.environ.get("FALLBACK_MODEL", "glm5_2_ms")

# ─── fallback 开关 (oc4105 设 0, 无 fallback) ────────────────────────────
FALLBACK_ENABLED = os.environ.get("FALLBACK_ENABLED", "1") == "1"

# ─── 超时分层 (R844: 对齐 cc4101, 修 connect 卡 90s + TTFB/idle 混用) ──────
# connect 阶段 (TCP 建连): 短, 抖动快断. forwarder.py 内 os.environ.get 读取 (与 R763 一致).
# header/TTFB 阶段 (connect 完成后到 getresponse 返回响应头):
#   primary 25s 覆盖 p90 TTFB (实测 3-14s, thinking 最慢 71s 由 idle 兜底而非 header);
#   fallback 30s 容纳 ms_gw 7-key RR 429 退避 (~18s 找 warm key).
# 到点没拿到响应头就切 fallback, 不白等.
PRIMARY_HEADER_TIMEOUT = float(os.environ.get("PRIMARY_HEADER_TIMEOUT", "25"))
FALLBACK_HEADER_TIMEOUT = float(os.environ.get("FALLBACK_HEADER_TIMEOUT", "30"))
# body idle 阶段 (响应头到达后, 两次 chunk 间隔): 长 150s, 容纳 glm5.2 thinking 静默期,
# 对齐 nv_gw [NV-THINKING-TIMEOUT]150s. 修复前用 PRIMARY_STREAM_TIMEOUT_S=90s, thinking 静默>90s 被误判卡死.
UPSTREAM_IDLE_TIMEOUT = float(os.environ.get("UPSTREAM_IDLE_TIMEOUT", "150"))
# 跨 stage 总预算 (primary + fallback + primary_retry). 预算不足时跳过 retry 快速失败, 避免三段超时叠加.
CC4101_TOTAL_BUDGET_S = float(os.environ.get("CC4101_TOTAL_BUDGET_S", "80"))
# fallback 失败后是否 retry primary 一次 (primary 常比 storming fallback 恢复快). 0=禁用.
RETRY_PRIMARY_AFTER_FALLBACK = os.environ.get("RETRY_PRIMARY_AFTER_FALLBACK", "1") == "1"

# ─── 兼容旧 env (不删, 作 fallback 默认) ─────────────────────────────────
# 旧的单值超时, 现仅用于非流 embeddings 透传 / fallback 阶段兜底默认.
FALLBACK_TIMEOUT_S = float(os.environ.get("FALLBACK_TIMEOUT_S", "300"))  # 旧: 整体 socket 超时上限
PRIMARY_STREAM_TIMEOUT_S = float(os.environ.get("PRIMARY_STREAM_TIMEOUT_S", "60"))  # 旧: 兼容, 新代码不直接用

# ─── circuit 熔断 (对齐 cc4101 三态 CLOSED/OPEN/HALF_OPEN) ─────────────────
CIRCUIT_FAILURE_THRESHOLD = int(os.environ.get("CIRCUIT_FAILURE_THRESHOLD", "5"))  # 连续 retryable 失败 N 次开路
CIRCUIT_OPEN_S = int(os.environ.get("CIRCUIT_OPEN_S", "60"))  # OPEN 持续秒数, 过期进 HALF_OPEN 探活
# 单次 fallback 后短冷却 (opclaw4103 特有, cc4101 没有): 刚 fallback 完别立刻戳 sick primary.
FALLBACK_RECOVER_S = int(os.environ.get("FALLBACK_RECOVER_S", "30"))

# ─── 鉴权 (adapter 自己的 token, 与 nv_gw/ms_gw token 解耦) ──────────────
ADAPTER_API_KEY = os.environ.get("ADAPTER_API_KEY", "cc-adapter-token")
AUTH_ENABLED = os.environ.get("AUTH_ENABLED", "1") == "1"

# ─── 上游 key (adapter 用 nv-gw-token / ms-gw-token 访问后端) ───────────
NV_GW_API_KEY = os.environ.get("NV_GW_API_KEY", "nv-gw-token")
MS_GW_API_KEY = os.environ.get("MS_GW_API_KEY", "ms-gw-token")

# ─── 日志 ──────────────────────────────────────────────────────────────────
LOG_DIR = os.environ.get("LOG_DIR", "/app/logs")

# ─── 提醒文案 (fallback 时插入响应, 不中断 agent 任务) ──────────────────
FALLBACK_NOTICE = os.environ.get(
    "FALLBACK_NOTICE",
    "⚠️ [{name}] primary 故障/超时, 已 fallback 到 {fb_model}. 本轮继续, 下一轮回 primary. ({name} fallback)"
).format(name=ADAPTER_NAME, fb_model=FALLBACK_MODEL)

# ─── R766: openclaw 兜底 (默认禁用, 仅 opclaw4103 启用) ─────────────────
# prompt token 估算超此值直接返回 400 (不转发 NVCF), 避免 openclaw Context overflow 后 retry 累积超时
PROMPT_TOKEN_LIMIT = int(os.environ.get("PROMPT_TOKEN_LIMIT", "0"))  # 0=禁用
# 流式 content=null 但有 reasoning_content 时, 流末补 content=reasoning 全文
SUPPLEMENT_REASONING_AS_CONTENT = os.environ.get("SUPPLEMENT_REASONING_AS_CONTENT", "0") == "1"
