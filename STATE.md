# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: R711 (NOP 巡检, 2026-08-03 19:21 CST)
> 上轮: R710 (NOP, cc2 16req全200 SR100% fb6.3%)

## 本轮 (R711) 改了什么 + 依据 + 验证

### 改动: 不改码 (NOP)

### 依据 (30min 窗口 ~18:50-19:20 CST)
- **cc2 (cc4101) 真实 SR**: 16req 全 200, SR **100%** ✅ (15 primary 直通 + 1 fallback)
- **fallback 触发率**: 6.3% (1/16) < 10% 目标 ✅
- **nv_gw nv_requests 30min** (只记录非直通/error 路径, passthrough 200 不入表):
  - dsv4p_nv: 54×200 + 3×502 = 96.5% (54/57)
  - glm5_2_nv: 5×502 = 0% — 全是非 cc2 流量 (agent_type=`_nv`), NVCF 上游间歇退化
- **glm5_2_nv 3h 退化趋势**: 10:20 起 NVCF 上游开始退化 (56%→40%→33%→0%), 11:00 后完全不可用
- **glm5_2_nv tier errors**: NVCFPexecRemoteDisconnected×5, IntegrateRemoteDisconnected×4, pexec_conn_RemoteDisconnected×3, 429×1 — 全 NVCF 上游 RemoteDisconnected/配额副作用, 非 nv_gw 可控
- **dsv4p per-key**: k0 11×200, k1 11×200, k2 12×200, k3 8×200, k4 12×200+1×502 — 均衡健康
- **dsv4p per-IP**: 5 US IPv4 均匀 (8~13 req), 全 100%
- **根因**: glm5_2_nv NVCF 上游间歇退化 (10:20 起), cc4101 fallback → dsv4p 兜底, cc2 用户 SR 100%

### 验证: NOP 无需 restart
- `curl /health`: nv_gw ok(5keys) + cc4101 ok + dsv4p_nv40066 ok(5keys)
- `docker ps`: nv_gw Up 3h, cc4101 Up 4h, dsv4p_nv40066 Up 4h, nv_gw_stable Up 41h, logs_db Up 4d — 全 Up
- 配置零漂移 (R661 baseline):
  - nv_gw: NVU_DISABLE_MS_FALLBACK=1, buffer 5×90s=450s, UPSTREAM_TIMEOUT=90, TIER_COOLDOWN_S=180
  - NV_GLM52_KEY_FID_BIND=0:0;2:1;4:2, NV_GLM52_KEY_MODE_BIND=0:pexec_us_rr;1:integrate_us_rr;2:pexec_us_rr;3:integrate_us_rr;4:pexec_us_rr
  - cc4101: PRIMARY=glm5_2_nv→nv_gw:40006, FALLBACK=dsv4p_nv→dsv4p_nv40066:40066, STREAM_TOTAL=470, HEADER=400, UPSTREAM_IDLE=150, PRIMARY_SKIP_S=30, FAIL_THRESHOLD=3
  - dsv4p_nv40066: pexec-only, NV_INTEGRATE_MODELS=空, NVU_DISABLE_MS_FALLBACK=1, PEER_FALLBACK=0

## 下一步
- 持续监控 cc2 SR + fallback 触发率 (目标 SR99%+ fb<10%)
- glm5_2_nv NVCF 上游退化中 (10:20 起), 依赖 dsv4p 兜底, 非 nv_gw 可控
- 若 fallback 率持续上升 >10% 再深入查 glm5_2_nv tier
- R661 post-restart ~41h+ 仍无新错误类型, 配置稳定

## 参数快照 (无变化, 沿用 R661)
- nv_gw: NVU_DISABLE_MS_FALLBACK=1, buffer 5×90s=450s, UPSTREAM_TIMEOUT=90, TIER_COOLDOWN_S=180
  - per-key FID bind: NV_GLM52_KEY_FID_BIND=0:0;2:1;4:2 (k0/k2/k4 pexec fid1/2/3)
  - per-key mode bind: NV_GLM52_KEY_MODE_BIND=0:pexec_us_rr;1:integrate_us_rr;2:pexec_us_rr;3:integrate_us_rr;4:pexec_us_rr
- cc4101: PRIMARY=glm5_2_nv→nv_gw:40006, FALLBACK=dsv4p_nv→dsv4p_nv40066:40066, STREAM_TOTAL=470, HEADER=400, UPSTREAM_IDLE=150
- deadline 链: 90s×5=450s buffer < 470s cc4101 < 600s API < 900s idle
