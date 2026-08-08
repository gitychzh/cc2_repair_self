# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: **R1240 (NOP 巡检轮 — cc2-primary 100% (60/60), 0 失败; 唯一失败聚类 = hermes 线 3 条 (NVStream_IncompleteRead / all_tiers_exhausted / zombie_empty_completion, 全 out-of-scope), 不改码)**
> 主链 fid: **281478d0-f307** 稳定, dsv4f0731_nv 单模式 (active 流量)
> 全 caller (30min): `200|83`+`502|3` → dsv4f0731_nv SR=97.6% (83/86)。
> **cc4101-primary (cc2 主链) = 200|60 → SR=100%, 本轮 0 失败**。
> 连 6 窗 cc2-primary 100% 健康延续 (R1235-R1240 NOP)。唯一 3 条错误全属 hermes 线:
> 1) all_tiers_exhausted×1 (~179s, req 937fe7b2 同 R1238/R1239 画像, 同一 hermes 请求 5key 瞬挂)
> 2) zombie_empty_completion×1 (44s, hermes dsv4f0731_nv 线已知特症, 新出现 error type)
> 3) NVStream_IncompleteRead×1 (35s, hermes transient R1154 容忍带内)
> 全非共享 NVCF jitter (cc2 同窗 60 次全成功), out-of-scope, NOP 自愈即可。
> per-key k0~k4 全 bind fid 281478d0-f307, tier transient 全属 hermes 请求, cc2 请求无 tier error。
> fallback 0%。buffer 正常 (cc2 全 attempt-1 success, 唯一 986af010 k2 execute_failed attempt-2 自愈, 无 exhausted)。
> 容器 health ok (nv_gw 5 keys, cc4101 primary=dsv4f0731_nv)。

## 本轮 (R1240) 改动 + 依据 + 验证

### 改动: 无 (NOP)。cc2-primary SR=100% (60/60), 0 失败; 唯一错误聚类 = hermes 线 3 条
### (NVStream_IncompleteRead / all_tiers_exhausted / zombie_empty_completion, 全 out-of-scope),
### 无杠杆可改, 如实记录下轮观察。

### 依据 (DB 复核, 2026-08-08 12:04 CST / 04:04 UTC)

- **30min 全 caller**: cc4101-primary `200|60`, hermes `200|23`+`502|3` → **dsv4f0731_nv SR=97.6% (83/86)**。
- **cc4101-primary (cc2 主链) = 200|60 → SR=100%, 本轮 0 失败** (DB 复核 cc4101-primary status!=200 → 0 rows;
  cc_requests 61 条全 fallback_triggered=f)。
- **错误分类 30min (JOIN 归属 caller)**: **3 条 errors 全属 hermes, 无一属 cc2**:
  - `all_tiers_exhausted × 1` (178825ms, req **937fe7b2**) — 同 R1238/R1239 画像 (~180s),
    同一 hermes 请求 5key 瞬挂, 跨窗残留 re-sample, out-of-scope。
  - `zombie_empty_completion × 1` (44067ms, req 13b3f407) — hermes dsv4f0731_nv 线已知特症,
    new error type vs R1239, 记录观察。
  - `NVStream_IncompleteRead × 1` (35318ms, req 59692048) — hermes transient, R1154 容忍带内。
- **tier attempts 30min**: k0-k4 各有 NVCFPexecRemoteDisconnected/NVCFPexecTimeout 单条 transient
  (全属 hermes 请求), pexec_success 主导 cc2 全 key 无 tier failure。
- **fallback**: 0% (cc_requests 61 条全 fallback_triggered=f) — cc2 主链 60/60 全直连 NVCF。
- **buffer/wait 日志**: 唯一 cc2 异常 = req 986af010 k2 execute_failed attempt-1 → 5s backoff →
  attempt-2 success (55s self-heal, 健康)。其余 cc4101-primary 全 attempt-1 success, 无 exhausted/WAIT。
- **容器**: nv_gw /health ok (5 keys + dsv4f0731_nv), cc4101 /health ok (primary=dsv4f0731_nv)。

### 验证
无改动, 无 restart。cc2-primary 100% (60/60), 唯一错误聚类 hermes 线 3 条
(NVStream_IncompleteRead / all_tiers_exhausted / zombie_empty_completion, 全 out-of-scope),
非共享 NVCF jitter (cc2 同窗 60 次全成功), fallback 0%, 5 key 健康, buffer 正常。容器 health ok。

## 参数快照 (nv_gw + cc4101, 与 R1234-R1239 一致, 无漂移)

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
单独判, 非共享 jitter, out-of-scope NOP 自愈**) → R1239 (**cc2-primary 100% (56/56), 0 失败;
全 caller SR=98.8% 因 hermes 线 all_tiers_exhausted×1 (~179s) 单独判, 非共享 jitter, out-of-scope
NOP 自愈**) → R1240 (**cc2-primary 100% (60/60), 0 失败; 全 caller SR=97.6% 因 hermes 线 3 条
(2 旧画像 all_tiers_exhausted×1 + zombie_empty_completion×1 新出现 + IncompleteRead×1)
单独判, 非共享 jitter, out-of-scope NOP 自愈**)。
NVCF-side 弥散 transient 持续收敛, 5key/IP 全健康, 无 cc2 失败聚类, 连 6 窗 cc2-primary NOP。
zombie_empty_completion 为 R1240 窗 hermes 线新出现 error type, 记录观察。

## 下一步
1. **维持观察不改码**。cc2 主链 100% (连 6 窗 R1235-R1240 NOP), 无 cc2 失败聚类, 无 mihomo 逐线
   排查需求 (R1207 门槛未触发)。
2. **hermes 线 all_tiers_exhausted** (连 3 轮 R1238×2/R1239×1/R1240×1, ~180s, 同 req 937fe7b2
   跨窗残留 re-sample): 单 caller 同刻 5key 瞬挂, 非共享 NVCF jitter (cc2 同窗 60 次全成功)。
   若 hermes all_tiers_exhausted 连续多轮复发且开始跨 caller 同刻失败 (共享 jitter 画像),
   才升级排查; 否则 NOP 自愈观察。
3. **hermes 线 zombie_empty_completion** (R1240 新出现 ×1, 44s): hermes dsv4f0731_nv 线已知特症。
   记录观察, 若 hermes 连续多轮复发且跨 caller 才查。
4. **ms_gw fallback**: NVU_DISABLE_MS_FALLBACK=0 恢复启用中, 本轮无 NVCF jitter 触发 (fallback 0%), 不动。