# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: **R1169 (NOP 巡检 — 实查 30min cc4101-primary 200|110 = 100% SR, 0 非-200, 总线 0 错误;
> 总线 dsv4f0731_nv SR=100% (181/181) 全 200 无任何非-200; tier 全 pexec_success (110)
> 无 429/empty; fallback 0%; buffer 无退避无 WAIT; 整窗全绿跨十二轮
> → NOP 不改码)**
> 主链 fid: **281478d0-f307** 稳定 (全 5 key pexec), dsv4f0731_nv 单模式
> 错误分类 (surface, 30min): (无错误 — 0 非-200)
> 根因: 链上静稳, 全窗 0 错误
> 最新 30min (03:30-04:00 CST): **cc2-primary 全 200 110/110 = 100% SR, 0 非-200**
> fallback: **0%** (cc_requests 直查 0 触发)

## 本轮 (R1169) 改动 + 依据 + 验证

### 改动: 无 (NOP 巡检轮。cc2 整窗 110/110 全 200, 总线 181/181 全 200, 无改码条件)

### 依据 (注入链路分析 2026-08-08 03:55 CST + 实查 30min + 容器健康)

- **实查 30min cc4101-primary**: `200|110` = 100% SR, 0 非-200。
- **实查 30min 总线**: cc4101-primary 110 + hermes 71 = 181 全部 `200`,
  无任何非-200, 总线 SR = **100% (181/181)**。上轮唯一 hermes 瞬时 502 未复发,
  印证其为一次性瞬时 first-byte 抖动非复发。
- **错误分类 (实查)**: `nv_requests` status != 200 → **0 行** (完全无错误)。
- **tier (实查)**: 全 `pexec_success` (24/21/19/23/23 = 110), 无 429/empty/新类型, 无冷却退避。
- **fallback (实查)**: 0 触发 (总线 181 全 200, 无 fallback 条件)。
- **buffer 日志 (注入)**: (无 buffer/wait/keymanager 异常日志) = 无退避、无 WAIT、无 buffer_exhausted。
- **容器 (实查)**: nv_gw + cc4101 /health 全 ok, nv_gw Up 24h / cc4101 Up 24h /
  nv_gw_stable Up 6d。

### 验证
实查 cc4101-primary 110/110 = 100% SR, 0 非-200; 总线 181/181 全 200 0 错误;
fallback 0%; tier 全 pexec_success 无新类型; buffer 无退避无 WAIT; 容器全健康。
链路稳定无改码条件。

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
R1168 (NOP — 实查 108/108 全 200, 总线 179/179 全 200 0 错误) → R1169 确认:
实查 110/110 全 200, 总线 181/181 全 200 0 错误, 上轮 hermes 502 未复发。
链路跨十二轮全绿无新事件。

## 下一步
维持静稳观察。**核心监控: 是否重现独立瞬时 burst 及复发间隔**。
Burst2 后已跨 ~200+ min 无任何 cc2 异常, 穿越十二轮 (R1158→R1169) 整窗全绿。
若下个窗口再现 ≥2× buffer_exhausted 且 request_id 全新 (JOIN 归属 cc2), 则为**独立新事件**,
按记忆 `ssleof-error-transient-egress-blip` 深挖 mihomo dsv4f0731_nv egress 线路 (7900-7904),
评估超 5 key 超大请求 buffer 首跳韧性。当前仍判定瞬时 egress 抖动非配置漂移, NOP。