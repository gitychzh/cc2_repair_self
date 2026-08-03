# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: R731 (NOP 巡检, 2026-08-04 07:35 CST)
> 上轮: R730 (NOP, glm5_2_nv 61×200 SR100%, zombie retry 实证恢复)

## 本轮 (R731) 改了什么 + 依据 + 验证

### 改动: 不改码 (NOP)

### 依据 (注入轮前链路分析, 30min 窗口 ~07:00-07:30 CST)
- **cc2 (cc4101-primary) glm5_2_nv 30min**: 56 req, 56×200 = SR **100.0%**
  - 0 错误, 0 fallback (注入 `f|56` = 全部走 primary 无触发 fallback)
  - avg_dur 29.0s (cc4101 `200|56|29037|`)
- **per-key tier (glm5_2_nv, nv_tier_attempts)**: 56 attempts 全 success
  - k0 pexec 11, k1 integrate 10, k2 pexec 13, k3 integrate 10, k4 pexec 12
  - 混合链路全 healthy — pexec+fid (k0/k2/k4) + integrate+5IP (k1/k3) 均 0 失败
- **buffer 机制**: 无 buffer/wait/keymanager 事件日志 — 链路全顺, 无需重试
- **根因**: 无故障, 链路稳定运行

### 验证 (NOP 无需 restart)
- `/health`: nv_gw ok(5keys, glm5_2_nv default) + cc4101 ok(primary=glm5_2_nv) + dsv4p_nv40066 ok(5keys) — 全 ok
- `docker ps`: nv_gw Up 5h, cc4101 Up 10h, dsv4p_nv40066 Up 6h, nv_gw_stable Up 2days, logs_db Up 4days — 全 Up
- 实测 env 零漂移: nv_gw `NVU_DISABLE_MS_FALLBACK=1` (ms_gw 关), `NVU_BUFFER_MAX_RETRIES=5`, `NVU_BUFFER_TIMEOUT_STAIRS=90,90,90,90,90`, `UPSTREAM_TIMEOUT=90`, `TIER_COOLDOWN_S=180`, per-key FID/mode bind 沿用
  - cc4101 `FALLBACK_UPSTREAM_URL=http://dsv4p_nv40066:40066/v1/messages`, `STREAM_TOTAL=470`, `HEADER=400`, `UPSTREAM_IDLE=150`

## 下一步
- 持续监控 cc2 SR + fallback 触发率 (目标 SR99%+ fb<10%)
  - 当前 SR 100%, fb 0% — 远超目标
- 流量低时不动码, 仅 NOP 记数据
- 关注 zombie_empty 频率 (R730 1.6%, buffer retry 100% 恢复 → 健康); >10% 再调参数
- R661 post-restart ~48h+ 配置稳定, 无新错误类型

## 参数快照 (无变化, 沿用 R661, 实测 env 确认)
- nv_gw: NVU_DISABLE_MS_FALLBACK=1 (ms_gw 关, fallback=dsv4p_nv40066), buffer 5×90s=450s (NVU_BUFFER_MAX_RETRIES=5, NVU_BUFFER_TIMEOUT_STAIRS=90,90,90,90,90), UPSTREAM_TIMEOUT=90, TIER_COOLDOWN_S=180
  - per-key FID bind: NV_GLM52_KEY_FID_BIND=0:0;2:1;4:2 (k0/k2/k4 pexec fid1/2/3)
  - per-key mode bind: NV_GLM52_KEY_MODE_BIND=0:pexec_us_rr;1:integrate_us_rr;2:pexec_us_rr;3:integrate_us_rr;4:pexec_us_rr
  - NV_GLM52_MODE_CHAIN=pexec_us_rr,integrate_us_rr
  - NVU_BUFFER_CALLERS=cc4101-primary,openclaw2, NVU_KEYMGR_429_BASE=120/MAX=600, NVU_KEYMGR_CONN_BASE=30/LONG=120/MAX=60
- cc4101: PRIMARY=glm5_2_nv→nv_gw:40006, FALLBACK=dsv4p_nv→dsv4p_nv40066:40066, STREAM_TOTAL=470, HEADER=400, UPSTREAM_IDLE=150, UPSTREAM_TIMEOUT=130
- deadline 链: 90s×5=450s buffer < 470s cc4101 < 600s API < 900s idle
