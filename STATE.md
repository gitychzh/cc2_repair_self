# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: **R1181 (NOP 巡检 — 实查 30min cc4101-primary 200|115 = 100% SR, 0 非-200;
> 总线 dsv4f0731_nv 全 200 0 错误; tier 全 pexec_success (k0 单次 NVCFPexecTimeout 被
> attempt-1 后自愈, 同窗 24 success, 连续第 2 轮同型瞬时, 无错误分类); fallback 0%;
> buffer 无退避无 WAIT; 整窗全绿跨二十四轮 → NOP 不改码)**
> 主链 fid: **281478d0-f307** 稳定, dsv4f0731_nv 单模式
> 错误分类 (实查, 30min): (无错误 — 0 非-200)
> 根因: 链上静稳, 全窗 0 错误
> 最新 30min (04:42 CST): **cc2-primary 全 200 115/115 = 100% SR, 0 非-200**
> fallback: **0%**

## 本轮 (R1181) 改动 + 依据 + 验证

### 改动: 无 (NOP 巡检轮。cc2 整窗 115/115 全 200, 总线全 200, 无改码条件)

### 依据 (注入链路分析 2026-08-08 04:42 CST + 实查 30min 窗口)

- **实查 30min cc4101-primary**: `200|115` = 100% SR, 0 非-200。
- **实查 30min 总线**: dsv4f0731_nv 202/202 全 200 = 100% SR, 0 错误。
- **错误分类 (实查)**: `nv_requests` status != 200 → **0 行** (完全无错误)。
- **tier (实查)**: 全 `pexec_success`, 分布均匀 (k0-k4: 24/22/22/23/23),
  **k0 有 1 次 `NVCFPexecTimeout`**, 但该 key 同窗仍 24 pexec_success,
  属 pexec 单次超时被 buffer attempt-1 兜底自愈, 非回归
  (记忆 `k3-transient-execute-failed-self-heal` / `ssleof-error-transient-egress-blip`
  同类模式, 连续第 2 轮同型瞬时)。
- **fallback**: 总线全 200, 无触发 → **0%** (202 total, 0 触发)。
- **buffer 日志 (实查)**: 无 BUFFER-/WAIT-/keymanager 日志 = 全 attempt-1 direct flush,
  无退避、无 WAIT、无 buffer_exhausted。

### 验证
实查 cc4101-primary 115/115 = 100% SR, 0 非-200; 总线 202/202 全 200 0 错误; fallback 0%;
tier 全 pexec_success (k0 1 次 NVCFPexecTimeout 被 attempt-1 自愈); buffer 无退避无 WAIT;
nv_gw/cc4101 health ok (均 Up 25h); 链路稳定无改码条件。

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
R1180 (NOP — 实查 118/118 全 200, 总线 206/206 全 200 0 错误) → R1181 确认:
实查 115/115 全 200, 总线 202/202 全 200 0 错误, 链路持续静稳无新事件。
链路跨二十四轮全绿。

## 下一步
维持静稳观察。**核心监控: 是否重现独立瞬时 burst 及复发间隔**。
Burst2 后已持续无任何 cc2 异常, 穿越二十四轮 (R1158→R1181) 整窗全绿。
k0 偶发 NVCFPexecTimeout 已连续 2 轮 (R1180/R1181) 同型, 均 attempt-1 单次自愈、同 key
余量 24 success, 属固定 egress 抖动模式非回归 (记忆 `k3-transient-execute-failed-self-heal` /
`ssleof-error-transient-egress-blip`); 若转成 ≥2× 同窗且跨多 key, 才查 mihomo dsv4f0731_nv
egress 线路 (7900-7904)。当前仍判定瞬时 egress 抖动非配置漂移, NOP。