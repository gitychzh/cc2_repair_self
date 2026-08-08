# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: **R1234 (NOP 巡检轮 — cc2-primary SR=100% (76/76), 唯一 502 归属 hermes 线 NVStream_IncompleteRead 非 cc2, 0 cc2 失败, 不改码)**
> 主链 fid: **281478d0-f307** 稳定, dsv4f0731_nv 单模式 (active 流量)
> 全 caller (30min): `200|118 + 502|1` → SR=99.2% (118/119)。
> **cc4101-primary (cc2 主链) = 200|76 → SR=100%, 本轮 0 失败**。
> 唯一 502 = hermes `NVStream_IncompleteRead` 38288ms (dsv4f0731_nv hermes 线), **归属非 cc2**。
> per-key k0~k4 全 pexec_success 主导 (12~18), NVCFPexecRemoteDisconnected 弥散 1-2/key attempt 换 key 自愈。
> 无 buffer_exhausted 归属 cc2, 无 deadline, 无任何 cc2 失败聚类。
> 容器 health ok (nv_gw 5 keys, cc4101 primary=dsv4f0731_nv)。

## 本轮 (R1234) 改动 + 依据 + 验证

### 改动: 无 (NOP)。cc2-primary SR=100% (76/76), 唯一 502 归属 hermes 线 (NVStream_IncompleteRead),
### 非 cc2 主链, 0 失败, 无杠杆可改, 如实记录下轮观察。

### 依据 (注入分析, 2026-08-08 10:22 CST / 02:22 UTC)

- **30min 全 caller**: cc4101-primary `200|76`, hermes `200|42 + 502|1` → **dsv4f0731_nv SR=99.2%**。
- **cc4101-primary (cc2 主链) = 200|76 → SR=100%, 本轮 0 失败**。
- **唯一 502**: hermes `NVStream_IncompleteRead` (avg_dur 38288ms), dsv4f0731_nv hermes 线 singular
  transient, 归属非 cc2 主链 (连 3 窗 R1232/R1233/R1234 同画像不同 request, 不聚类)。memory
  `primary-model-dsv4f0731-r1095`: zombie/IncompleteRead 多归属 hermes 线非 cc2; isolated 单条
  不聚类, 不动。
- **per-key 30min**: k0~k4 全 pexec_success 主导 (k0:15/k1:12/k2:18/k3:17/k4:14), transient
  NVCFPexecRemoteDisconnected 弥散 (k1:2/k3:1), 每条 attempt 换 key + AKE fail-fast, 无 single-key-stuck。
- **buffer/wait 日志**: 30min 无 buffer/wait/keymanager 日志, 全 attempt-1 success, 无 retry
  无 WAIT, 无 buffer_exhausted 归属 cc2。
- **容器**: nv_gw Up 31h /health ok (5 keys + dsv4f0731_nv), cc4101 Up 30h ok (primary=dsv4f0731_nv)。

### 验证
无改动, 无 restart。cc2-primary 100%, 全 key 健康, 唯一 502 归属 hermes 线非 cc2。容器 health ok。

## 参数快照 (nv_gw + cc4101, 与 R1233 一致, 无漂移)

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
R1232 (SR 99.2%, 唯一 502 = hermes 线 NVStream_IncompleteRead, cc2-primary 100% (77/77)) →
R1233 (SR 99.1%, 唯一 502 = hermes 线 NVStream_IncompleteRead (不同 request, 同画像, 不聚类),
cc2-primary 100% (72/72)) → R1234 (SR 99.2%, 唯一 502 = hermes 线 NVStream_IncompleteRead
(连 3 窗同画像不同 request, 不聚类), cc2-primary 100% (76/76), 0 失败)。NVCF-side 弥散 transient
完全收敛, 5key/IP 全健康, 无单线/配置杠杆, NOP。

## 下一步
1. **维持观察不改码**。cc2 主链 100%, 无失败聚类, 无 mihomo 逐线排查需求 (R1207 门槛未触发)。
2. **跟踪 hermes dsv4f0731_nv IncompleteRead**: 连 3 窗各 1 条 hermes 线 singular (R1232/R1233/
   R1234, 不同 request, 不聚类), 非 cc2, 不动。若跨 caller 同刻 502 聚类 (NVCF-side jitter 画像)
   才关注; 若 hermes 线 IncompleteRead 连续增长或跨 caller 弥散才升级观察。
3. **ms_gw fallback**: NVU_DISABLE_MS_FALLBACK=0 恢复启用中, 本轮无 NVCF jitter 触发, 不动。
