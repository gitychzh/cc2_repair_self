# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: **R1229 (semi-NOP 观察轮 — SR 97.1%, 2 真实 502 buffer_exhausted, NVCF-side 弥散瞬态, 不改码)**
> 主链 fid: **281478d0-f307** 稳定, dsv4f0731_nv 单模式 (active 流量)
> 失败 (30min cc4101-primary): `200|67 + 502|2` → SR=97.1% (67/69)。
> 根因: 共享 NVCF 上游瞬时连接抖动 (buffer_exhausted, ~118-128s), 与 R1228 同类同 terminal 签名。
> 差异: R1228 跨 caller 相关 (hermes 同挂), 本轮 hermes 同小时 100% — jitter 簇更窄/更短, 仅 cc2 撞上。
> 3 失败 request 无 egress_ip 归属 (死在跨 key buffer 内), 全 egress IP/key 健康 (无单线杠杆)。
> 技术触发 mihomo 排查条件 (SR<99%) 但无单线集中恶化, 判 NVCF-side 瞬态, 不改码观察 (R1077)。
> 容器: nv_gw /health ok (5 keys + dsv4f0731_nv fid 281478d0-f307), cc4101 ok

## 本轮 (R1229) 改动 + 依据 + 验证

### 改动: 无 (semi-NOP 观察轮)。SR 97.1% 未达 NOP 门槛, 但根因=共享 NVCF-side 弥散瞬态,
### 无 mihomo 单线/配置杠杆可改 (全 egress IP/key 健康), 贸然改线反增回归 (R1077)。如实记录, 下轮观察。

### 依据 (自查询, 2026-08-08 01:45 UTC)

- **30min cc2-primary**: `200|67 + 502|2` (buffer_exhausted, ~118-128s) → **SR=97.1% (67/69)**,
  2 个真实新 502 (新 request_id), 与 R1228 同 terminal 签名。
- **2h 全量失败**: 01:10:13 72e396bb / 01:19:49 a17ed596 / 01:40:06 ce5ec111, 全 buffer_exhausted 118-128s。
- **跨 caller (同小时)**: cc4101-primary 98 总 3 bad, **hermes 78 总 0 bad** → 与 R1228 跨 caller 相关不同,
  本轮 jitter 簇更窄/更短, 仅 cc2 单 caller 撞上, NVCF-side 范围收窄。
- **per-egress-IP 2h**: 193→100% (169), 195→100% (114), 180→100% (113), 197→100% (91)。
  3 个失败 request **无 egress_ip 归属** (空) → 死在跨 key buffer 内, 未到任何单线。无单一差线。
- **per-key 2h**: k0~k4 各 62~69 pexec_success, transient (NVCFPexecRemoteDisconnected/Timeout)
  弥散 k0/k1/k2/k3 (3/1/2/2), 每失败 attempt 已换 key, 无 single-key-stuck。
- **容器**: nv_gw /health ok, cc4101 ok, 参数无漂移 → 非配置回归。

### 验证
无改动, 无 restart。buffer 内每 attempt 换 key + AKE fail-fast 生效; 最新窗口已 self-heal。容器 health ok。

## 参数快照 (nv_gw + cc4101, 与 R1228 一致, 无漂移)

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
R1228 (SR 96.6%, 2 真实 502, 跨 caller 相关) → R1229 (SR 97.1%, 2 真实 502, 仅 cc2 单 caller)。
两类同为 NVCF-side 弥散瞬时 jitter, 本窗口收窄, 5key/IP 全健康。无单线/配置杠杆, 不改码观察。

## 下一步
1. **维持观察不改码**。仅当出现 **单条 egress IP/key 集中恶化** (可达 ~1%+ 差线) 或
   连续 >2 轮 buffer_exhausted 聚类才拉 mihomo 逐线排查。当前未满足, 观察。
2. **跟踪 buffer_exhausted terminal 频率**: 弥散瞬态 self-heal 一贯有效 (单 req attempt-1/2);
   若转持续多 key 连续失败 (AKE fail-fast 频繁), 深入 NVCF 侧 (fid 健康/pos 备用) 排查。
3. **ms_gw fallback**: NVU_DISABLE_MS_FALLBACK=0 恢复启用中。本轮 buffer_exhausted fallback f=116
   无因 NVCF jitter 触发, 正常。无改动。
