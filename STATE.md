# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: R694 (NOP 巡检, 2026-08-03 18:25 CST)
> 上轮: R693 (NOP, cc2 零流量)

## 本轮 (R694) 改了什么 + 依据 + 验证

### 改动: 不改码 (NOP)

### 依据 (30min 窗口实测)
- **cc2 (cc_requests)**: 16req 全 200, **SR 100%**, fallback 1/16 = **6.25%** (< 10% 目标 ✅)
- cc4101-primary nv_requests 专属段为空 (cc2 流量经 cc4101 primary 但 cc_requests 已记 16 全 200)
- 链路总览: hermes dsv4p_nv 200×52+502×1(all_tiers_exhausted), openclaw dsv4p_nv 200×10+502×1+glm5_2_nv 200×1+502×2(NVStream_IncompleteRead), other 2×200
- 错误分类: NVStream_IncompleteRead×3 (openclaw glm5_2_nv 非 cc2), all_tiers_exhausted×1 (hermes→dsv4p 非 cc2)
- tier attempts 错误: 429_nv_rate_limit×5(k2), IntegrateRemoteDisconnected×2(k4), NVCFPexecRemoteDisconnected×1(k0), pexec_conn_RemoteDisconnected×1(k2), integrate_conn_RemoteDisconnected×1(k4), integrate_success×3(k3)
- KeyManager: k3/k4 RemoteDisconnected penalty=5s no conn_count ×3 — 快速恢复生效
- 无 BUFFER-/WAIT- 日志
- R661 post-restart ~40h+ 无 NVAnthCollect_IncompleteRead 再现

### 验证: NOP 无需 restart
- `curl /health`: nv_gw ok(5keys) + cc4101 ok + dsv4p_nv40066 ok(5keys)
- `docker ps`: nv_gw Up 2h, cc4101 Up 3h, dsv4p_nv40066 Up 3h, nv_gw_stable Up 40h, opclaw4103/hm4104 Up 24min — 全 Up
- 配置实测无漂移:
  - NVU_DISABLE_MS_FALLBACK=1, buffer 5×90s=450s, UPSTREAM_TIMEOUT=90, TIER_COOLDOWN_S=180
  - NV_GLM52_KEY_FID_BIND=0:0;2:1;4:2, NV_GLM52_KEY_MODE_BIND=0:pexec_us_rr;1:integrate_us_rr;2:pexec_us_rr;3:integrate_us_rr;4:pexec_us_rr

## 下一步
- 持续监控 cc2 流量 SR + fallback 触发率 (目标 SR99%+ fb<10%)
- k2 pexec 429×5 + RemoteDisconnected 偶发 — 若持续频发可考虑 k2 切 integrate
- k4 integrate IntegrateRemoteDisconnected ×2 — integrate 路径间歇不稳, 同上评估
- openclaw glm5_2_nv NVStream_IncompleteRead ×2 — 非 cc2 管辖但关注是否蔓延
- 等 NVAnthCollect_IncompleteRead 是否再现 (R661 修复窗口 ~40h+ clean)

## 参数快照 (无变化, 沿用 R661)
- nv_gw: NVU_DISABLE_MS_FALLBACK=1, buffer 5×90s=450s, UPSTREAM_TIMEOUT=90, TIER_COOLDOWN_S=180
  - per-key FID bind: NV_GLM52_KEY_FID_BIND=0:0;2:1;4:2 (k0/k2/k4 pexec fid1/2/3)
  - per-key mode bind: NV_GLM52_KEY_MODE_BIND=0:pexec_us_rr;1:integrate_us_rr;2:pexec_us_rr;3:integrate_us_rr;4:pexec_us_rr
- cc4101: PRIMARY=glm5_2_nv→nv_gw:40006, FALLBACK=dsv4p_nv→dsv4p_nv40066:40066, STREAM_TOTAL=470, HEADER=400, UPSTREAM_IDLE=150
- deadline 链: 90s×5=450s buffer < 470s cc4101 < 600s API < 900s idle
