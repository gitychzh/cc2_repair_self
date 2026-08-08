# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: **R1238 (NOP 巡检轮 — cc2-primary 100% (52/52), 0 失败; 唯一失败聚类 = hermes 线 all_tiers_exhausted × 2 (~180s, out-of-scope), 不改码)**
> 主链 fid: **281478d0-f307** 稳定, dsv4f0731_nv 单模式 (active 流量)
> 全 caller (30min): `200|76`+`502|1` → dsv4f0731_nv SR=98.7% (76/77)。
> **cc4101-primary (cc2 主链) = 200|52 → SR=100%, 本轮 0 失败**。
> 连多窗 cc2-primary 100% 健康延续。唯一失败聚类 all_tiers_exhausted×2 (~180s/条) 归属
> **hermes 单 caller** (同刻 5key 瞬挂, RemoteDisconnected/Timeout spread), 而 cc2 同窗 52 次全成功 —
> 非共享 NVCF jitter, out-of-scope, NOP 自愈即可。
> per-key k0~k4 全 bind fid 281478d0-f307, 45min 分布正常 (k0:18/k1:17/k2:17/k3:17/k4:22),
> tier transient 全属 hermes 请求, cc2 请求无 tier error。
> fallback 0%。buffer 正常 (1 条 cc2 attempt-2 5s backoff 自愈, 无 exhausted)。
> 容器 health ok (nv_gw 5 keys, cc4101 primary=dsv4f0731_nv)。

## 本轮 (R1238) 改动 + 依据 + 验证

### 改动: 无 (NOP)。cc2-primary SR=100% (52/52), 0 失败; 唯一失败聚类 = hermes 线
### all_tiers_exhausted (out-of-scope), 无杠杆可改, 如实记录下轮观察。

### 依据 (注入分析, 2026-08-08 11:34 CST / 03:34 UTC + DB 复核)

- **30min 全 caller**: cc4101-primary `200|52`, hermes `200|24`+`502|1` → **dsv4f0731_nv SR=98.7% (76/77)**。
- **cc4101-primary (cc2 主链) = 200|52 → SR=100%, 本轮 0 失败** (DB 复核 cc4101-primary status!=200 → 0 rows)。
- **错误分类 30min**: `all_tiers_exhausted × 1` (duration_ms=180029), DB 复核归属 **caller=hermes**,
  request_id=1a6a4b35 (45min 窗另有 hermes 937fe7b2, 同画像 ~179s)。**非 cc2 主链, out-of-scope**。
- **tier attempts 30min**: pexec_success 主导。NVCFPexecRemoteDisconnected + NVCFPexecTimeout 弥散跨 key,
  每条归属**独立 hermes 请求** (4847d338/75882c89/b8a770e4/c7e78710 单条 transient),
  hermes 线 937fe7b2 = 3×RemoteDisconnected+1×Timeout → hermes 单 caller 5key 瞬挂。**cc2 请求无任何 tier error**。
- **per-key 45min fid 分布**: k0:18/k1:17/k2:17/k3:17/k4:22 全 bind 281478d0-f307 (正确单模式 fid), 分布正常。
  无 single-key-stuck, 无单线杠杆。
- **fallback**: 0% (cc_requests 全 fallback_triggered=f) — cc2 主链 52/52 全直连 NVCF。
- **buffer/wait 日志**: 正常 — 1 条 cc4101-primary 请求 attempt-2 5s backoff 后自愈 (50s, 无 exhausted),
  其余全 attempt-1 success。keymanager 无 clip/429 累积。
- **容器**: nv_gw /health ok (5 keys + dsv4f0731_nv), cc4101 /health ok (primary=dsv4f0731_nv)。

### 验证
无改动, 无 restart。cc2-primary 100% (52/52), 唯一失败聚类 hermes all_tiers_exhausted (out-of-scope),
非共享 NVCF jitter (cc2 同窗 52 次全成功), fallback 0%, 5 key 健康, buffer 正常。容器 health ok。

## 参数快照 (nv_gw + cc4101, 与 R1234/R1235/R1236 一致, 无漂移)

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
R1233 (SR 99.1%, 唯一 502 = hermes 线 NVStream_IncompleteRead (diff request, 不聚类),
cc2-primary 100% (72/72)) → R1234 (SR 99.2%, 唯一 502 = hermes 线 NVStream_IncompleteRead
(连 3 窗同画像 diff request, 不聚类), cc2-primary 100% (76/76)) → R1235 (**SR 100% (116/116),
全 caller 0 错误, hermes 线 IncompleteRead 收敛, cc2-primary 100% (73/73)**) → R1236
(**SR 100% (116/116), 连 2 窗全绿 0 错误, cc2-primary 100% (74/74), 0 失败**) → R1237
(**SR 100% (117/117), 连 3 窗全绿 0 错误, cc2-primary 100% (80/80), 0 失败, fallback 0%**) →
R1238 (**cc2-primary 100% (52/52), 0 失败; 全 caller SR=98.7% 因 hermes 线 all_tiers_exhausted×2
单独判, 非共享 jitter, out-of-scope NOP 自愈**)。
NVCF-side 弥散 transient 持续收敛, 5key/IP 全健康, 无 c2 失败聚类, 连 4 窗 cc2-primary NOP。

## 下一步
1. **维持观察不改码**。cc2 主链 100% (连 4 窗 R1235-R1238 NOP), 无 cc2 失败聚类, 无 mihomo 逐线
   排查需求 (R1207 门槛未触发)。
2. **hermes 线 all_tiers_exhausted** (本轮 ×2, ~180s): 单 caller 同刻 5key 瞬挂, 非共享 NVCF jitter
   (cc2 同窗 52 次全成功)。若 hermes all_tiers_exhausted 连续多轮复发且开始跨 caller 同刻失败
   (共享 jitter 画像), 才升级排查; 否则 NOP 自愈观察。
3. **ms_gw fallback**: NVU_DISABLE_MS_FALLBACK=0 恢复启用中, 本轮无 NVCF jitter 触发 (fallback 0%), 不动。