# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: **R1179 (NOP 巡检 — 实查 30min cc4101-primary 200|117 = 100% SR, 0 非-200;
> 总线 dsv4f0731_nv 全 200 0 错误; tier 全 pexec_success 均分 0 错误;
> fallback 0%; buffer 全 attempt-1 direct flush 无退避无 WAIT; 整窗全绿跨二十二轮 → NOP 不改码)**
> 主链 fid: **281478d0-f307** 稳定, dsv4f0731_nv 单模式
> 错误分类 (实查, 30min): (无错误 — 0 非-200)
> 根因: 链上静稳, 全窗 0 错误
> 最新 30min (04:33 CST): **cc2-primary 全 200 117/117 = 100% SR, 0 非-200**
> fallback: **0%**

## 本轮 (R1179) 改动 + 依据 + 验证

### 改动: 无 (NOP 巡检轮。cc2 整窗 117/117 全 200, 总线全 200, 无改码条件)

### 依据 (注入链路分析 2026-08-08 04:32 CST + 实查 30min 窗口)

- **实查 30min cc4101-primary**: `200|117` = 100% SR, 0 非-200。
- **实查 30min 总线**: dsv4f0731_nv 202/202 全 200, 0 错误。
- **错误分类 (实查)**: `nv_requests` status != 200 → **0 行** (完全无错误)。
- **tier (实查)**: 118 全 `pexec_success`, 分布均匀 (k0-k4: 24/25/23/22/24),
  0 错误, 无 429/empty/新类型。
- **fallback**: 总线全 200, 无触发 → **0%** (118 total, 0 触发)。
- **buffer 日志 (实查)**: 所有请求 `attempt=1/5` → `success` (success_tool_call /
  success_text), 全部 direct flush (elapsed 1-14s) 无退避、无 WAIT、无 buffer_exhausted。

### 验证
实查 cc4101-primary 117/117 = 100% SR, 0 非-200; 总线 202/202 全 200 0 错误; fallback 0%;
tier 全 pexec_success; buffer 全 attempt-1 direct flush
无退避无 WAIT; nv_gw/cc4101 health ok; 链路稳定无改码条件。

## 参数快照 (nv_gw + cc4101, 本轮注入无变更)

- **nv_gw**: UPSTREAM_TIMEOUT=90, TIER_TIMEOUT_BUDGET_S=180, NVU_BUFFER_MAX_RETRIES=5
  (stairs 90×5=450s), NVU_DISABLE_MS_FALLBACK=0, NVU_FORCE_STREAM_UPGRADE=0,
  NVU_PEER_FB_SKIP_MODELS=glm5_2_nv,dsv4p_nv, KEY_COOLDOWN_S=30, INTEGRATE_KEY_COOLDOWN_S=90,
  TIER_COOLDOWN_S=180, MIN_OUTBOUND_INTERVAL_S=10, NVU_BUFFER_CALLERS=cc4101-primary,openclaw2,
  (全 key bind fid index 0=281478d0-f307, dsv4f0731_nv 单模式)。
- **cc4101**: PRIMARY_UPSTREAM_MODEL=dsv4f0731_nv, PRIMARY_UPSTREAM_URL=http://nv_gw:40006/v1/messages,
  FALLBACK_UPSTREAM_MODEL=glm5_2_ms, FALLBACK_UPSTREAM_URL=http://ms_gw:40007/v1/chat/completions,
  CC4101_STREAM_TOTAL_DEADLINE_S=470, PRIMARY_HEADER_TIMEOUT=400, PRIMARY_FAIL_THRESHOLD=3,
  PRIMARY_SKIP_S=30, UPSTREAM_TIMEOUT=130, UPSTREAM_IDLE_TIMEOUT=150。

## 上轮
R1178 (NOP — 实查 116/116 全 200, 总线全 200 0 错误) → R1179 确认:
实查 117/117 全 200, 总线 202/202 全 200 0 错误, 链路持续静稳无新事件。
链路跨二十二轮全绿。

## 下一步
维持静稳观察。**核心监控: 是否重现独立瞬时 burst 及复发间隔**。
Burst2 后已持续无任何 cc2 异常, 穿越二十二轮 (R1158→R1179) 整窗全绿。
若下个窗口再现 ≥2× buffer_exhausted 且 request_id 全新 (JOIN 归属 cc2), 则为**独立新事件**,
按记忆 `ssleof-error-transient-egress-blip` 深挖 mihomo dsv4f0731_nv egress 线路 (7900-7904),
评估超 5 key 超大请求 buffer 首跳韧性。当前仍判定瞬时 egress 抖动非配置漂移, NOP。