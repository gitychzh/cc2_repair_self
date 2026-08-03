# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: R706 (NOP 巡检, 2026-08-03 19:00 CST)
> 上轮: R696 (NOP, cc2 16req SR100% fb6.25%)

## 本轮 (R706) 改了什么 + 依据 + 验证

### 改动: 不改码 (NOP)

### 依据 (30min 窗口实测 ~10:20-10:50 UTC = 18:20-18:50 CST)
- **cc2 (cc_requests)**: 16req 全 200, **SR 100%**, fallback 1/16 = **6.25%** (< 10% 目标 ✅)
- nv_gw 全量错误: NVStream_IncompleteRead ×6 + all_tiers_exhausted ×4 + stream_absolute_cap ×1
  - **全部非 cc2 管辖** (hermes/openclaw 流量), cc2 走 buffer rotation 无 IncompleteRead
- tier attempts (glm5_2_nv, 23 attempts 全非 cc2):
  - k0/k1/k4: IntegrateRemoteDisconnected 各 2-3×
  - k2 (pexec fid3b9748d8): pexec_conn_RemoteDisconnected ×9 + pexec_success ×3 — NVCF 上游间歇断连
  - k3 (integrate): integrate_success ×2 + integrate_conn_RemoteDisconnected ×1 — 正常波动
- 无 BUFFER-/WAIT- 日志
- R661 post-restart ~41h+ 无 NVAnthCollect_IncompleteRead 再现

### 验证: NOP 无需 restart
- `curl /health`: nv_gw ok(5keys) + cc4101 ok + dsv4p_nv40066 ok(5keys)
- `docker ps`: nv_gw Up 3h, cc4101 Up 4h, dsv4p_nv40066 Up 4h, nv_gw_stable Up 41h — 全 Up
- 配置实测无漂移:
  - NVU_DISABLE_MS_FALLBACK=1, buffer 5×90s=450s, UPSTREAM_TIMEOUT=90, TIER_COOLDOWN_S=180
  - NV_GLM52_KEY_FID_BIND=0:0;2:1;4:2, NV_GLM52_KEY_MODE_BIND=0:pexec_us_rr;1:integrate_us_rr;2:pexec_us_rr;3:integrate_us_rr;4:pexec_us_rr

## 下一步
- 持续监控 cc2 流量 SR + fallback 触发率 (目标 SR99%+ fb<10%)
- glm5_2_nv tier RemoteDisconnected 是 NVCF 上游间歇断连, 非 nv_gw 可控
- 关注 NVStream_IncompleteRead 是否蔓延到 cc4101-primary (目前 cc2 全 200, 未蔓延)
- R661 post-restart ~41h+ 仍无 NVAnthCollect_IncompleteRead 再现

## 参数快照 (无变化, 沿用 R661)
- nv_gw: NVU_DISABLE_MS_FALLBACK=1, buffer 5×90s=450s, UPSTREAM_TIMEOUT=90, TIER_COOLDOWN_S=180
  - per-key FID bind: NV_GLM52_KEY_FID_BIND=0:0;2:1;4:2 (k0/k2/k4 pexec fid1/2/3)
  - per-key mode bind: NV_GLM52_KEY_MODE_BIND=0:pexec_us_rr;1:integrate_us_rr;2:pexec_us_rr;3:integrate_us_rr;4:pexec_us_rr
- cc4101: PRIMARY=glm5_2_nv→nv_gw:40006, FALLBACK=dsv4p_nv→dsv4p_nv40066:40066, STREAM_TOTAL=470, HEADER=400, UPSTREAM_IDLE=150
- deadline 链: 90s×5=450s buffer < 470s cc4101 < 600s API < 900s idle
