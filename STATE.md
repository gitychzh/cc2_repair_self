# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: R710 (NOP 巡检, 2026-08-03 19:16 CST)
> 上轮: R709 (NOP, cc2 16req全200 SR100%)

## 本轮 (R710) 改了什么 + 依据 + 验证

### 改动: 不改码 (NOP)

### 依据 (30min 窗口实测 ~10:50-11:16 UTC = 18:50-19:16 CST)
- **cc2 (cc4101) 真实 SR**: 16req 全 200, SR **100%** ✅ (primary 15 + fallback 1)
- **fallback 触发率**: 6.25% (1/16) < 10% 目标 ✅
- **nv_gw 全量 30min** (非全 cc2 管辖):
  - dsv4p_nv: 50/52=96.2% (hermes 33+2×502, openclaw 17)
  - glm5_2_nv: 0/6=0% (全 hermes, NVCF 上游间歇)
- **错误分类**: NVStream_IncompleteRead×3, all_tiers_exhausted×3, stream_absolute_cap×1
- **tier attempts (glm5_2_nv)**: k1 integrate×1, k2 pexec(3b9748d8)×3+integrate×2, k3 integrate×1 — 全 0 ok
  - 错误: NVCFPexecRemoteDisconnected, IntegrateRemoteDisconnected, pexec_conn_RemoteDisconnected, 429
- **dsv4p per-key**: k0 11×200, k1 9×200, k2 11×200, k3 7×200, k4 12×200+1×502 — 均衡
- **dsv4p per-IP**: 5 IP 均匀分布 (7~13 req), 全 100%
- **根因**: glm5_2_nv tier 6/6 全 502 是 NVCF 上游 RemoteDisconnected/429 配额副作用, 非 nv_gw 可控; cc4101 fallback 到 dsv4p 兜底, cc2 用户可见 SR 100%

### 验证: NOP 无需 restart
- `curl /health`: nv_gw ok(5keys) + cc4101 ok + dsv4p_nv40066 ok(5keys)
- `docker ps`: nv_gw Up 3h, cc4101 Up 4h, dsv4p_nv40066 Up 4h, nv_gw_stable Up 41h, logs_db Up 4d — 全 Up
- 配置无漂移 (R661 baseline):
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
