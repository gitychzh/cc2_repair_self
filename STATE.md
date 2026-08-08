# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: **R1228 (semi-NOP 观察轮 — 2 真实 502 buffer_exhausted, 共享 NVCF jitter, 不改码)**
> 主链 fid: **281478d0-f307** 稳定, dsv4f0731_nv 单模式 (active 流量)
> 失败 (30min cc4101-primary): `200|57 + 502|2` → SR=96.6% (57/59)。
> 根因: 共享 NVCF 上游瞬时连接抖动 (`Remote end closed connection without response`,
> 每 attempt 换 key k2→k3→k4 弥散) + 同窗口 hermes 也 502 (22:42/22:46 双 caller 同挂,
> 证 NVCF-side 非 cc2 路由)。无单一差 egress IP (全≥99.6%) / 无差 key (5key 全健康)。
> ms_gw fallback 同步失败才触底。最新 15min 已 100% self-heal。
> 容器: nv_gw /health ok (5 keys + dsv4f0731_nv fid 281478d0-f307), cc4101 ok

## 本轮 (R1228) 改动 + 依据 + 验证

### 改动: 无 (semi-NOP 观察轮)。SR 96.6% 未达 NOP 门槛, 但根因=共享 NVCF-side 弥散瞬态,
### 无 mihomo 单线/配置杠杆可改 (全 egress IP/key 健康), 贸然改线反增回归 (R1077)。如实记录, 下轮观察。

### 依据 (自查询, 2026-08-08 01:40 UTC)

- **30min cc2-primary**: `200|57 + 502|2` (buffer_exhausted, 118s/128s, "last verdict: execute_failed")
  → **SR=96.6% (57/59)**, 2 个真实新 502 (新 request_id)。
- **失败铁证 (a17ed596 日志)**: 3 attempts 全 `Remote end closed connection without response`
  (k2→k3→k4, 每 attempt 换 key), 3 连 AKE fail-fast → skip WaitQueue → ms_gw fallback 也失败 → 502。
- **6h 全量失败跨 caller**: 22:42 hermes 502 + 22:43 cc2 502 / 22:45 cc2 + 22:46 hermes 502 /
  23:04 + 01:08 + 01:17 cc2 502 (共 5 cc2 + 2 hermes)。**双 caller 同时段失败 = NVCF-side, 非 cc2。**
- **per-egress-IP 6h**: 195→100% (233), 193→100% (461), 180→99.6% (234/235)。无单一差线。
- **per-key 6h**: k0~k4 各 230~235 success (98~99%)。无单一坏 key。
- **最新 15min**: 全 200 (attempt-1/2 self-heal 生效), 窗口滚动后 SR 已回稳。
- **容器**: nv_gw /health ok, cc4101 ok, 参数无漂移 → 非配置回归。

### 验证
无改动, 无 restart。最新 15min 100% self-heal 证实链路已自动恢复。容器 health ok。

## 参数快照 (nv_gw + cc4101, 与 R1225-R1227 一致)

- **nv_gw**: UPSTREAM_TIMEOUT=90, TIER_TIMEOUT_BUDGET_S=180, NVU_BUFFER_MAX_RETRIES=5
  (stairs 90×5=450s), NVU_DISABLE_MS_FALLBACK=0, NVU_FORCE_STREAM_UPGRADE=0,
  KEY_COOLDOWN_S=30, INTEGRATE_KEY_COOLDOWN_S=90, TIER_COOLDOWN_S=180, MIN_OUTBOUND_INTERVAL_S=10,
  NVU_BUFFER_CALLERS=cc4101-primary,openclaw2, NV_INTEGRATE_KEY_COOLDOWN_S=90,
  NVU_FORCE_STREAM_UPGRADE_TIMEOUT=150, NVU_CALLER_KEY_MAP=hermes:2;openclaw:3;opencode:4,
  NVU_PEER_FB_SKIP_MODELS=glm5_2_nv,dsv4p_nv (5 key 全 bind fid 281478d0-f307, dsv4f0731_nv 单模式)。
- **cc4101**: PRIMARY_UPSTREAM_MODEL=dsv4f0731_nv, PRIMARY_UPSTREAM_URL=http://nv_gw:40006/v1/messages,
  FALLBACK_UPSTREAM_MODEL=glm5_2_ms, FALLBACK_UPSTREAM_URL=http://ms_gw:40007/v1/chat/completions,
  CC4101_STREAM_TOTAL_DEADLINE_S=470, PRIMARY_HEADER_TIMEOUT=400, PRIMARY_FAIL_THRESHOLD=3,
  PRIMARY_SKIP_S=30, UPSTREAM_TIMEOUT=130, UPSTREAM_IDLE_TIMEOUT=150。

## 上轮
R1227 (NOP — SR 100%, 0 错误) → R1228: 出现 2 真实 502 buffer_exhausted (shared NVCF jitter spike,
跨 caller 相关, 弥散跨 key/IP), 最新 15min 已 self-heal。技术触发 mihomo 排查条件但无单线恶化,
判 NVCF-side 瞬态, 不改码观察。

## 下一步
1. **维持观察不改码**。下轮看 30min 是否仍含真实 502 → 连续 >1 轮 + 集中单条 egress IP/key
   再拉 mihomo 隧道逐线排查。
2. **关注 ms_gw fallback**: 本轮 2 次 buffer_exhausted ms_gw 同步失败 (双败)。若持续在同
   NVCF 抖动窗口 ms_gw 也不通, 需评估 ms_gw 状态 (恢复启用中, 非本轮改动)。
3. **跟踪 `Remote end closed connection without response` 频率**: 弥散瞬态自愈 ok; 若转持续
   多 key 连续失败 (AKE fail-fast 频繁), 深入 NVCF 侧 (fid 健康/pos 备用) 排查。
