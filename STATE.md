# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: **R1230 (NOP 巡检轮 — SR 98.75%, 1 边界重采样非新失败, latest 15min 100%, 不改码)**
> 主链 fid: **281478d0-f307** 稳定, dsv4f0731_nv 单模式 (active 流量)
> 失败 (30min cc4101-primary): `200|79 + 502|1` → SR=98.75% (79/80)。
> 唯一 502 ce5ec111@01:40 (buffer_exhausted, 122s) = **R1229 已记录失败的同 request 边界重采样**,
> **本轮 0 新 cc2 失败**。latest 15min cc4101-primary = 100% (41/41) self-heal 完好。
> hermes 线 1 个 NVStream_IncompleteRead (92eb7e97, k2) 非 cc2 主链 caller, 判属 hermes。
> 无 egress_ip/key 归属 (死在跨 key buffer 内), 全 egress IP/key 健康 (无单线杠杆)。
> 符 NVCF-side 弥散瞬态画像 (R1077), NOP 不再动线。容器 health ok。

## 本轮 (R1230) 改动 + 依据 + 验证

### 改动: 无 (NOP)。本轮唯一 cc2 502 是 R1229 已记录的 ce5ec111 边界重采样, 0 新失败,
### latest 15min 100% self-heal, 无单线/配置杠杆可改, 如实记录下轮观察。

### 依据 (自查询, 2026-08-08 01:56 UTC)

- **30min cc2-primary**: `200|79 + 502|1` → **SR=98.75% (79/80)**, 较 R1229 (97.1%) 回升。
- **唯一 502**: ce5ec111 @01:40 buffer_exhausted 122s, 与 **R1229 STATE 记录的同 request** (R1229
  窗口同见 01:40:06 ce5ec111), 本轮 = 滚动窗口边界 re-sample 判同一条, **非新 request**。
  R1229 另两个失败 (72e396bb/a17ed596) 已滚出窗。
- **latest 15min cc4101-primary**: `200|41` → **100% self-heal**。
- **hermes**: 92eb7e97 NVStream_IncompleteRead (k2) 38s → hermes 线, 非 cc2 主链 caller。判属 hermes。
- **per-key 30min**: k0~k4 全 pexec_success (14~16), transient NVCFPexecRemoteDisconnected 弥散
  k0:2/k1:1/k2:1/k3:1, 每失败已换 key, 无 single-key-stuck。
- **容器**: nv_gw /health ok (5 keys + dsv4f0731_nv), cc4101 ok, buffer 全 attempt-1 success (10-12s flush)
  无 retry 无 WAIT → 非配置回归。

### 验证
无改动, 无 restart。buffer attempt-1 success + 无 buffer_exhausted 复现, latest 15min 100%。容器 health ok。

## 参数快照 (nv_gw + cc4101, 与 R1229 一致, 无漂移)

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
R1229 (SR 97.1%, 2 真实 502 buffer_exhausted, 仅 cc2 单 caller) → R1230 (SR 98.75%,
唯一 502 为 R1229 边界重采样, 本轮 0 新失败, latest 15min 100%)。
NVCF-side 弥散瞬时 jitter 收敛, 5key/IP 全健康, 无单线/配置杠杆, NOP。

## 下一步
1. **维持观察不改码**。仅出现单条 egress IP/key 集中恶化 (可达 ~1%+ 差线) 或连续 >2 轮
   新 buffer_exhausted 聚类才拉 mihomo 逐线排查。当前 0 新失败, 观察。
2. **跟踪 buffer_exhausted**: ce5ec111 已跨 R1229/R1230 两轮 re-sample, 下一轮应滚出。
   若新 request 且跨多 key 连续失败 (AKE fail-fast 频繁), 深入 NVCF 侧排查。
3. **ms_gw fallback**: NVU_DISABLE_MS_FALLBACK=0 恢复启用中。本轮无因 NVCF jitter 触发, 不动。