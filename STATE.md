# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: R733 (NOP 巡检, 2026-08-04 09:04 CST)
> 上轮: R732 (NOP, glm5_2_nv 58×200 nv_gw SR100%, cc4101 60×200+2×499 client_gone)

## 本轮 (R733) 改了什么 + 依据 + 验证

### 改动: 不改码 (NOP)

### 依据 (实测 30min 窗口 ~08:34-09:04 CST, created_at 字段)
- **nv_gw 层 (cc4101-primary)**: 32 req, 32×200 = SR **100.0%**, 0 错误
- **per-key tier (glm5_2_nv, nv_tier_attempts)**: 32 attempts 全 success
  - pexec_success 19 (k0/k2/k4) + integrate_success 13 (k1/k3) — 混合链路全 healthy
- **cc4101 层 (cc_requests, created_at 30min)**: 33 req, 32×200 + 1×499 client_gone_mid_stream = SR 97.0%
  - 1×499 = cc2 SDK 主动断连, 非 nv_gw 故障
- **fallback 触发率**: 0% (0/33) — 远超 < 10% 目标
- **buffer 日志**: 全 NV-BUFFER-SUCCESS, 多数 1 attempt 成功; 1 个 attempt=4 仍 success (buffer retry 吸收抖动, elapsed 167s)
  - 无 WAIT/KEYMGR/breaker/cooling 事件

### 验证 (NOP 无需 restart)
- `/health`: nv_gw ok(5keys, glm5_2_nv default) + cc4101 ok(primary=glm5_2_nv) + dsv4p_nv40066 ok(5keys) — 全 ok
- `docker ps`: nv_gw Up 7h, cc4101 Up 11h, dsv4p_nv40066 Up 7h, nv_gw_stable Up 2days, logs_db Up 4days — 全 Up
- env 零漂移 (沿 R-glm52split 架构)
  - nv_gw: NVU_DISABLE_MS_FALLBACK=1, buffer 5×90s=450s, UPSTREAM_TIMEOUT=90, TIER_COOLDOWN_S=180
  - cc4101: FALLBACK=dsv4p_nv40066:40066, STREAM_TOTAL=470, HEADER=400, UPSTREAM_IDLE=150

### 注入轮前分析 vs 实测一致性
- 注入: `glm5_2_nv SR=100.0% (28/28)`, per-key 8+5+7+7+1=28, `f|28`
- 实测 (晚 ~90s): 32×200, pexec 19 + integrate 13, 0 fb — 一致

## 下一步
- 持续监控 cc2 SR + fallback 触发率 (目标 SR99%+ fb<10%)
  - 当前 nv_gw SR 100%, cc4101 SR 97.0% (1 client_gone 非 nv_gw), fb 0% — 远超目标
- 流量低时不动码, 仅 NOP 记数据
- cc_requests.ts 时区 bug 沿用: 分析用 created_at (R730/R732 已实证)
- R661 post-restart ~48h+ 配置稳定, 无新错误类型

## 参数快照 (无变化, 沿用 R-glm52split, 实测 env 确认)
- nv_gw: NVU_DISABLE_MS_FALLBACK=1 (ms_gw 关, fallback=dsv4p_nv40066), buffer 5×90s=450s (NVU_BUFFER_MAX_RETRIES=5, NVU_BUFFER_TIMEOUT_STAIRS=90,90,90,90,90), UPSTREAM_TIMEOUT=90, TIER_COOLDOWN_S=180
  - per-key FID bind: NV_GLM52_KEY_FID_BIND=0:0;2:1;4:2 (k0/k2/k4 pexec fid1/2/3)
  - per-key mode bind: NV_GLM52_KEY_MODE_BIND=0:pexec_us_rr;1:integrate_us_rr;2:pexec_us_rr;3:integrate_us_rr;4:pexec_us_rr
  - NV_GLM52_MODE_CHAIN=pexec_us_rr,integrate_us_rr
  - NVU_BUFFER_CALLERS=cc4101-primary,openclaw2, NVU_KEYMGR_429_BASE=120/MAX=600, NVU_KEYMGR_CONN_BASE=30/LONG=120/MAX=60
- cc4101: PRIMARY=glm5_2_nv→nv_gw:40006, FALLBACK=dsv4p_nv→dsv4p_nv40066:40066, STREAM_TOTAL=470, HEADER=400, UPSTREAM_IDLE=150, UPSTREAM_TIMEOUT=130
- deadline 链: 90s×5=450s buffer < 470s cc4101 < 600s API < 900s idle
