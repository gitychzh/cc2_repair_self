# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: R692 (NOP 巡检, 2026-08-03 18:15 CST)
> 上轮: R691 (NOP, cc2 无流量 0req, 全量 dsv4p_nv SR98%)

## 本轮 (R692) 改了什么 + 依据 + 验证

### 改动: 不改码 (NOP)

### 依据 (30min 窗口实测, DB 抽查确认)
- **cc2 (cc4101→primary glm5_2_nv) 30min: 16 req 全 200, SR 100%, fallback 1/16=6.25%** (< 10% 目标 ✓)
- 连续第 3 轮有 cc2 真实流量 (R689-R691), 链路稳定
- nv_requests 30min: 200×47 + 502×1 (SR 97.9%) — 502 是 hermes→dsv4p_nv all_tiers_exhausted, 非 cc2 管辖
- glm5_2_nv 混合链路 tier attempts:
  - k2 pexec fid=3b9748d8 RemoteDisconnected (1次) → buffer 内恢复 (k3 integrate success)
  - k3 integrate success
- KeyManager: k3 RemoteDisconnected penalty=5s (no conn_count) — 快速恢复设计生效
- 无 BUFFER/WAIT/NV-ANTH-COLLECT 日志
- R661 post-restart ~40h+ 仍无 NVAnthCollect_IncompleteRead 再现
- 配置无漂移: NVU_DISABLE_MS_FALLBACK=1, buffer 5×90s, UPSTREAM_TIMEOUT=90, TIER_COOLDOWN_S=180

### 验证: NOP 无需 restart
- `curl /health` nv_gw(ok 5keys) + cc4101(ok) + dsv4p_nv40066(ok 5keys)
- `docker ps` 容器都 Up: nv_gw 2h, cc4101 3h, dsv4p_nv40066 3h, nv_gw_stable 40h
- 配置实测一致

## 下一步
- cc2 流量持续 (R689-R691 连续 3 轮有流量) — 继续监控混合链路 k2/k3/k4 fid 路由稳定性
- 关注 k2 pexec fid=3b9748d8 RemoteDisconnected 是否频发 → 若持续可考虑 k2 切 integrate
- hermes dsv4p_nv all_tiers_exhausted 间歇 → 非 cc2 管辖, 关注 fallback 路径(dsv4p_nv40066)可用性
- 等 NVAnthCollect_IncompleteRead 是否再现 (R661 修复窗口 ~40h+ 仍 clean)

## 参数快照 (无变化, 沿用 R661)
- nv_gw: NVU_DISABLE_MS_FALLBACK=1, buffer 5×90s=450s, UPSTREAM_TIMEOUT=90, TIER_COOLDOWN_S=180
  - per-key FID bind: NV_GLM52_KEY_FID_BIND=0:0;2:1;4:2 (k0/k2/k4 pexec fid1/2/3)
  - per-key mode bind: NV_GLM52_KEY_MODE_BIND=0:pexec_us_rr;1:integrate_us_rr;2:pexec_us_rr;3:integrate_us_rr;4:pexec_us_rr
- cc4101: PRIMARY=glm5_2_nv→nv_gw:40006, FALLBACK=dsv4p_nv→dsv4p_nv40066:40066, STREAM_TOTAL=470, HEADER=400, UPSTREAM_IDLE=150
- deadline 链: 90s×5=450s buffer < 470s cc4101 < 600s API < 900s idle
