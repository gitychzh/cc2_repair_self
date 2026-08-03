# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: R693 (NOP 巡检, 2026-08-03 18:20 CST)
> 上轮: R692 (NOP, cc2 16req SR100% fallback6.25%)

## 本轮 (R693) 改了什么 + 依据 + 验证

### 改动: 不改码 (NOP)

### 依据 (30min 窗口实测, 轮前链路分析注入)
- **cc2 (cc4101→primary glm5_2_nv) 30min: 0 req** — cc4101-primary 专属段为空, 本轮 cc2 无流量
- 无流量 = 无新数据 = 不动手 (铁律 1: 改前必有数据)
- 链路总览 (所有 caller):
  - dsv4p_nv SR 97.9% (47/48) — 1 个 502 all_tiers_exhausted (hermes→dsv4p, 非 cc2 管辖)
  - glm5_2_nv 200×1 (other caller)
- nv_tier_attempts 错误: k0 NVCFPexecRemoteDisconnected×1, k2 429_nv_rate_limit×4 + pexec_conn_RemoteDisconnected×1, k3 integrate_success×1
- 30min fallback 发生率: f×49 (全部 hermes→dsv4p 路径, cc2 无 fallback)
- 无 BUFFER/WAIT/NV-ANTH-COLLECT 日志
- R661 post-restart ~40h+ 仍无 NVAnthCollect_IncompleteRead 再现

### 验证: NOP 无需 restart
- `curl /health`: nv_gw ok(5keys) + cc4101 ok + dsv4p_nv40066 ok(5keys)
- `docker ps`: nv_gw 2h, cc4101 3h, dsv4p_nv40066 3h, nv_gw_stable 40h, logs_db 4d — 全 Up
- 配置实测无漂移:
  - NVU_DISABLE_MS_FALLBACK=1, buffer 5×90s=450s, UPSTREAM_TIMEOUT=90, TIER_COOLDOWN_S=180
  - NV_GLM52_KEY_FID_BIND=0:0;2:1;4:2, NV_GLM52_KEY_MODE_BIND=0:pexec_us_rr;1:integrate_us_rr;2:pexec_us_rr;3:integrate_us_rr;4:pexec_us_rr

## 下一步
- 等 cc2 流量恢复 (R689-R692 曾连续有流量, 本轮中断)
- 持续监控 k2 pexec fid=3b9748d8 RemoteDisconnected + 429 是否频发 → 若持续可考虑 k2 切 integrate
- hermes dsv4p_nv all_tiers_exhausted 间歇 → 非 cc2 管辖, 关注 dsv4p_nv40066 fallback 路径可用性
- 等 NVAnthCollect_IncompleteRead 是否再现 (R661 修复窗口 ~40h+ 仍 clean)

## 参数快照 (无变化, 沿用 R661)
- nv_gw: NVU_DISABLE_MS_FALLBACK=1, buffer 5×90s=450s, UPSTREAM_TIMEOUT=90, TIER_COOLDOWN_S=180
  - per-key FID bind: NV_GLM52_KEY_FID_BIND=0:0;2:1;4:2 (k0/k2/k4 pexec fid1/2/3)
  - per-key mode bind: NV_GLM52_KEY_MODE_BIND=0:pexec_us_rr;1:integrate_us_rr;2:pexec_us_rr;3:integrate_us_rr;4:pexec_us_rr
- cc4101: PRIMARY=glm5_2_nv→nv_gw:40006, FALLBACK=dsv4p_nv→dsv4p_nv40066:40066, STREAM_TOTAL=470, HEADER=400, UPSTREAM_IDLE=150
- deadline 链: 90s×5=450s buffer < 470s cc4101 < 600s API < 900s idle
