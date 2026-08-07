# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: **R1193 (NOP 巡检 — 活查 30min cc4101-primary 200|102 = 100% SR, 0 非-200;
> 总线 dsv4f0731_nv 注入 165/165 全 200 0 错误; tier 活查 102 全 pexec_success 0 error
> (连续六轮无瞬时); fallback 0%;
> buffer 全 attempt-1 direct flush 无退避无 WAIT;
> 整窗全绿跨三十六轮 → NOP 不改码)**
> 主链 fid: **281478d0-f307** 稳定, dsv4f0731_nv 单模式
> 错误分类 (活查, 30min): 0 非-200 行
> 根因: 链上静稳, 全窗 0 错误
> 最新 30min (~05:33 CST): **cc2-primary 全 200 102/102 = 100% SR, 0 非-200**
> fallback: **0%**

## 本轮 (R1193) 改动 + 依据 + 验证

### 改动: 无 (NOP 巡检轮。cc2 整窗 102/102 全 200, 总线全 200, 无改码条件)

### 依据 (注入链路分析 2026-08-08 05:32:33 CST + 活查 DB 复核)

- **活查 30min cc4101-primary**: `200|102` = 100% SR, 0 非-200
  (注入同窗 cc2 102, 活查复核一致)。
- **注入 30min 总线**: dsv4f0731_nv 165/165 全 200 = 100% SR
  (活查拆解 102 cc2 + 63 hermes), 0 非-200。
- **错误分类 (nv_requests)**: 活查 `status != 200` → **0 行** (完全无错误)。
- **tier (nv_tier_attempts)**: 活查 102 → 全 `pexec_success`, **0 error**。
  - 连续第六轮 (R1188→R1193) 完全无瞬时: R1187 的 k0 单次 NVCFPexecTimeout
    已持续自愈、本轮未复发, 属固定 egress 抖动非回归 (记忆
    `ssleof-error-transient-egress-blip` / `k3-transient-execute-failed-self-heal`)。
  - 无 429 / empty / 新错误类型。
- **fallback**: 活查 1776 total, 0 触发 → **0%**。
- **buffer 日志 (docker logs nv_gw --since 30m)**: 最近日志全 attempt-1 direct flush
  (`success_tool_call`, elapsed 5-15s, flush 2110b/3026b/28592b/10231b),
  无退避、无 WAIT-KEYMGR、无 buffer_exhausted。

### 验证
活查 cc4101-primary 102/102 = 100% SR, 0 非-200; 总线注入 165/165 全 200 0 错误; fallback 0%;
tier 活查 102 全 pexec_success 0 error; buffer 全 attempt-1 direct flush 无退避无 WAIT;
nv_gw (Up 31h)/cc4101 (Up 26h) health ok; 链路稳定无改码条件。

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
R1192 (NOP — 活查 109/109 全 200, 总线注入 172/172 全 200 0 错误) → R1193 确认:
活查 102/102 全 200, 总线注入 165/165 全 200 0 错误, 链路持续静稳无新事件。
链路跨三十六轮全绿。

## 下一步
维持静稳观察。**核心监控: 是否重现独立瞬时 burst 及复发间隔**。
Burst2 后已持续无任何 cc2 异常, 穿越三十六轮 (R1158→R1193) 整窗全绿。
k0 偶发 NVCFPexecTimeout 已连续 6 轮 (R1188→R1193) 未复发 (最近一次 R1187),
均 attempt-1 单次自愈、同 key 余量 21-22 success, 属固定 egress 抖动模式非回归 (记忆
`ssleof-error-transient-egress-blip` / `k3-transient-execute-failed-self-heal`);
若转成 ≥2× 同窗且跨多 key, 才查 mihomo dsv4f0731_nv egress 线路 (7900-7904)。
当前仍判定瞬时 egress 抖动非配置漂移, NOP。