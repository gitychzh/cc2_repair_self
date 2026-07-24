#!/usr/bin/env python3
"""Configuration for NV proxy (nv_gw) — single-model dsv4p_nv, 三 agent 通用.

unify-nv (2026-06-30): 内部 model key 从 deepseek_hm_nv 改为 dsv4p_nv, 反映
      通用语义 (供 hermes/opencode/openclaw 三 agent 共用, 非 Hermes 专属).
      旧名 deepseek_hm_nv 保留为 alias 向后兼容.
R274: Removed kimi dead code. The proxy serves exactly one model —
      dsv4p_nv (deepseek-v4-pro) — via NVCF pexec. No tier fallback.

Chain: agent (hermes/opencode/openclaw) → nv_gw → NVCF pexec
       (orion-deepseek-v4-pro, ACTIVE) → per-key SOCKS5 → mihomo/direct → NV API.

5 keys (k1→k5) round-robin with a persistent RR counter (全局共享, N+1 跨 agent
连续, 重启续接). A request fails only when all 5 keys are exhausted
(429 / empty 200 / timeout) within the tier budget — there is no model fallback.

Reng (HM1 self-change, authorized): modularized for long-term maintainability.
RR counter state machine → gateway/rr_counter.py; 429 cooldown state machine
→ gateway/cooldown.py; NVCF connection layer → gateway/nvcf_conn.py; pexec
request construction/validation → gateway/pexec.py. This file now holds pure
configuration + throttle_outbound only. Logic is byte-for-byte equivalent;
all downstream `from .config import ...` statements keep working via re-export.
"""
import os
import sys
import time
import threading

# ─── Network ──────────────────────────────────────────────────────────────
LISTEN_HOST = "0.0.0.0"
LISTEN_PORT = int(os.environ.get("LISTEN_PORT", "40006"))
PROXY_TIMEOUT = int(os.environ.get("PROXY_TIMEOUT", "300"))
UPSTREAM_TIMEOUT = int(os.environ.get("UPSTREAM_TIMEOUT", "30"))  # CC-2026-07-01: 45->30, NVCF挂死超时更快放弃切key; compose env 同步  # R38.5: 60→45 (NV p95<30s)

# ─── Gateway auth (局域网 agent 共享 key, 2026-06-30) ──────────────────────
# 空 = 不校验(向后兼容); 非空 = /v1/* 须带 Authorization: Bearer <NVU_GATEWAY_API_KEY>
# 或 x-api-key: <NVU_GATEWAY_API_KEY>. /health 与 CORS preflight 免鉴权.
# 默认 nv-local (与 hermes config model.api_key 一致, 局域网 agent 共用).
NVU_GATEWAY_API_KEY = os.environ.get("NVU_GATEWAY_API_KEY", "nv-gw-token")

# ─── Proxy Role ────────────────────────────────────────────────────────────
# "passthrough" — serves /v1/chat/completions (OpenAI format)
PROXY_ROLE = os.environ.get("PROXY_ROLE", "passthrough")

# ─── Logging ──────────────────────────────────────────────────────────────
LOG_DIR = os.environ.get("LOG_DIR", "/app/logs")

# ─── NVCF pexec configuration (三模型 pass-through, 各 agent 各后端) ──────
# 3model (2026-07-01): 从单 dsv4p_nv 坍缩态扩为多模型直路由, 三 agent 各对应一真实后端.
#   hermes   → kimi_nv  (f966661c nvquery-kimi-k2_6)
#   opencode → dsv4p_nv (74f02205 ai-deepseek-v4-pro)
#   openclaw → glm5_2_nv (3b9748d8 ai-glm-5_2)
# R704 (2026-07-05): 已下架的旧 tier 此处移除, 仅保留 kimi/dsv4p/glm5_2 三模型.
# 思考能力抓包实测 (key1 直连 NVCF, 完整 dump 全字段, 足 max_tokens + 推理题):
#   - dsv4p 74f02205(ai-deepseek): 普通模式最快(1.8-4.9s 首字节). thinking:{type:enabled}/reasoning_effort
#     都会让 74f02205 进入慢推理模式(首字节 12-49s) → strip 全部思考参数, inject 空.
#   - kimi f966661c: reasoning_effort/thinking/chat_template_kwargs 三种都触发, 用 reasoning_effort.
#   - glm5_2 3b9748d8: chat_template_kwargs.enable_thinking 唯一有效 (reasoning_effort 无效, rc=None).
# 教训: NVCF 每个 function 思考触发参数各不相同, 不能假设统一, 必须逐个完整 dump 抓包.
# inject 字段语义: dict, key=要注入的 body 参数路径, value=要设的值; 客户端已自带该参数则不覆盖.
NVCF_BASE_URL = os.environ.get("NVCF_BASE_URL", "api.nvcf.nvidia.com")
# R_multi (2026-07-02): function_id → function_ids (有序候选列表).
# NVCF function 有 ACTIVE→DEGRADING→DEGRADED→INACTIVE 生命周期 + 间歇 surge 故障.
# 单一 function 一旦 surge/下架, 该模型全网不可用. 多候选 + func_health 健康度自动切换:
# handlers/upstream 按 per-function 健康度选首个健康候选, surge 的自动跳过, 恢复后自动回切.
# 顺序 = 首选优先; env 可覆盖首选 (NVCF_*_FUNCTION_ID 覆盖候选[0]).
NVCF_PEXEC_MODELS = {
    "kimi_nv": {
        # 首选 f966661c (nvquery-kimi-k2_6, ACTIVE, 中国直连秒回); 备选 f966661c 同 id 无其他 ACTIVE 候选 → 单元素
        "function_ids": [os.environ.get("NVCF_KIMI_FUNCTION_ID",
                                        "f966661c-790d-4f71-b973-c525fb8eafd4")],
        "strip_params": ["thinking_budget"],  # NVCF 拒 thinking_budget → 400
        "inject": {"reasoning_effort": "low"},
    },
    "dsv4p_nv": {
        # 首选 74f02205 (ai-deepseek-v4-pro, ACTIVE, 中国直连秒回); 备选 8915fd28 (sglang, surge 间歇挂死, 恢复时可用)
        "function_ids": [os.environ.get("NVCF_DEEPSEEK_FUNCTION_ID",
                                        "74f02205-c7ba-438f-b81a-2537955bd7ec")],
        "strip_params": ["reasoning_effort", "stream_options", "thinking"],  # reasoning_effort: strip 客户端 xhigh (openclaw thinkingDefault). stream_options: handlers.py:196 给所有 stream 请求加 stream_options.include_usage, 但 74f02205 带该字段首字节 5x 慢且常挂死. thinking: strip 客户端/防旧 inject.
        # ★ R694 抓包实测 (2026-07-04) — 四段递进定位:
        #   1) integrate 端点对 deepseek-v4-pro 30s 挂死 → NV_INTEGRATE_MODELS 设空, 全走 pexec.
        #   2) pexec 74f02205 + stream_options.include_usage → 首字节 2.8→14.1s 且常 28s timeout → strip stream_options.
        #   3) pexec 74f02205 + thinking:{type:enabled} + 复杂prompt → 首字节 12-49s → timeout → strip thinking.
        #   4) pexec 74f02205 + reasoning_effort=medium (无 thinking) + 代码prompt → 首字节 >40s (still slow!).
        #      但完全无思考参数 → 首字节 1.8-4.9s ✅. 结论: reasoning_effort=medium 也会让 74f02205 进入慢推理模式
        #      (即便不输出 rc 字段). 故 inject 必须为空 — 不注入任何思考参数, deepseek 普通模式秒回.
        #   - 8915fd28(sglang, failover): 同一 strip 也去掉 reasoning_effort, sglang 普通模式也快 (不触发思考).
        #   方案: strip reasoning_effort + stream_options + thinking, inject 空 {}.
        #   74f02205 普通模式首字节 1.8-4.9s, 25s UPSTREAM_TIMEOUT 充足. is_thinking_req=False (inject 空) → 走默认 25s.
        "inject": {},  # 空: 不注入任何思考参数. deepseek-v4-pro 74f02205 普通模式最快 (1.8-4.9s 首字节).
    },
    "glm5_2_nv": {
        # 2026-07-03: NVCF 上线 ai-glm-5_2 (3b9748d8, ACTIVE, ownedByDifferentAccount=True=NVIDIA官方).
        # 抓包探测: glm-5.2 思考触发参数 = chat_template_kwargs.enable_thinking
        #   或 thinking:{type:enabled} (OpenAI 风格, 也生效); reasoning_effort 无效 (rc=None).
        #   裸请求无思考 (rc=None), 必须显式触发.
        #   触发后 finish=stop (非 length), 思考消耗 ~400-535 tokens, content 正常 — 健康.
        # strip 掉 reasoning_effort/thinking 防干扰, 由 inject 补 chat_template_kwargs.
        "function_ids": [os.environ.get("NVCF_GLM52_FUNCTION_ID",
                                        "3b9748d8-1d85-40e8-8573-0eeaa63a4b63")],
        "strip_params": ["thinking_budget", "reasoning_effort", "thinking"],
        # R797: NVCF 3b9748d8 thinking 路径 504 退化 (2026-07-07 直连实测 5/5 false=200, true=504).
        # 停 inject enable_thinking, 走普通模式 (同 dsv4p_nv 策略). 普通模式 5/5 200 <4s.
        # 思考输出 (reasoning_content) 丧失 — 但 thinking 路径已 504 不可用, 保 content 优于全失.
        # NVCF 恢复 thinking 后可改回 (env 无 inject 覆盖, 改此行 + restart).
        "inject": {},  # R854: 禁强制 thinking. GLM5.2 thinking 模式实测把答案写进 reasoning_content(4000c) 但 content 空(0c) + finish=length(涨满 max_tokens), CC 报 empty/filtered completion. 普通模式 content 正常. R827 注释 content 正常 已 stale.
    },
}
# 向后兼容: 部分老代码/测试可能读 nvcf_cfg["function_id"], 暴露首选 (候选[0]) 避免 KeyError.
# 新代码应直接读 ["function_ids"] 列表 + func_health.select_healthy_function().
for _m in NVCF_PEXEC_MODELS:
    NVCF_PEXEC_MODELS[_m]["function_id"] = NVCF_PEXEC_MODELS[_m]["function_ids"][0]

# ─── NV API keys for NVCF pexec (all models use same 5 keys) ──────────────
NVU_KEYS = []
for i in range(1, 6):
    key = os.environ.get(f"NVU_KEY{i}", "")
    if key:
        NVU_KEYS.append(key)
NVU_NUM_KEYS = len(NVU_KEYS)

# ─── Per-key mihomo SOCKS5 proxy URLs ──────────────────────────────────────
# K1→7894, K2→direct, K3→7896, K4→direct, K5→7899  (Rproxy: empty=direct)
NVU_PROXY_URLS = []
for i in range(1, 6):
    url = os.environ.get(f"NVU_PROXY_URL{i}", "")
    NVU_PROXY_URLS.append(url)  # Rproxy: keep ALL slots incl. empty for correct index alignment

# ─── R784: Per-key egress IP/route mapping (for long-term IP-diversity analysis) ──
# 每个 key 实际走哪个出口 IP + 人类可读 route 标签, 写入 DB nv_requests.egress_ip/egress_route.
# IP 从 env NVU_EGRESS_IP<n> 读 (便于 IP 变化时改 env 不改代码); route 从 proxy_url 推导.
#   - proxy_url 空 = "direct" route (容器宿主网络直连)
#   - proxy_url 非空 = "mihomo-<port>" route (socks5 代理出口)
NVU_EGRESS_IPS = []
for i in range(1, 6):
    NVU_EGRESS_IPS.append(os.environ.get(f"NVU_EGRESS_IP{i}", ""))


def egress_info_for_key(key_idx):
    """Return (egress_route, egress_ip) for a given key index.

    R784: 用于 metrics 记录, 写入 DB 做长期 IP-稳定性分析.
    route: 'direct' 或 'mihomo-<port>' 或 'unknown'
    ip: 从 NVU_EGRESS_IP<n> env 取 (配置时硬编码, 运行时不解析代理出口)
    """
    if key_idx >= len(NVU_PROXY_URLS):
        return ("unknown", "")
    proxy_url = NVU_PROXY_URLS[key_idx]
    ip = NVU_EGRESS_IPS[key_idx] if key_idx < len(NVU_EGRESS_IPS) else ""
    if not proxy_url or proxy_url.strip() == "":
        route = "direct"
    else:
        # 从 socks5h://host:port 提取 port (用 rsplit 避免 import re)
        port = proxy_url.strip().rsplit(":", 1)[-1] if ":" in proxy_url else "?"
        route = f"mihomo-{port}"
    return (route, ip)

def egress_info_for_integrate_key(key_idx):
    """Return (egress_route, egress_ip) for integrate path. R828.

    integrate 走 NV_INTEGRATE_PROXY_URLS[key_idx % len], 与 pexec 的 NVU_PROXY_URLS 不同.
    无 integrate 代理配置时回退到 egress_info_for_key.
    """
    if not NV_INTEGRATE_PROXY_URLS:
        return egress_info_for_key(key_idx)
    idx = key_idx % len(NV_INTEGRATE_PROXY_URLS)
    proxy_url = NV_INTEGRATE_PROXY_URLS[idx]
    ip = NV_INTEGRATE_EGRESS_IPS[idx] if idx < len(NV_INTEGRATE_EGRESS_IPS) else ""
    port = proxy_url.strip().rsplit(":", 1)[-1] if ":" in proxy_url else "?"
    return (f"integrate-mihomo-{port}", ip)


if NVU_NUM_KEYS < 5:
    print(f"[NV-CONFIG] WARN: only {NVU_NUM_KEYS} NV keys configured (expected 5)", file=sys.stderr, flush=True)

# ─── Three-model tiers (3model 2026-07-01: 各 agent 各后端, 无跨 tier fallback) ───
# NV_MODEL_TIERS 仅用于 get_tier_index 定位 start tier; upstream.execute_request 改 tier_order=[mapped_model]
# 单元素, 天然无跨 tier fallback (各 agent 各后端语义, 不允许 deepseek 悄悄变 glm5.2).
# R704: 旧已下架 tier 移除.
NV_MODEL_TIERS = ["kimi_nv", "dsv4p_nv", "glm5_2_nv"]

NV_MODEL_IDS = {
    "kimi_nv": "moonshotai/kimi-k2.6",
    "dsv4p_nv": "deepseek-ai/deepseek-v4-pro",
    "glm5_2_nv": "z-ai/glm-5.2",
}

DEFAULT_NV_MODEL = "glm5_2_nv"  # R2143 (cc2, 2026-07-21): dsv4p_nv NVCF pexec 端点 09:18 CST 起整体 404 "Inference error" (per-account deploy diff / function DEGRADED, 非重启引起 非软挂), dsv4p_nv 30min 123req/0OK=0% SR; 同窗 glm5_2_nv 49/49=100%. cc4101(cc2 自流量)发 model=cc-glm5-2 (未识别名) → fallback 此处, 旧值 dsv4p_nv 把 cc2 流量拐进失效端点 → 内存中 all_tiers_exhausted 502. 切 default→glm5_2_nv 让 cc2裸名流量重路由到健康 tier. 显式 deepseek-v4-pro 映射不变 (仍 dsv4p_nv, 乃 peer opencode 流量, 其 404 乃 NVCF 上游问题非 cc2 可解). .bak.R2143. 改后 docker compose restart nv_gw.

# ─── Integrate direct path (R572: 5-key 全走 integrate 首选, pexec 降为 fallback) ───
# 实测 (2026-07-02): integrate.api.nvidia.com 的 /v1/chat/completions 路径
#   - 延迟 3-13s 平均 8.9s (pexec 15-28s, 快 2-3x)
#   - 成功率 10/10 (pexec 有 surge/502)
#   - 思考触发: thinking:{type:enabled} (与 pexec 74f02205 完全一致, 复用 inject)
#   - 限流: per-KEY (不是 per-IP!), 单 key ~6-12/min 窗口, 冷却 1-2min
#   - 多 key 独立: key2 限流不影响同 IP 的 key4 (已验证)
#   - 5 key 合计 ~50 RPM (hermes 峰值 8/min 远低于)
# 策略: 5 key rr 轮换走 integrate, 全局 1.5s 延时分摊; 429 立即跳 key + 90s 冷却;
#       全限流 → fallback 现有 pexec 通道 (保证不宕).
NV_INTEGRATE_ENABLED = os.environ.get("NV_INTEGRATE_ENABLED", "1") == "1"
NV_INTEGRATE_HOST = os.environ.get("NV_INTEGRATE_HOST", "integrate.api.nvidia.com")
NV_INTEGRATE_PATH = "/v1/chat/completions"
# 429 冷却时长 (秒). 实测单 key 429 冷却 1-2min, 取 90s 保守.
NV_INTEGRATE_KEY_COOLDOWN_S = int(os.environ.get("NV_INTEGRATE_KEY_COOLDOWN_S", "90"))
# 全 key 限流时, 标记整个 integrate 路径冷却多久 (强制走 pexec).
NV_INTEGRATE_PATH_COOLDOWN_S = int(os.environ.get("NV_INTEGRATE_PATH_COOLDOWN_S", "60"))
# 哪些 model 走 integrate 首选 (其余 model 直接走 pexec, 不受影响).
# 默认只 dsv4p_nv (openclaw 主力, 流量最大 82%). kimi/glm5_2 流量低, 保持 pexec.
NV_INTEGRATE_MODELS = os.environ.get("NV_INTEGRATE_MODELS", "dsv4p_nv").split(",")
# R827: integrate 路径专用美国代理(per-key). integrate.api.nvidia.com 对 glm5_2 有地理限制,
# 只接受美国出口IP(JP/SG 卡死40s). pexec 仍用 NVU_PROXY_URLS(全直连)互不影响.
# 逗号分隔, 按 key_idx 取模轮换. 空=直连(兼容).
NV_INTEGRATE_PROXY_URLS = [u.strip() for u in os.environ.get("NV_INTEGRATE_PROXY_URLS", "").split(",") if u.strip()]
# R828: integrate per-port 真实美国出口IP (对应 NV_INTEGRATE_PROXY_URLS 顺序)
NV_INTEGRATE_EGRESS_IPS = [ip.strip() for ip in os.environ.get("NV_INTEGRATE_EGRESS_IPS", "").split(",") if ip.strip()]

# ─── R838: per-key 跨链路调度 (per-model 粒度) ────────────────────────────
# 指定哪些 model 的哪些 key(1-based) 首选 integrate, 其余 key 走 pexec. 与 NV_INTEGRATE_MODELS
# (模型级全 key) 互补: model 在 NV_INTEGRATE_MODELS → 全 key integrate; 否则查本表, 命中的 key
# 先试 integrate 失败回退 pexec, 不在表的 key 走 pexec.
# 格式: "model:key1,key2;model2:key3" (model=内部 tier 名 kimi_nv/dsv4p_nv/glm5_2_nv).
# 旧格式纯数字 "5" 向后兼容 = 应用到所有不在 NV_INTEGRATE_MODELS 的 model.
# 例: "dsv4p_nv:5" = 仅 dsv4p 的 K5 先试 integrate. 空=不启用(完全回滚).
def _parse_nv_key_integrate(raw):
    out = {}
    if not raw:
        return out
    if ":" not in raw:
        # 旧格式: 纯数字列表, 应用到所有非 NV_INTEGRATE_MODELS 的 model
        keys = [int(x.strip()) - 1 for x in raw.split(",") if x.strip()]
        return {"__all__": keys}
    for part in raw.split(";"):
        if ":" not in part:
            continue
        mdl, kstr = part.split(":", 1)
        mdl = mdl.strip()
        keys = [int(x.strip()) - 1 for x in kstr.split(",") if x.strip()]
        if mdl and keys:
            out[mdl] = keys
    return out
NV_KEY_INTEGRATE_KEYS_MAP = _parse_nv_key_integrate(os.environ.get("NV_KEY_INTEGRATE_KEYS", ""))
def nv_key_integrate_keys_for(tier_model):
    """Return list of 0-based key idxs that should try integrate first for this model. R838."""
    if tier_model in NV_KEY_INTEGRATE_KEYS_MAP:
        return NV_KEY_INTEGRATE_KEYS_MAP[tier_model]
    if "__all__" in NV_KEY_INTEGRATE_KEYS_MAP and tier_model not in NV_INTEGRATE_MODELS:
        return NV_KEY_INTEGRATE_KEYS_MAP["__all__"]
    return []
# per-key 跨链路时这些 key 的 integrate 代理(逗号分隔, 顺序对齐该 model 的 key 列表).
# 空=复用 NV_INTEGRATE_PROXY_URLS 按 key_idx 轮换.
NV_KEY_INTEGRATE_PROXY_URLS = [u.strip() for u in os.environ.get("NV_KEY_INTEGRATE_PROXY_URLS", "").split(",") if u.strip()]
NV_KEY_INTEGRATE_EGRESS_IPS = [ip.strip() for ip in os.environ.get("NV_KEY_INTEGRATE_EGRESS_IPS", "").split(",") if ip.strip()]
# integrate 限流白名单: 收到 429 的 key 标冷却, rr 轮到自动跳过 (复用 cooldown.py 的
# per-(tier_model, key_idx) 机制, tier_model 用 "<model>_integrate" 虚拟 tier 名隔离).

# ─── R839: glm5_2_nv per-key-mode 动态切换链 (5 模式递进) ─────────────────
# GLM5.2 极度不稳定: 今天 pexec+direct 稳明天 integrate+5美国IP 稳, 必须动态切换.
# 本机制 = "当前生效 mode" 是一个跨请求持久化的动态指针 (NOT per-key 静态绑定):
#   - 当前 key 用当前 mode 发请求;
#   - 故障 (429/timeout/empty200/连接错/5xx) → 换下一个 key + mode 递进到下一档;
#   - 稳住 → 保持当前 mode (不递进), 下一个 key 继续用这个 mode;
#   - mode 只往前递进不回退 (避免反复撞已知不稳的 mode); 后端整体恢复后由定时测速
#     脚本 (glm52_speedtest, 每天 02:00/14:00) 重排 NV_GLM52_MODE_CHAIN 顺序实现"软重置".
# 模式定义 (channel, ip_strategy):
#   pexec_direct        = pexec + 直连
#   pexec_us_rr         = pexec + 5 美国 IP 轮换 (NV_GLM52_RR_US_PROXIES)
#   integrate_us_rr     = integrate + 5 美国 IP 轮换
#   pexec_us_single     = pexec + 单一最快美国 IP (NV_GLM52_SINGLE_US_PROXY, 7894->193 两机共有)
#   integrate_us_single = integrate + 单一最快美国 IP
# 与 R572/R838b 互斥: 仅 tier_model=="glm5_2_nv" 且配置了 NV_GLM52_MODE_CHAIN 时触发,
# R839 分支在 R838b/R572 之前, 命中即 return, 不命中落到原逻辑.
NV_GLM52_MODE_CHAIN_RAW = os.environ.get("NV_GLM52_MODE_CHAIN", "")
def _parse_glm52_mode_chain(raw):
    """Parse NV_GLM52_MODE_CHAIN into list of (mode_name, channel, ip_strategy)."""
    if not raw or not raw.strip():
        return []
    valid = {
        "pexec_direct":        ("pexec", "direct"),
        "pexec_us_rr":         ("pexec", "rr_us"),
        "integrate_us_rr":     ("integrate", "rr_us"),
        "pexec_us_single":     ("pexec", "single_us"),
        "integrate_us_single": ("integrate", "single_us"),
    }
    out = []
    for tok in [t.strip() for t in raw.split(",") if t.strip()]:
        if tok in valid:
            ch, ip = valid[tok]
            out.append((tok, ch, ip))
        else:
            print(f"[NV-GLM52-CONFIG] WARN unknown mode token ignored: {tok!r}", file=sys.stderr, flush=True)
    return out
NV_GLM52_MODE_CHAIN = _parse_glm52_mode_chain(NV_GLM52_MODE_CHAIN_RAW)
# 单一最快美国 IP 代理 (两机共有 7894->193). 默认空 (走 NV_INTEGRATE_PROXY_URLS[0] 兜底).
NV_GLM52_SINGLE_US_PROXY = os.environ.get("NV_GLM52_SINGLE_US_PROXY", "")
# 5 美国 IP 轮换代理列表 (pexec_us_rr / integrate_us_rr 用). 默认空 → 回退 NV_INTEGRATE_PROXY_URLS.
NV_GLM52_RR_US_PROXIES = [u.strip() for u in os.environ.get("NV_GLM52_RR_US_PROXIES", "").split(",") if u.strip()]
# ── R1621b: per-key mode 绑定 (反转 R1621 方向) + key→proxy 一对一绑定 ──────────
# 用户真实意图: 正常请求 RR 轮流 k1~k5, 每 key 走自己绑定的 mode (非"故障才 fallback").
# k1/k3/k5→integrate_us_rr, k2/k4→pexec_us_rr. 某 key 失败→cooldown 该 key→跳下一 key(走它自己 mode).
# KEY_MODE_BINDING: "key_idx:mode_name;key_idx:mode_name" (0-based key idx). 未绑定的 key → mode_idx 指针兜底.
# NV_GLM52_KEY_PROXY_BIND: "k_idx,k_idx:proxy,proxy;k_idx,k_idx:proxy,proxy" — key 与 proxy 按位置对应.
_km_raw = os.environ.get("KEY_MODE_BINDING", "").strip()
KEY_MODE_BINDING = {}
if _km_raw:
    for tok in _km_raw.split(";"):
        tok = tok.strip()
        if not tok or ":" not in tok: continue
        kstr, mname = tok.split(":", 1)
        if kstr.strip().lstrip("-").isdigit():
            KEY_MODE_BINDING[int(kstr)] = mname.strip()
_kpb_raw = os.environ.get("NV_GLM52_KEY_PROXY_BIND", "").strip()
NV_GLM52_KEY_PROXY_MAP = {}
if _kpb_raw:
    for grp in _kpb_raw.split(";"):
        grp = grp.strip()
        if not grp or ":" not in grp: continue
        klist, plist = grp.split(":", 1)
        ks = [int(x) for x in klist.split(",") if x.strip().lstrip("-").isdigit()]
        ps = [u.strip() for u in plist.split(",") if u.strip()]
        for _k, _p in zip(ks, ps):
            NV_GLM52_KEY_PROXY_MAP[_k] = _p
# 持久化 current_mode_idx (跨请求保持上次稳定的 mode, mode 只往前递进不回退).
# 复用 rr_counter.json 同款机制 (写入 LOG_DIR/glm52_mode_idx.json).
NV_GLM52_MODE_IDX_FILE = os.path.join(LOG_DIR, "glm52_mode_idx.json")

# R839 re-export: state machine lives in glm52_mode_idx.py (mirrors rr_counter pattern).
from .glm52_mode_idx import (  # noqa: E402
    glm52_current_mode_idx,
    glm52_save_mode_idx,
    glm52_reset_mode_idx,
)

# ─── Cross-model fallback (已删除 R753) ───────────────────────────────────
# R753: 删除 FALLBACK_GRAPH 跨 model fallback. 原因: 41xx 适配器 (cx4102/opclaw4103/
# hm4104/oc4105) 已做跨后端同模型 fallback (nv_gw→ms_gw), nv_gw 内部跨 model fallback
# 会让 agent 看到的模型不一致 (glm5.2 请求可能返回 dsv4p 输出), 违反模型一致性原则.
# 现在 nv_gw 只做单 model 5 key 轮转, 全挂返 5xx 让 41xx 切后端.
# 保留: func_health (intra-model function 选择, B 类), PEER-FB (跨机同 model), key cooldown.

# ─── Tier timeout budget ──────────────────────────────────────────────────
TIER_TIMEOUT_BUDGET_S = float(os.environ.get("TIER_TIMEOUT_BUDGET_S", "60"))

# ─── Agent suffix (unify-nv: _nv 通用, 非 Hermes 专属) ───────────────────
AGENT_SUFFIXES = {
    "_nv": {"name": "NVCus", "format": "openai"},
}
DEFAULT_AGENT_SUFFIX = "_nv"

# ─── Model name mapping (3model 2026-07-01: pass-through, 不再坍缩) ─────
# 三模型各自路由到对应内部 key, 不再统一坍缩到 dsv4p_nv.
# detect_nv_model() 对未知名 fallback 到 DEFAULT_NV_MODEL (dsv4p_nv).
MODEL_MAP = {
    "kimi_nv": "kimi_nv",
    "kimi-k2.6": "kimi_nv",
    "moonshotai/kimi-k2.6": "kimi_nv",
    "dsv4p_nv": "dsv4p_nv",
    "deepseek-v4-pro": "dsv4p_nv",
    "deepseek-ai/deepseek-v4-pro": "dsv4p_nv",
    "glm5_2_nv": "glm5_2_nv",
    "glm5.2": "glm5_2_nv",
    "z-ai/glm-5.2": "glm5_2_nv",
}

def detect_nv_model(model_id: str) -> str:
    """Map a frontend model name to the internal NV model key.

    Returns: one of kimi_nv / dsv4p_nv / glm5_2_nv. Falls back to
    DEFAULT_NV_MODEL for unrecognized names.
    """
    mapped = MODEL_MAP.get(model_id, None)
    if mapped and mapped in NV_MODEL_IDS:
        return mapped
    return DEFAULT_NV_MODEL

def get_tier_index(mapped_model: str) -> int:
    """Get the tier index for a mapped model."""
    try:
        return NV_MODEL_TIERS.index(mapped_model)
    except ValueError:
        return 0

# ─── Token estimation ──────────────────────────────────────────────────────
CHARS_PER_TOKEN_ESTIMATE = float(os.environ.get("CHARS_PER_TOKEN_ESTIMATE", "3.0"))

# ─── Outbound throttle ──────────────────────────────────────────────────────
MIN_OUTBOUND_INTERVAL_S = float(os.environ.get("MIN_OUTBOUND_INTERVAL_S", "1.5"))
_outbound_last_sent = 0.0
_outbound_throttle_lock = threading.Lock()

def throttle_outbound():
    """Enforce MIN_OUTBOUND_INTERVAL_S between consecutive outbound requests."""
    if MIN_OUTBOUND_INTERVAL_S <= 0:
        return
    global _outbound_last_sent
    with _outbound_throttle_lock:
        now = time.monotonic()
        elapsed = now - _outbound_last_sent
        wait = MIN_OUTBOUND_INTERVAL_S - elapsed
        if wait > 0:
            time.sleep(wait)
            now = time.monotonic()
        _outbound_last_sent = now

# ─── Context window (3model: 三模型各 131072) ───────────────────────────
MODEL_INPUT_TOKEN_SAFETY = {
    "kimi_nv": 131072,   # kimi 仍 128K (上游未开放 1M)
    "dsv4p_nv": 131072,  # dsv4p 仍 128K
    "glm5_2_nv": 1048576,  # R2188: glm5.2 NVCF/z.ai 已开放 1M, DB 实测 253987c 200 成功
}
DEFAULT_CONTEXT_FALLBACK = 131072

# ─── Thread locks for logging ────────────────────────────────────────────
_log_lock = threading.Lock()
_metrics_lock = threading.Lock()
_error_detail_lock = threading.Lock()

# ─── Re-exports for backward compatibility (Reng modularization) ──────────
# These state machines were extracted to their own modules. Re-export here so
# all existing `from .config import _next_nv_key / is_key_cooling / ...`
# statements in handlers.py and upstream.py keep working unchanged.
# NOTE: imported at end-of-file so LOG_DIR / NVU_NUM_KEYS (needed by rr_counter)
# are already defined when the import resolves.
from .rr_counter import (  # noqa: E402
    _next_nv_key,
    _peek_nv_key,
    _save_rr_counter,
)


# ─── R502: Stream upgrade for non-stream requests ──────────────────────
# Non-stream reqs to NVCF have ~48%% SR vs ~87%% for stream (kimi-k2.6 thinking).
# NVCF server must complete full inference before sending first byte in non-stream,
# causing frequent pexec_timeout. Stream mode avoids this by establishing TTFB earlier.
# FORCE_STREAM_UPGRADE=1: upgrade non-stream → stream internally, accumulate SSE,
# return non-stream JSON to caller. Zero caller-visible change.
# R502: When force-stream-upgrade is active, non-stream requests are sent as stream
# to NVCF. Thinking requests (injected thinking:type:enabled) need longer for first
# byte. This override extends the per-attempt upstream timeout for upgraded requests
# only (original non-stream callers). Default: 55s (vs 25s normal), giving thought
# models more time to emit the first SSE chunk.
NVU_FORCE_STREAM_UPGRADE_TIMEOUT = int(os.environ.get('NVU_FORCE_STREAM_UPGRADE_TIMEOUT', '55'))
NVU_FORCE_STREAM_UPGRADE = os.environ.get('NVU_FORCE_STREAM_UPGRADE', '0')
# R576 (2026-07-03): per-model 排除 force-stream 升级.
# dsv4p_nv 流式+thinking 实测 content 丢失 90% (19/21 content=0c): deepseek-v4-pro 流式时
# 思考消耗 max_tokens, 正式 content 在末尾 chunk, finish=length 时根本不产生 content.
# dsv4p 走 integrate 非流原生 26-35s 正常返回 content (远低于 61s timeout), 无需 force-stream.
# R577 (2026-07-03): +glm5_2_nv. _accumulate_stream_to_nonstream 重组非流JSON时只提取
# delta.content/reasoning_content, 不提取 delta.tool_calls → 工具调用结构丢失
# (finish=tool_calls 但 tool_calls=null content空). glm5.2 直接打NVCF非流工具调用完美,
# 思考也快(3-6s 远低61s timeout), 无需 force-stream. 排除后走原生非流, tool_calls 保留.
NVU_FORCE_STREAM_EXCLUDE_MODELS = [m for m in os.environ.get('NVU_FORCE_STREAM_EXCLUDE_MODELS', 'dsv4p_nv,glm5_2_nv').split(',') if m]

# ─── 跨机 peer fallback (2026-07-01, 用户要求两台互备) ──────────────────
# 本机 nv_gw 在 all_tiers_exhausted (单 tier 5 key 全失败) 时, 转发请求到对端 nv_gw
# 同模型, 而非直接返回 502. 对端同样 all_keys_exhausted 才真正返回 502.
# 循环防护: 转发请求带 X-Fallback-Hop: 1 头, 对端收到该头 ≥1 时不再转发 (无状态 hop count).
# 安全约束 (cc2 三轮仲裁): 只在 tier 耗尽时转发, 不在单 key SSL error 转发
#   (否则 F-fix 删的跨机重试以转发形式复活, 且两次跨机往返比本地重试慢).
# 透传: 流式 SSE + 非 JSON 均透传, 对端响应原样回客户端.
# env: NVU_PEER_FALLBACK_URL (对端 nv_gw base, 如 http://100.109.57.26:40006)
#      NVU_PEER_FALLBACK_ENABLED (1 开启, 默认关)
NVU_PEER_FALLBACK_ENABLED = os.environ.get('NVU_PEER_FALLBACK_ENABLED', '0') == '1'
NVU_PEER_FALLBACK_URL = os.environ.get('NVU_PEER_FALLBACK_URL', '').rstrip('/')
# 转发请求自身的超时 (秒). 对端 nv_gw 内部有自己的 tier budget, 这里只限转发整体上限.
NVU_PEER_FALLBACK_TIMEOUT = int(os.environ.get('NVU_PEER_FALLBACK_TIMEOUT', '120'))

# ─── R1648c: nv→ms fallback (5key 全坏兜底, 仅 glm5_2_nv) ─────────────────
# R1648 框架: fallback 从 cc4101 下沉到 nv_gw. NVCF 5key×mode 链全挂
# (all_keys_exhausted) 时, nv_gw 自己 POST ms_gw (ModelScope, glm5_2_ms, 每日限额
# 兜底). 对 cc4101/CC 透明 (返回的 openai SSE 经现有 handler 路径, /v1/messages 再经
# oai_to_anth 转 anthropic). 与 R753 删的跨 *model* fallback 不同: R753 删的是跨 NVCF
# 模型 (dsv4p↔glm5_2↔kimi); R1648c 是跨 *后端* (NVCF→ModelScope, 同 glm5.2 模型族),
# 仅 glm5_2_nv (dsv4p/kimi 无对应 ms 模型).
# env: NVU_MS_FALLBACK_URL (ms_gw chat-completions 全 URL, 如 http://ms_gw:40007/v1/chat/completions)
#      NVU_MS_FALLBACK_ENABLED (1 开启, 默认关 — 先验证再开)
#      NVU_MS_FALLBACK_TOKEN (ms_gw token, 默认 ms-gw-token)
#      NVU_MS_FALLBACK_MODEL (ms 侧模型名, 默认 glm5_2_ms)
#      NVU_MS_FALLBACK_TIMEOUT (POST ms_gw 整体超时, 秒; 默认 120, ms_gw 内有自己的 variant 冷却)
#      NVU_MS_FALLBACK_FAIL_THRESHOLD (nv breaker 阈值: 连续全挂 N 次后 OPEN 直走 ms, 默认 15)
#      NVU_MS_FALLBACK_SKIP_S (OPEN 冷却秒数, 期间直走 ms, 默认 30)
NVU_MS_FALLBACK_ENABLED = os.environ.get('NVU_MS_FALLBACK_ENABLED', '0') == '1'
NVU_MS_FALLBACK_URL = os.environ.get('NVU_MS_FALLBACK_URL', 'http://ms_gw:40007/v1/chat/completions').rstrip('/')
NVU_MS_FALLBACK_TOKEN = os.environ.get('NVU_MS_FALLBACK_TOKEN', 'ms-gw-token')
NVU_MS_FALLBACK_MODEL = os.environ.get('NVU_MS_FALLBACK_MODEL', 'glm5_2_ms')
NVU_MS_FALLBACK_TIMEOUT = int(os.environ.get('NVU_MS_FALLBACK_TIMEOUT', '120'))
NVU_MS_FALLBACK_FAIL_THRESHOLD = int(os.environ.get('NVU_MS_FALLBACK_FAIL_THRESHOLD', '15'))
NVU_MS_FALLBACK_SKIP_S = int(os.environ.get('NVU_MS_FALLBACK_SKIP_S', '30'))
# 仅 glm5_2_nv 享受 ms fallback (其他模型无对应 ms 后端). execute_request 内判定用.
NVU_MS_FALLBACK_MODELS = {m.strip() for m in os.environ.get('NVU_MS_FALLBACK_MODELS', 'glm5_2_nv').split(',') if m.strip()}

# ─── R2224: peek 内部换 key 重试 (撤 40007 第一步: 恢复职责下沉 nv_gw 内部) ─
# R1716 peek barrier 在 send_response(200) commit message_start 前判健康. 软挂时
# 旧逻辑直接调 _ms_fallback_request 切外部 ms_gw 后端. 本开关: 软挂后先在 nv_gw
# 内部换下一个 NVCF key 重放整个请求 (peek 窗口内 message_start 未 commit, 安全),
# 内部重试也软挂才落 ms_gw (二线保留). ChatGPT 确认 commit-point 边界: peek 窗口内
# 可安全换 key, peek 之后只能 graceful end (不动).
#   NVU_PEEK_RETRY_KEYS: 内部换 key 次数, 默认 2 (ChatGPT 建议限 1-2, 不试满 5T
#     打穿 SLA). 0 = 禁用 (回退现状, 直接走 ms_gw), 作回滚开关.
#   NVU_PEEK_RETRY_BUDGET_S: 内部重试总 budget 上限秒, 0 = 用 _fb_s 单 key 上限
#     (按 input 分档 20/60/45/60s), 不另设总上限.
NVU_PEEK_RETRY_KEYS = int(os.environ.get('NVU_PEEK_RETRY_KEYS', '2'))
NVU_PEEK_RETRY_BUDGET_S = float(os.environ.get('NVU_PEEK_RETRY_BUDGET_S', '0'))

# ─── R1673: 超大 input big-input breaker env (独立于 R1648c nv_breaker) ───────
# NVCF glm5.2 对 ~250k+ chars 超大 input 系统性 200-then-hang (~115s/次, CC 死循环 1h+).
# 连续 N 次超大 input hang 失败 → OPEN, cooldown 内对超大 input 直走 ms_gw 省 ~115s.
# 默认 ENABLED=1 (与 NVU_MS_FALLBACK_ENABLED 联动: ms fallback 关则本 breaker 无处可降级).
# 阈值 250000 (数据: <250k 各档 SR 71-100%, 250-300k 骤降至 29.2%).
NVU_BIG_INPUT_THRESHOLD = int(os.environ.get('NVU_BIG_INPUT_THRESHOLD', '250000'))
NVU_BIG_INPUT_FAIL_N = int(os.environ.get('NVU_BIG_INPUT_FAIL_N', '3'))
NVU_BIG_INPUT_COOLDOWN_S = int(os.environ.get('NVU_BIG_INPUT_COOLDOWN_S', '180'))
NVU_BIG_INPUT_MODELS = {m.strip() for m in os.environ.get('NVU_BIG_INPUT_MODELS', 'glm5_2_nv').split(',') if m.strip()}

# ─── R835/R839/R840: stream deadline + zombie empty 检测 (HM1 移植) ──────────
# R835: 流式 idle deadline (首字节后). 兜 SSE keep-alive 喂饭式卡死.
# R839: 首字节前绝对 deadline. 兜 upstream 200头但 body 首字节永不来.
# R840: 空僵尸响应检测. finish_reason=stop 但 content 极少 + 无 tool_calls
#       + 大 context → 判假完成空响应, 不写终末 chunk, 写 content_filter error
#       SSE chunk → openclaw throw → fallback 链生效 (避免 8min 卡死).
NVU_STREAM_TOTAL_DEADLINE_S = float(os.environ.get("NVU_STREAM_TOTAL_DEADLINE_S", "90"))
NVU_STREAM_FIRST_BYTE_DEADLINE_S = float(os.environ.get("NVU_STREAM_FIRST_BYTE_DEADLINE_S", "20"))
# R1781: passthrough 流式绝对 wall-clock 总 cap (秒). 不被任何 chunk 刷新. 旧洞: stream_idle_deadline
# (=NVU_STREAM_TOTAL_DEADLINE_S=90s 思考×2=180s) 名字像总 deadline 实为 idle gap — 每收到真内容就刷新,
# 一个 "TTFB→吐一点→hang 89s→再吐一点→再 hang" 的请求能反复刷新 escape, DB 实测 stream_no_content_gap
# 7 个全 128-210s (4 个超 TIER_TIMEOUT_BUDGET_S=180). 而正常 200 流式 2h 182 个 max=102s p99=71s
# (无一超 120s). 绝对 cap=120 落在正常上限 102s 与失败下限 128s 之间 (18s buffer), 零误杀正常请求,
# 把 no_content_gap 总时长从 210s 压到 ≤120s (用户少挂死 90s). 失败仍 record nv_breaker (R1719 不重放).
NVU_STREAM_ABSOLUTE_CAP_S = float(os.environ.get("NVU_STREAM_ABSOLUTE_CAP_S", "120"))
# R1927: per-key 指数退避开关 (监督者 21:00/21:15 指数退避+ms 双层方案 step2.1-a).
# 0/未设 = 关 (沿用 min(UPSTREAM_TIMEOUT, remaining) 均匀 per-attempt timeout, 当前行为).
# 1 = 开: _glm52_single_attempt per-key timeout 按 attempt_idx 指数递增 (60/120/240, 封顶 240),
# 配合 chain_budget 420s 容 3 key 指数和, 让 NVCF "慢但活着" 的请求 (实测 114 成功 ttfb 58-148s)
# 有时间等到首字节而非被 66s UPSTREAM_TIMEOUT 提前杀掉换 key. 数学保证: nv 420s + ms 5s = 425s
# < CC API_TIMEOUT_MS 600s, 留 175s 余量 (cc4101 STREAM_TOTAL_DEADLINE 已 480, header 待对齐).
NVU_GLM52_EXP_BACKOFF = os.environ.get("NVU_GLM52_EXP_BACKOFF", "0") == "1"
# R1927: 指数退避档位 (秒). attempt_idx 0->60s, 1->120s, 2->240s, 3+ 封顶 240s.
# 60/120/240 三档累计 420s = chain_budget (NVU_TIER_BUDGET_GLM5_2_NV env 120->420).
NVU_GLM52_EXP_BACKOFF_STEPS = [int(x) for x in os.environ.get(
    "NVU_GLM52_EXP_BACKOFF_STEPS", "60,120,240").split(",") if x.strip()]
NVU_GLM52_EXP_BACKOFF_CAP = int(os.environ.get("NVU_GLM52_EXP_BACKOFF_CAP", "240"))
# R1407: 真内容 idle gap 硬兜底 (秒). NVCF 大 context 请求可能返回 200 头 + 持续空 chunk 但无真内容,
# cc4101 非-thinking 100s stall-watcher 会先 kill + emit api_error → CC 报 "Server error mid-response"
# (CC 不重试 mid-flight api_error). 此值 60s < 100s, 让 nv_gw 先主动断流 + 发 content_filter error chunk,
# 避免 cc4101 stall + DB 伪装 200. thinking 流自动翻倍 (120s 容纳长思考).
NVU_STREAM_NO_CONTENT_GAP_S = float(os.environ.get("NVU_STREAM_NO_CONTENT_GAP_S", "60"))
# R1768: thinking 模式下 gap 的放大系数. 旧值硬编码 *2 (base 60 -> thinking 120s).
# 实测 (2h 窗口 7 个 stream_no_content_gap, 全 120s 整, total_input_chars 75k-97k thinking
# 请求) 上游 prefill 静默撞满 120s; 而 cc4101 活源码已移除 idle-gap stall-watcher, 仅留
# CC4101_STREAM_TOTAL_DEADLINE_S=360s 总时长兜底 + UPSTREAM_IDLE_TIMEOUT=150. 即 nv_gw 思考
# gap 现 < cc4101 360s 充裕. 放宽到 3.0 (thinking 180s) 给 75k-97k prefill 多 60s, 仍远 < 360s,
# nv_gw 依旧先于 cc4101 总 deadline 主动断发 err_chunk (设计意图保留). 默认 2.0=旧行为可回滚.
NVU_STREAM_THINKING_GAP_SCALE = float(os.environ.get("NVU_STREAM_THINKING_GAP_SCALE", "2.0"))
# R1408: 流式 read 短轮询 timeout. getresponse 后把 socket read timeout 设成此值 (用
# resp.fp.raw._sock, 因 conn.sock 在 getresponse 后为 None, 同 cc4101 R853 坑), 让
# resp.read(8192) 每最多 POLL_S 秒抛 socket.timeout -> except 内 continue -> 循环顶的
# 60s/90s/20s deadline 检查真正能跑 (旧洞: read 阻塞在 NVCF 200-then-hang 的静默期,
# deadline 检查在循环顶但 read 不返回就永远跑不到 -> cc4101 100s stall 先命中 -> mid-response).
NVU_STREAM_POLL_S = float(os.environ.get("NVU_STREAM_POLL_S", "15"))
NVU_ZOMBIE_EMPTY_CONTENT_CHARS = int(os.environ.get("NVU_ZOMBIE_EMPTY_CONTENT_CHARS", "50"))
NVU_ZOMBIE_MIN_INPUT_CHARS = int(os.environ.get("NVU_ZOMBIE_MIN_INPUT_CHARS", "5000"))
# R1627: stream 全量缓冲模式. 1=收到 NVCF 200 后不立即向下游 flush, 缓冲到流结束
# (finish_reason/[DONE]) 再一次性 flush. NVCF 中途卡死 (gap/timeout/zombie) 时丢弃缓冲,
# 因从未 flush 任何字节 → 等价 Scenario A (零内容) → 发 content_filter error chunk →
# cc4101 → api_error → CC 自动重试下个 key (DB 实锤 Scenario A CC 会重试 1-2 次).
# 根治 Scenario B (mid-response 已 flush 内容后卡死) 导致 CC 卡死需手动"继续"的大 BUG.
# 0=旧行为 (边读边 flush, Scenario B 仍存在). 失败可立即回退.
NVU_STREAM_FULL_BUFFER = os.environ.get("NVU_STREAM_FULL_BUFFER", "1").strip() != "0"
from .cooldown import (  # noqa: E402
    is_key_cooling,
    mark_key_cooling,
    reset_key429_count,
    KEY_COOLDOWN_S,
    TIER_COOLDOWN_S,
    is_key_auth_failed,
    mark_key_auth_failed,
    KEY_AUTHFAIL_COOLDOWN_S,
    is_tier_degraded,
    mark_tier_degraded,
    TIER_DEGRADED_COOLDOWN_S,
)
