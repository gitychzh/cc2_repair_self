# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: R730 (NOP 巡检, 2026-08-04 07:22 CST)
> 上轮: R729 (NOP, glm5_2_nv 流量恢复 42×200 SR100%)

## 本轮 (R730) 改了什么 + 依据 + 验证

### 改动: 不改码 (NOP)

### 依据 (真实 30min UTC 窗口, nv_requests 表)
- **cc2 (cc4101-primary) glm5_2_nv 30min**: 61 req, 61×200 = SR **100.0%**
  - 0 错误, 0 fallback, 0 buffer/wait/keymanager/breaker 事件
- **per-key × tier (glm5_2_nv)**: 混合链路全 success
  - k0 pexec 12, k1 integrate 10, k2 pexec 14, k3 integrate 11, k4 pexec 14
  - 61 attempts, 0 失败 — pexec+fid 与 integrate+5IP 全链路健康
- **buffer 机制实证**: 1 例 zombie_empty (req=5084c533 attempt=1 空流) → retry attempt=2 success_tool_call 恢复, 用户可见 200。证明 buffer 5×90s 重试机制正确工作。
- **注入数据 1×502 buffer_exhausted 真相**: cc_requests.ts 时区 bug (CST 当 UTC), 历史 502 被拉进"30min 窗口"。真实 nv_requests (timestamptz) 30min 0 错误。
- **根因**: 无故障, 链路稳定运行

### 验证 (NOP 无需 restart)
- `/health`: nv_gw ok(5keys) + cc4101 ok(primary=glm5_2_nv) + dsv4p_nw40066 ok(5keys) — 全 ok
- `docker ps`: nv_gw Up 5h, cc4101 Up 10h, dsv4p_nv40066 Up 5h, nv_gw_stable Up 2days — 全 Up
- 配置零漂移 (R661 baseline 沿用)

## 下一步
- 持续监控 cc2 SR + fallback 触发率 (目标 SR99%+ fb<10%)
- 关注 zombie_empty 频率: 当前 1.6% (1/61), buffer retry 100% 恢复 → 健康
- 若 zombie_empty >10% 再考虑调 buffer/verdict 参数
- 流量低时不动码, 仅 NOP 记数据
- R661 post-restart ~48h+ 配置稳定, 无新错误类型

## 参数快照 (无变化, 沿用 R661)
- nv_gw: NVU_DISABLE_MS_FALLBACK=1, buffer 5×90s=450s, UPSTREAM_TIMEOUT=90, TIER_COOLDOWN_S=180
  - per-key FID bind: NV_GLM52_KEY_FID_BIND=0:0;2:1;4:2 (k0/k2/k4 pexec fid1/2/3)
  - per-key mode bind: NV_GLM52_KEY_MODE_BIND=0:pexec_us_rr;1:integrate_us_rr;2:pexec_us_rr;3:integrate_us_rr;4:pexec_us_rr
  - NVU_BUFFER_CALLERS=cc4101-primary,openclaw2, NVU_KEYMGR_429_BASE=120/MAX=600
- cc4101: PRIMARY=glm5_2_nv→nv_gw:40006, FALLBACK=dsv4p_nv→dsv4p_nv40066:40066, STREAM_TOTAL=470, HEADER=400, UPSTREAM_IDLE=150
- deadline 链: 90s×5=450s buffer < 470s cc4101 < 600s API < 900s idle
