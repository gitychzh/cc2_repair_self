# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: R709 (NOP 巡检, 2026-08-03 19:15 CST)
> 上轮: R708 (NOP, cc2 60min零流量)

## 本轮 (R709) 改了什么 + 依据 + 验证

### 改动: 不改码 (NOP)

### 依据 (30min 窗口实测 ~15:00-15:30 UTC = 18:45-19:15 CST)
- **cc2 (cc4101) 真实 SR**: 16req 全 200, SR **100%** ✅ (primary 15 + fallback 1)
- **fallback 触发率**: 6.3% (1/16) < 10% 目标 ✅
- **延迟**: max_dur=101s, avg=42s, 无 stream_total_deadline 超时 (6h 0行)
- **nv_gw 全量 30min** (非全 cc2 管辖):
  - hermes: 29/38=76.3% (dsv4p 29/31 + glm5_2 1/8)
  - openclaw: 17/17=100% (全 dsv4p)
- **glm5_2_nv tier 不稳**: hermes 1/8 (SR 12.5%), 全 RemoteDisconnected/429 NVCF 上游间歇
- **错误分类**: NVStream_IncompleteRead×4, all_tiers_exhausted×4, stream_absolute_cap×1
- **tier attempts**: NVCFPexecRemoteDisconnected×5, IntegrateRemoteDisconnected×4, pexec_conn_RemoteDisconnected×4, 429×1
- **KeyMgr**: penalty=5s no conn_count 快速恢复生效 (k3 多次)
- **STREAMBREAK**: 3× IncompleteRead content_flushed=0~444c NVCF 上游断连
- **根因**: glm5_2_nv tier 502 全是 NVCF 上游 RemoteDisconnected/429 配额副作用, 非 nv_gw 可控; cc4101 fallback 到 dsv4p 兜底, 用户可见 SR 100%

### 验证: NOP 无需 restart
- `curl /health`: nv_gw ok(5keys) + cc4101 ok + dsv4p_nv40066 ok(5keys)
- `docker ps`: nv_gw Up 3h, cc4101 Up 4h, dsv4p_nv40066 Up 4h, nv_gw_stable Up 41h, logs_db Up 4d — 全 Up
- 配置实测无漂移 (R661 baseline):
  - NVU_DISABLE_MS_FALLBACK=1, buffer 5×90s=450s, UPSTREAM_TIMEOUT=90, TIER_COOLDOWN_S=180
  - NV_GLM52_KEY_FID_BIND=0:0;2:1;4:2, NV_GLM52_KEY_MODE_BIND=0:pexec_us_rr;1:integrate_us_rr;2:pexec_us_rr;3:integrate_us_rr;4:pexec_us_rr
  - cc4101: PRIMARY=glm5_2_nv→nv_gw:40006, FALLBACK=dsv4p_nv→dsv4p_nv40066:40066, STREAM_TOTAL=470, HEADER=400, UPSTREAM_IDLE=150

## 下一步
- 持续监控 cc2 流量 SR + fallback 触发率 (目标 SR99%+ fb<10%)
- glm5_2_nv tier RemoteDisconnected/429 是 NVCF 上游间歇+配额副作用, 非 nv_gw 可控
- cc4101 fallback 到 dsv4p 兜底, 用户可见 SR 100% 已达目标
- R661 post-restart ~41h+ 仍无 NVAnthCollect_IncompleteRead 再现
- 关注 fallback 率若持续上升 >10% 再深入查 glm5_2_nv tier

## 参数快照 (无变化, 沿用 R661)
- nv_gw: NVU_DISABLE_MS_FALLBACK=1, buffer 5×90s=450s, UPSTREAM_TIMEOUT=90, TIER_COOLDOWN_S=180
  - per-key FID bind: NV_GLM52_KEY_FID_BIND=0:0;2:1;4:2 (k0/k2/k4 pexec fid1/2/3)
  - per-key mode bind: NV_GLM52_KEY_MODE_BIND=0:pexec_us_rr;1:integrate_us_rr;2:pexec_us_rr;3:integrate_us_rr;4:pexec_us_rr
- cc4101: PRIMARY=glm5_2_nv→nv_gw:40006, FALLBACK=dsv4p_nv→dsv4p_nv40066:40066, STREAM_TOTAL=470, HEADER=400, UPSTREAM_IDLE=150
- deadline 链: 90s×5=450s buffer < 470s cc4101 < 600s API < 900s idle
