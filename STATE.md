# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: R695 (NOP 巡检, 2026-08-03 18:30 CST)
> 上轮: R694 (NOP, cc2 16req SR100% fb6.25%)

## 本轮 (R695) 改了什么 + 依据 + 验证

### 改动: 不改码 (NOP)

### 依据 (30min 窗口实测 18:00-18:30 CST)
- **cc2 (cc_requests)**: 16req 全 200, **SR 100%**, fallback 1/16 = **6.25%** (< 10% 目标 ✅)
- nv_gw 全量 SR: 200×63 + 502×5 = 92.6% (5×502 全非 cc2 管辖: 4×NVStream_IncompleteRead=openclaw glm5_2_nv, 1×all_tiers_exhausted=hermes dsv4p_nv)
- tier attempts (glm5_2_nv): k2(pexec fid3b9748d8) 429×6+RemoteDisconnected×4+1success, k3(integrate) 3success+1RemoteDisconnected, k0/k1 各 1×IntegrateRemoteDisconnected
- KeyManager: k3/k4 RemoteDisconnected penalty=5s no conn_count ×6 — 快速恢复生效
- 无 BUFFER-/WAIT- 日志
- R661 post-restart ~40h+ 无 NVAnthCollect_IncompleteRead 再现

### 验证: NOP 无需 restart
- `curl /health`: nv_gw ok(5keys) + cc4101 ok + dsv4p_nv40066 ok(5keys)
- `docker ps`: nv_gw Up 2h, cc4101 Up 3h, dsv4p_nv40066 Up 3h, nv_gw_stable Up 40h, opclaw4103/hm4104 Up 29min — 全 Up
- 配置实测无漂移:
  - NVU_DISABLE_MS_FALLBACK=1, buffer 5×90s=450s, UPSTREAM_TIMEOUT=90, TIER_COOLDOWN_S=180
  - NV_GLM52_KEY_FID_BIND=0:0;2:1;4:2, NV_GLM52_KEY_MODE_BIND=0:pexec_us_rr;1:integrate_us_rr;2:pexec_us_rr;3:integrate_us_rr;4:pexec_us_rr

## 下一步
- 持续监控 cc2 流量 SR + fallback 触发率 (目标 SR99%+ fb<10%)
- k2 pexec 429×6 + RemoteDisconnected×4 — NVCF 配额+连接间歇, 若持续频发可考虑 k2 切 integrate
- k0/k1 IntegrateRemoteDisconnected 各 1× — 偶发, 关注是否蔓延
- openclaw glm5_2_nv NVStream_IncompleteRead ×4 — 非 cc2 管辖但关注是否蔓延
- 等 NVAnthCollect_IncompleteRead 是否再现 (R661 修复窗口 ~40h+ clean)

## 参数快照 (无变化, 沿用 R661)
- nv_gw: NVU_DISABLE_MS_FALLBACK=1, buffer 5×90s=450s, UPSTREAM_TIMEOUT=90, TIER_COOLDOWN_S=180
  - per-key FID bind: NV_GLM52_KEY_FID_BIND=0:0;2:1;4:2 (k0/k2/k4 pexec fid1/2/3)
  - per-key mode bind: NV_GLM52_KEY_MODE_BIND=0:pexec_us_rr;1:integrate_us_rr;2:pexec_us_rr;3:integrate_us_rr;4:pexec_us_rr
- cc4101: PRIMARY=glm5_2_nv→nv_gw:40006, FALLBACK=dsv4p_nv→dsv4p_nv40066:40066, STREAM_TOTAL=470, HEADER=400, UPSTREAM_IDLE=150
- deadline 链: 90s×5=450s buffer < 470s cc4101 < 600s API < 900s idle
