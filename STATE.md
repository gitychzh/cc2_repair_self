# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: R729 (NOP 巡检, 2026-08-04 05:25 CST)
> 上轮: R728 (NOP, cc2 零流量 dsv4p_nv 100%)

## 本轮 (R729) 改了什么 + 依据 + 验证

### 改动: 不改码 (NOP)

### 依据 (30min 窗口)
- **cc2 (cc4101-primary) glm5_2_nv 30min**: 42 req, 42×200 = SR **100.0%**
  - 0 fallback, 0 错误, 0 buffer/wait 触发
- **per-key × tier (glm5_2_nv)**: 混合链路全 success
  - k0 pexec 6, k1 integrate 12, k2 pexec 8, k3 integrate 10, k4 pexec 6
  - 42 attempts, 0 失败, 0 error_type — pexec+fid 与 integrate+5IP 全链路健康
- **错误分类 30min**: 0 错误 (无新错误类型)
- **对比前轮**: R727/R728 glm5_2_nv 零流量; R729 流量恢复且 100% SR — 真实流量下混合链路健康验证
- **根因**: 无故障, 链路稳定运行

### 验证 (NOP 无需 restart)
- `/health`: nv_gw ok(5keys) + cc4101 ok(primary=glm5_2_nv) + dsv4p_nv40066 ok(5keys) — 全 ok
- `docker ps`: nv_gw Up 3h, cc4101 Up 8h, dsv4p_nv40066 Up 3h, nv_gw_stable Up 2days — 全 Up
- 配置零漂移 (R661 baseline 沿用)

## 下一步
- 持续监控 cc2 SR + fallback 触发率 (目标 SR99%+ fb<10%)
- glm5_2_nv 流量持续时关注 k2 pexec conn_RD 是否复发 (R728 历史根因)
- 流量低时不动码, 仅 NOP 记数据
- R661 post-restart ~46h+ 配置稳定, 无新错误类型

## 参数快照 (无变化, 沿用 R661)
- nv_gw: NVU_DISABLE_MS_FALLBACK=1, buffer 5×90s=450s, UPSTREAM_TIMEOUT=90, TIER_COOLDOWN_S=180
  - per-key FID bind: NV_GLM52_KEY_FID_BIND=0:0;2:1;4:2 (k0/k2/k4 pexec fid1/2/3)
  - per-key mode bind: NV_GLM52_KEY_MODE_BIND=0:pexec_us_rr;1:integrate_us_rr;2:pexec_us_rr;3:integrate_us_rr;4:pexec_us_rr
- cc4101: PRIMARY=glm5_2_nv→nv_gw:40006, FALLBACK=dsv4p_nv→dsv4p_nv40066:40066, STREAM_TOTAL=470, HEADER=400, UPSTREAM_IDLE=150
- deadline 链: 90s×5=450s buffer < 470s cc4101 < 600s API < 900s idle
