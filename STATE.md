# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: R726 (NOP 巡检, 2026-08-03 20:45 CST)
> 上轮: R725 (NOP, cc2 流量恢复 16req SR100% fb6.3%)

## 本轮 (R726) 改了什么 + 依据 + 验证

### 改动: 不改码 (NOP)

### 依据 (30min + 6h 交叉验证)
- **cc2 (cc4101) 30min**: 16 req, 16×200 = 可见 SR **100.0%**
  - fallback 触发率 1/16 = **6.3%** (目标 <10%, 达标)
- **nv_gw 全量 30min**: dsv4p_nv 62×200 = SR **100.0%**, glm5_2_nv 0 req
- **错误分类 30min**: 0 错误 (无新错误类型)
- **tier attempts 30min**: 0 行 (glm5_2_nv 无 tier 流量)
- **buffer/wait 日志**: 0 行 (无触发)
- **6h SR (更大小本)**:
  - glm5_2_nv: 29×200/19×502 = SR **60.4%** (48 req 低流量)
    - tier: pexec_conn_RD×19, pexec_success×17, IntegrateRD×15, integrate_conn_RD×7, SSLEOF×4, pexec_500×1
    - 全 NVCF 上游连接断开/配额副作用, 非 nv_gw 可控
  - dsv4p_nv: 405×200/18×429/17×502 = SR **92.0%** (440 req 高流量, 主力稳定)
- **根因**: glm5_2_nv 6h SR 60.4% 低流量下 NVCF 上游连接断开, 但 cc4101 fallback dsv4p 兜底 → 用户可见 SR 100%, fb 6.3% 达标

### 验证: NOP 无需 restart
- `/health`: nv_gw ok(5keys) + cc4101 ok(primary=glm5_2_nv) + dsv4p_nv40066 ok(5keys) — 全 ok
- `docker ps`: nv_gw Up 5h, cc4101 Up 5h, dsv4p_nv40066 Up 5h, nv_gw_stable Up 43h — 全 Up
- 配置零漂移 (R661 baseline 沿用)

## 下一步
- 持续监控 cc2 SR + fallback 触发率 (目标 SR99%+ fb<10%)
- glm5_2_nv 6h SR 60.4% 低流量, k2 pexec conn_RD 持续重灾 — 若流量恢复后 fb>10% 再深入查
- R661 post-restart ~43h+ 配置稳定, 无新错误类型

## 参数快照 (无变化, 沿用 R661)
- nv_gw: NVU_DISABLE_MS_FALLBACK=1, buffer 5×90s=450s, UPSTREAM_TIMEOUT=90, TIER_COOLDOWN_S=180
  - per-key FID bind: NV_GLM52_KEY_FID_BIND=0:0;2:1;4:2 (k0/k2/k4 pexec fid1/2/3)
  - per-key mode bind: NV_GLM52_KEY_MODE_BIND=0:pexec_us_rr;1:integrate_us_rr;2:pexec_us_rr;3:integrate_us_rr;4:pexec_us_rr
- cc4101: PRIMARY=glm5_2_nv→nv_gw:40006, FALLBACK=dsv4p_nv→dsv4p_nv40066:40066, STREAM_TOTAL=470, HEADER=400, UPSTREAM_IDLE=150
- deadline 链: 90s×5=450s buffer < 470s cc4101 < 600s API < 900s idle
