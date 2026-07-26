#!/usr/bin/env python3
"""Configuration constants and environment variables for cc4101.

R684/R1648/R1711: CC-dedicated glm5.2 透传层. No v×k cycling, no NV tiers.
R1711: 透传 anthropic body → nv_gw/ms_gw /v1/messages (anthropic 端点). 转换下沉.
R1643: fallback 已加回 (nv 不限额优先, ms 每天限额兜底).
auth token, DB settings.

All configurable parameters are read from env vars with defaults.
"""
import os
import threading

# ─── Network ──────────────────────────────────────────────────────────────
# Listen on all in-container interfaces; the docker-compose `ports:` mapping is
# what controls off-host exposure (published as 127.0.0.1:4101:4101 there so
# only the host loopback can reach it — see compose, R690).
LISTEN_HOST = os.environ.get("LISTEN_HOST", "0.0.0.0")
LISTEN_PORT = int(os.environ.get("LISTEN_PORT", "4101"))
UPSTREAM_TIMEOUT = int(os.environ.get("UPSTREAM_TIMEOUT", "30"))  # R829: connect+header总超时(死连接快速放弃). R830语义澄清: 此值只管connect+getresponse(), body read改用UPSTREAM_IDLE_TIMEOUT.
UPSTREAM_IDLE_TIMEOUT = int(os.environ.get("UPSTREAM_IDLE_TIMEOUT", "150"))  # R830: body read idle超时(两次chunk间隔). 对齐nv_gw [NV-THINKING-TIMEOUT]150s, 容纳thinking静默期. 与UPSTREAM_TIMEOUT分离: 后者管死连接快断, 本值管长思考不误杀.
# R845 B7: stream stall-watcher 双门槛 (总时长+idle). per-read socket timeout(UPSTREAM_IDLE_TIMEOUT=150s)
# 被 keep-alive drip 绕过即失明 (a1db6f13: 上游120.8s断连, 150s没触发, cc4101连检查点都没有).
# 解法: per-read 改用短轮询 CC4101_STREAM_POLL_S, read 每次最多阻塞这么久就抛 socket.timeout,
# 在 except 里不立即break, 而是检查双门槛: 总时长超限 or idle间隙超限. 阈值见下.
CC4101_STREAM_TOTAL_DEADLINE_S = float(os.environ.get("CC4101_STREAM_TOTAL_DEADLINE_S", "360"))  # R846: ttfb后绝对总时长兜底. 旧值180s误杀正常长请求(51493627实测: 模型产出99个content chunk, thinking90s+长文200s正常超180s被硬断→emit"upstream stream interrupted"→CC无谓重试). 提到360s容纳thinking+长文. 真静默仍由IDLE_GAP_S=60s兜底, 本值只兜纯挂死.
CC4101_STREAM_IDLE_GAP_S = float(os.environ.get("CC4101_STREAM_IDLE_GAP_S", "100"))  # R847: 60→100. 真根因: cc4101 stall-watcher IDLE_GAP(60s) 先于 nv_gw TOTAL_DEADLINE(90s) 触发 → cc4101 进 interrupted 路径提前返回 → nv_gw 后发的 content_filter err_chunk 永远迟到被丢 → 报 upstream stream interrupted. 提到 100s(>90s) 让 nv_gw 先兜底先发 content_filter chunk, cc4101 后兜底才能收到并走 zombie→api_error 正确路径. 无真内容场景多等 40s, 不误杀正常长请求(真内容持续刷新不触发).
CC4101_STREAM_POLL_S = float(os.environ.get("CC4101_STREAM_POLL_S", "30"))  # per-read socket timeout(短轮询获取检查点). 原UPSTREAM_IDLE_TIMEOUT(150s)退为总预算语义, 不再作per-read.
# R822: header/TTFB timeout — connect + time-to-response-header.
# Body read uses per-read poll timeout (CC4101_STREAM_POLL_S) via _restore_read_timeout.
UPSTREAM_HEADER_TIMEOUT = int(os.environ.get("UPSTREAM_HEADER_TIMEOUT", "12"))
# R854: per-stage header timeout. primary only now (no fallback). empty200 单key降级由
# nv_gw 内部 threshold=3 + key cooldown 处理.
PRIMARY_HEADER_TIMEOUT = int(os.environ.get("PRIMARY_HEADER_TIMEOUT", "25"))  # R828: 45->25. R827后integrate实测3-14s, 25s覆盖p90留余量. (R854: 无fallback, 超时直接返回error让CC重试.)

# R824d/R854: primary circuit breaker. nv_gw degraded (empty200/storm/thinking-silence)
# after N consecutive failures -> OPEN fast-fail (503) so CC retries instead of burning
# ~25s/req on a sick upstream. R851 removed fallback, so OPEN = fast-fail (no ms_gw).
# States: CLOSED (normal) -> OPEN (fast-fail 503) -> HALF_OPEN (one probe) -> CLOSED/OPEN.
# Tunable via env. Disable by setting CC4101_PRIMARY_FAIL_THRESHOLD=0.
CC4101_PRIMARY_FAIL_THRESHOLD = int(os.environ.get("CC4101_PRIMARY_FAIL_THRESHOLD", "5"))
CC4101_PRIMARY_SKIP_S = int(os.environ.get("CC4101_PRIMARY_SKIP_S", "60"))

# ─── Role ─────────────────────────────────────────────────────────────────
PROXY_ROLE = os.environ.get("PROXY_ROLE", "cc4101")
HOST_MACHINE = os.environ.get("CC4101_HOST_MACHINE") or os.environ.get("HOSTNAME") or "unknown"

# ─── Upstream (R1643: nv_gw glm5_2_nv 主, ms_gw glm5_2_ms 末位兜底) ──────
# R854 曾删除 fallback; R1643 按用户需求加回: nv 不限额优先, ms 每天限额仅兜底.
#   触发: (a) primary circuit OPEN(连续≥8次失败) 直走 fallback;
#         (b) CLOSED 时 primary 失败(5xx/conn/timeout) 立即试 fallback 一次.
#   fallback 失败仍返回 error 让 CC 重试. fallback 不计 breaker(只盯 primary).
#   中途流挂(SSE 头已发)不切 fallback, 由 stream.py emit api_error 让 CC 重试.
# FALLBACK_UPSTREAM_URL="" 或 "none" 可禁用 fallback(回 R854 行为).
PRIMARY_UPSTREAM_URL = os.environ.get("PRIMARY_UPSTREAM_URL", "http://nv_gw:40006/v1/messages")
PRIMARY_UPSTREAM_MODEL = os.environ.get("PRIMARY_UPSTREAM_MODEL", "glm5_2_nv")
PRIMARY_UPSTREAM_TOKEN = os.environ.get("PRIMARY_UPSTREAM_TOKEN", "nv-gw-token")
_fb_url = os.environ.get("FALLBACK_UPSTREAM_URL", "http://ms_gw:40007/v1/messages")
FALLBACK_UPSTREAM_URL = None if (not _fb_url or _fb_url.lower() == "none") else _fb_url
FALLBACK_UPSTREAM_MODEL = os.environ.get("FALLBACK_UPSTREAM_MODEL", "glm5_2_ms")
FALLBACK_UPSTREAM_TOKEN = os.environ.get("FALLBACK_UPSTREAM_TOKEN", "ms-gw-token")

# R1712-force-fb (2026-07-18): 强制走 ms_gw 的客户端 model 名. 收到此名 -> 跳过 primary(nv_gw)
# 直走 fallback ms_gw, 不经断路器. 用途: loop 自优化子会话(cc-glm5-2-ms)绕开 nv_gw 间歇劣化窗口
# (47-57s api_error / 60-120s 无首字节 / 385s stall), 确保长子会话能稳定产出 round_N.md 报告.
# 注意: 走此路径 = 子会话不再"自我指涉"验证 nv_gw 优化效果, 但优先保 loop 转起来不出空转.
# 置空则禁用(回到所有请求先 primary 的默认行为).
FORCE_FALLBACK_MODEL = os.environ.get("FORCE_FALLBACK_MODEL", "cc-glm5-2-ms")


# ─── Auth (gateway-side, for CC → cc4101) ─────────────────────────────────
CC4101_GATEWAY_API_KEY = os.environ.get("CC4101_GATEWAY_API_KEY", "cc4101-token")
AUTH_ENABLED = os.environ.get("AUTH_ENABLED", "1") == "1"

# ─── Truncation / estimation ──────────────────────────────────────────────
MAX_TOOL_DESC = int(os.environ.get("MAX_TOOL_DESC", "2000"))
MAX_SCHEMA_DESC = int(os.environ.get("MAX_SCHEMA_DESC", "600"))
CHARS_PER_TOKEN_ESTIMATE = float(os.environ.get("CHARS_PER_TOKEN_ESTIMATE", "3.0"))

# ─── Thinking signature (Anthropic thinking block requires a signature) ───
THINKING_SIGNATURE_DEFAULT = os.environ.get(
    "THINKING_SIGNATURE",
    "ErUB3WY0k2GCM2h+4O0S3Y3W3Y3f3Y3f3Y3f3Y3f3Y3f3Y3f3Y3f3Y3f3Y3f3Y3f3Y3f",
)

# ─── Frontend model (what /v1/models advertises to CC) ────────────────────
# CC sends "claude-opus-4-8" or any name; we map everything to the primary
# upstream model. /v1/models lists one canonical name.
CC_FRONTEND_MODEL = os.environ.get("CC_FRONTEND_MODEL", "cc-glm5-2")
MODEL_INPUT_TOKEN_SAFETY = int(os.environ.get("MODEL_INPUT_TOKEN_SAFETY", "170000"))

# ─── Logging ──────────────────────────────────────────────────────────────
LOG_DIR = os.environ.get("LOG_DIR", "/app/logs")
LOG_RETENTION_DAYS = int(os.environ.get("LOG_RETENTION_DAYS", "14"))


# ─── Model name mapping ──────────────────────��────────────────────────────
# cc4101 only serves glm5.2. Any model name CC sends maps to PRIMARY_UPSTREAM_MODEL.
# We keep a MODEL_MAP for explicit names but everything routes to the same backend.
MODEL_MAP = {
    CC_FRONTEND_MODEL: PRIMARY_UPSTREAM_MODEL,
    "glm5.2": PRIMARY_UPSTREAM_MODEL,
    "glm-5.2": PRIMARY_UPSTREAM_MODEL,
    "zhipuai/glm-5.2": PRIMARY_UPSTREAM_MODEL,
    # Claude Code names → glm5.2
    "claude-opus-4-8": PRIMARY_UPSTREAM_MODEL,
    "claude-opus-4-7": PRIMARY_UPSTREAM_MODEL,
    "claude-opus-4": PRIMARY_UPSTREAM_MODEL,
    "claude-sonnet-4-6": PRIMARY_UPSTREAM_MODEL,
    "claude-sonnet-4": PRIMARY_UPSTREAM_MODEL,
    "claude-haiku-4-5": PRIMARY_UPSTREAM_MODEL,
    "claude-sonnet-4-20250514": PRIMARY_UPSTREAM_MODEL,
    "claude-opus-4-20250514": PRIMARY_UPSTREAM_MODEL,
    "claude-opus-4-8-20250514": PRIMARY_UPSTREAM_MODEL,
    "claude-haiku-4-5-20251001": PRIMARY_UPSTREAM_MODEL,
    "claude-3-5-sonnet-20241022": PRIMARY_UPSTREAM_MODEL,
    "claude-3-5-haiku-20241022": PRIMARY_UPSTREAM_MODEL,
    "claude-3-opus-20240229": PRIMARY_UPSTREAM_MODEL,
}


def map_model(requested_model):
    """Map any client-supplied model name to the upstream model id.

    Returns the upstream model id (str). Unknown names → primary upstream model
    (cc4101 is glm5.2-only; we never reject a model name, we just route to glm5.2).
    """
    if not requested_model:
        return PRIMARY_UPSTREAM_MODEL
    return MODEL_MAP.get(requested_model, PRIMARY_UPSTREAM_MODEL)


# ─── Thread locks for logging ─────────────────────────────────────────────
_log_lock = threading.Lock()
_metrics_lock = threading.Lock()
_error_detail_lock = threading.Lock()
