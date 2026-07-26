#!/usr/bin/env python3
"""Configuration for ms_gw — MS (ModelScope) unified proxy.

Env-driven. All tunables here. No NVCF, no DB, no Anthropic conversion.
"""
import os
import sys
import threading
import json

# ─── Listen ──────────────────────────────────────────────────────────────
LISTEN_HOST = os.environ.get("LISTEN_HOST", "0.0.0.0")
LISTEN_PORT = int(os.environ.get("LISTEN_PORT", "40007"))
PROXY_ROLE = os.environ.get("PROXY_ROLE", "ms_uni")

# ─── Upstream (ModelScope) ───────────────────────────────────────────────
MS_BASEURL = os.environ.get("MS_BASEURL", "https://api-inference.modelscope.cn/v1")
# Strip trailing slash for clean URL join
if MS_BASEURL.endswith("/"):
    MS_BASEURL = MS_BASEURL[:-1]

UPSTREAM_TIMEOUT = float(os.environ.get("UPSTREAM_TIMEOUT", "300"))
PROXY_TIMEOUT = float(os.environ.get("PROXY_TIMEOUT", "600"))
# R844 F10: connect 阶段独立短超时, 避免 ModelScope connect hang 卡满 UPSTREAM_TIMEOUT(300)
MS_CONNECT_TIMEOUT = float(os.environ.get("MS_CONNECT_TIMEOUT", "10"))

# ─── MS keys (7) ─────────────────────────────────────────────────────────
# Read MS_KEY1..7 from env. Compose references the same ${MS_KEYx} as ms_uni41001
# (shared keys, decoupled containers — no key duplication).
MS_KEYS = []
for i in range(1, 16):  # scan up to 15, stop at first missing
    k = os.environ.get(f"MS_KEY{i}")
    if not k:
        break
    MS_KEYS.append(k)
NUM_KEYS = len(MS_KEYS)
if NUM_KEYS == 0:
    print("[MS-PROXY] FATAL: no MS_KEY1..N configured", file=sys.stderr, flush=True)
    # Don't crash — let health endpoint report it. But warn loudly.

# ─── Variants (10, IMMUTABLE) — 10 ModelScope model_id typos for ZHIPUAI/GLM-5.2 ───
# These are the 10 ModelScope model_id typos for ZHIPUAI/GLM-5.2.
# NEVER remove — each carries independent 200/id/day quota.
GLM5_2_VARIANT_IDS = [
    "ZHIPUAI/GLM-5.2",     # v1
    "ZHIPUAI/GLm-5.2",     # v2
    "ZHIPUAI/GlM-5.2",     # v3
    "ZHIPUAI/Glm-5.2",     # v4
    "ZHIPUAI/gLM-5.2",     # v5
    "ZHIPUAI/gLm-5.2",     # v6
    "ZHIPUAI/glM-5.2",     # v7
    "ZHIPUAI/glm-5.2",     # v8
    "ZHIPUAi/GLM-5.2",     # v9
    "ZHIPUAi/GLm-5.2",     # v10
]
NUM_VARIANTS = int(os.environ.get("NUM_VARIANTS", str(len(GLM5_2_VARIANT_IDS))))
# Truncate/extend to NUM_VARIANTS (env override for testing)
GLM5_2_VARIANT_IDS = GLM5_2_VARIANT_IDS[:NUM_VARIANTS]

# ─── dsv4p variants (10, R703) ───────────────────────────────────────────
# ModelScope 标准 model_id 是 "deepseek-ai/DeepSeek-V4-Pro". 实测 (R703, HM2)
# ModelScope 对 model_id 大小写不敏感路由 —— 任意大小写 typo 都返回 200,
# 且与 GLM-5.2 同样具备"每个 typo 变体独立 200/id/day 配额"的行为.
# 10 个变体 = 10×7key = 70 槽位, 与 glm5_2_ms 对称.
DSV4P_VARIANT_IDS = [
    "deepseek-ai/DeepSeek-V4-Pro",  # v1 (canonical)
    "deepseek-ai/Deepseek-V4-Pro",  # v2
    "deepseek-ai/deepseek-v4-pro",  # v3
    "deepseek-ai/DeepSeek-v4-pro",  # v4
    "deepseek-ai/DEEPSEEK-V4-PRO",  # v5
    "deepseek-ai/Deepseek-v4-Pro",  # v6
    "deepseek-ai/deepseek-V4-Pro",  # v7
    "deepseek-ai/DeepSeek-V4-pro",  # v8
    "deepseek-ai/deepseek-v4-Pro",  # v9
    "deepseek-ai/DEEPSEEK-v4-pro",  # v10
]
# Per-model variant count (dsv4p_ms 用同样 10 个; env 可覆盖测试)
DSV4P_NUM_VARIANTS = int(os.environ.get("DSV4P_NUM_VARIANTS", str(len(DSV4P_VARIANT_IDS))))
DSV4P_VARIANT_IDS = DSV4P_VARIANT_IDS[:DSV4P_NUM_VARIANTS]

# ─── Model registry (agent-facing model_id → backend spec) ───────────────
# Each agent-facing model maps to: (backend_variant_ids, default_params)
# glm5_2_ms + dsv4p_ms implemented (R703).
MODEL_REGISTRY = {
    "glm5_2_ms": {
        "backend": "ms_glm5_2",
        "name": "GLM-5.2 (ModelScope via ms_gw, 7key×10variant)",
        "variants": GLM5_2_VARIANT_IDS,
        "context_window": 1048576,  # R2188: glm5.2 z.ai 已开放 1M, 同步 nv_gw
        "max_tokens": 32768,
        "supports_thinking": True,
    },
    # ── R703: dsv4p_ms 现已实现 (hermes dsv4p_nv 5key全挂时的 fallback) ──
    "dsv4p_ms": {
        "backend": "ms_dsv4p",
        "name": "DeepSeek V4 Pro (ModelScope via ms_gw, 7key×10variant)",
        "variants": DSV4P_VARIANT_IDS,
        "context_window": 131072,
        "max_tokens": 32768,
        "supports_thinking": True,
    },
}
DEFAULT_MODEL = os.environ.get("DEFAULT_MODEL", "glm5_2_ms")

# ─── Cooldown ────────────────────────────────────────────────────────────
KEY_COOLDOWN_S = float(os.environ.get("KEY_COOLDOWN_S", "60"))
# When all 7 keys of a variant fail, mark variant cooling
VARIANT_COOLDOWN_S = float(os.environ.get("VARIANT_COOLDOWN_S", "30"))
# When all 10 variants × 7 keys exhausted, how long to refuse (all_keys_exhausted)
ALL_EXHAUSTED_COOLDOWN_S = float(os.environ.get("ALL_EXHAUSTED_COOLDOWN_S", "30"))

# ─── Burst throttle (between outbound requests, protects rpm=1) ──────────
MIN_OUTBOUND_INTERVAL_S = float(os.environ.get("MIN_OUTBOUND_INTERVAL_S", "1.0"))

# ─── empty_200 FASTBREAK (surge期 MS 返回 choices:null 畸形空壳) ─────────
# Surge 期连续多个 key 返回畸形空壳时, 不要把所有 70 槽都试一遍 (会卡 143s).
# 连续 N 次 empty_200/choices:null → fastbreak, 返回 all_keys_exhausted.
EMPTY_200_FASTBREAK_THRESHOLD = int(os.environ.get("EMPTY_200_FASTBREAK_THRESHOLD", "5"))
# R822: cross-variant total empty limit. Without this, a storming model (glm5_2_ms
# choices_null across all variants) cycles up to NUM_VARIANTS * FASTBREAK = 50 attempts
# (50-100s) per request, stalling cc4101. This cap aborts the whole request after N
# total empties across all variants -> mark all_exhausted, return fast. Default 12
# (~2 variants worth). Set 0 to disable (legacy 50-attempt behavior).
EMPTY_200_TOTAL_LIMIT = int(os.environ.get("EMPTY_200_TOTAL_LIMIT", "12"))

# ─── Auth ────────────────────────────────────────────────────────────────
MSU_GATEWAY_API_KEY = os.environ.get("MSU_GATEWAY_API_KEY", "ms-local")
AUTH_ENABLED = bool(os.environ.get("AUTH_ENABLED", "1"))

# ─── Logging ─────────────────────────────────────────────────────────────
LOG_DIR = os.environ.get("LOG_DIR", "/app/logs")
LOG_RETENTION_DAYS = int(os.environ.get("LOG_RETENTION_DAYS", "7"))

_log_lock = threading.Lock()
_metrics_lock = threading.Lock()
_error_detail_lock = threading.Lock()

# ─── RR counter key per agent-facing model ───────────────────────────────
# Each model gets its own counter slot in rr_counter.json
_MODEL_RR_KEYS = {
    "glm5_2_ms": "ms_glm5_2",
    "dsv4p_ms": "ms_dsv4p",
}


def _detect_caller(user_agent: str, x_caller: str = "") -> str:
    """Best-effort caller identification for logging."""
    ua = (user_agent or "").lower()
    xc = (x_caller or "").lower()
    # R1700: cc4101 注入的 X-Caller (cc4101-primary / cc4101-fallback) 原样保留,
    # 这样 metrics.caller 能区分 fallback 流量(回答"ms fallback 次数"). 放最前,
    # 精确标签优先于 hermes/openclaw 等子串模糊匹配.
    if xc.startswith("cc4101"):
        return xc
    if "hermes" in ua or "hermes" in xc:
        return "hermes"
    if "openclaw" in ua or "openclaw" in xc:
        return "openclaw"
    if "opencode" in ua or "opencode" in xc:
        return "opencode"
    if "curl" in ua:
        return "curl"
    return "unknown"


def _startup_check():
    """Validate bind-mount: gateway dir must exist and be non-empty."""
    try:
        import os as _os
        gd = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)))
        # /app/gateway — check the bind-mounted target
        app_gw = "/app/gateway"
        if _os.path.isdir(app_gw):
            files = _os.listdir(app_gw)
            if not files:
                print(f"[MS-PROXY] WARN: /app/gateway is EMPTY — bind-mount may have "
                      f"overridden COPY with empty dir. Container may crash on import.",
                      file=sys.stderr, flush=True)
    except Exception as e:
        print(f"[MS-PROXY] startup check error: {e}", file=sys.stderr, flush=True)


_startup_check()

# Print config summary
print(f"[MS-PROXY] config: LISTEN={LISTEN_HOST}:{LISTEN_PORT} role={PROXY_ROLE} "
      f"keys={NUM_KEYS} variants={NUM_VARIANTS} models={list(MODEL_REGISTRY.keys())} "
      f"default={DEFAULT_MODEL} baseurl={MS_BASEURL}", file=sys.stderr, flush=True)
if NUM_KEYS == 0:
    print("[MS-PROXY] FATAL: NUM_KEYS=0 — no MS_KEY1..N in env", file=sys.stderr, flush=True)
