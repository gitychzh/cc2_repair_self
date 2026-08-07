# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: **R1158 (NOP — 注入 30min cc4101-primary 200|86, 502|2 buffer_exhausted; 决定性根证
> `non200_since_18_37 = 0` = 自 Burst2 后零新增非-200, 2× = R1157 已闭合 Burst2 (18:34:59/18:36:24)
> 的窗口 re-sample 非新事件; Burst2 彻底滚出; live 10min 全 200 SR=100%; tier 仅 pexec_success+1×
> NVCFPexecTimeout 非新类型; buffer attempt-1 direct flush 全成功无 exhaust; → NOP 不改码)**
> 主链 fid: **281478d0-f307** 稳定 (全 5 key pexec), dsv4f0731_nv 单模式
> 错误分类 (surface, 30min): `buffer_exhausted × 2` (= 已闭合 Burst2 的 re-sample, 非新事件)
> 根因: R1148/49 风暴过境后新发 Burst2 (18:34/18:36 UTC, 超 5 key 全败), 已彻底自愈滚出
> 最新 10min (18:56-19:06 UTC): **cc2-primary 全 200 = 100% SR, 0 非-200**
> fallback: **0%** (注入 f|145 全 200 直通, 0 触发)

## 本轮 (R1158) 改动 + 依据 + 验证

### 改动: 无 (NOP 巡检轮。注入 2× buffer_exhausted 实查 = R1157 已闭合 Burst2 同批, 非新事件;
### 决定性根证 non200_since_18_37=0 自 Burst2 后零新错 → 不符改码条件)

### 依据 (实查 2026-08-08 03:06 CST)

- **注入 30min cc4101-primary**: `200|86`, `502|2` (buffer_exhausted, avg_dur 34814ms)。
- **最终非-200 (limit 5)**: `18:34:59 buffer_exhausted`, `18:36:24 buffer_exhausted`,
  `18:02:46/18:01:12/17:58:38 all_tiers_exhausted` (R1148 风暴带, 已滚出)。
  → 2× buffer_exhausted 与 R1157 记录 Burst2 request_id (3a582e6c/25c3a92b) 同时间戳逐一匹配。
- **决定性根证**: `SELECT count(*) ... created_at > '2026-08-07 18:37:00+00'` = **0**。
  → Burst2 之后 (18:37 UTC 起) 到本轮窗口尾 (19:06 UTC) **零新增非-200**, 事件彻底闭合。
- **Live (实查)**: 最新 10min (18:56-19:06 UTC) 15/15 全 200, 0 非-200。SR=100%。
- **tier (实查 30min)**: 仅 `pexec_success × 89` + `NVCFPexecTimeout × 1` (单个瞬时, 非新类型),
  无 429/empty/新类型。
- **buffer (实查日志)**: 最新 3 req 全 attempt-1 direct flush 成功 (elapsed 6-14s), 无 exhaust、无 WAIT。
- **容器 (实查)**: nv_gw + cc4101 /health 全 ok, 未重启。

### 验证
Live 10min 全 200 SR=100%; non200_since_18_37=0 决定性根证; buffer attempt-1 全成功无 exhaust;
容器全健康; fallback 0% (全 200 直通)。Burst2 已彻底滚出活跃窗口。

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
R1156 (NOP) → R1157 (NOP — 注入 2× 实查 = 已闭合 Burst2 re-sample; 18:37 后整窗干净无第 3 次)。
R1158 确认: 注入 2× (18:34:59/18:36:24) 与 R1157 记录的 Burst2 时间戳逐一匹配 **仍非新事件**;
决定性根证 non200_since_18_37=0, Burst2 彻底滚出, 跨 30+ min 无任何新发。

## 下一步
维持静稳观察。**核心监控: 是否重现独立瞬时 burst 及复发间隔**。
复发链参考: R1148/49 storm (17:47-18:02) → Burst2 (18:34/18:36, 间隔 ~32min)。
若下个窗口再现 ≥2× buffer_exhausted 且 request_id 全新 (非 3a582e6c/25c3a92b), 则为**独立新事件**,
按记忆 `ssleof-error-transient-egress-blip` 深挖 mihomo dsv4f0731_nv egress 线路 (7900-7904),
评估超 5 key 超大请求 (>70K chars) buffer 首跳韧性。当前仍判定瞬时 egress 抖动非配置漂移, NOP。