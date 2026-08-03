# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: R725 (NOP 巡检, 2026-08-03 20:35 CST)
> 上轮: R724 (NOP, cc2 零流量 dsv4p 100%)

## 本轮 (R725) 改了什么 + 依据 + 验证

### 改动: 不改码 (NOP)

### 依据 (30min + 2h/6h 交叉验证)
- **cc2 (cc4101) 30min 恢复流量**: 16 req, 15×primary 200 + 1×fallback 200 = 可见 SR **100.0%** (16/16)
  - fallback 触发率 1/16 = **6.25%** (目标 <10%, 达标) — R716-R724 连续 9 轮零流量 streak 终结
  - 唯一 fallback: req=7c201729 primary glm5_2_nv 502 after 34s → dsv4p 200 after 2s
- **nv_gw 全量 30min**:
  - dsv4p_nv: 63×200 = SR **100.0%** (持平 R724 100.0%)
  - glm5_2_nv: 0 req 最终态 (tier attempts=0 — pexec 失败后 integrate 成功的 req 被 ABS-CAP/IncompleteRead 截断→502→cc4101 fallback)
- **6h SR (更大小本)**:
  - glm5_2_nv: 29×200/19×502 = SR **60.4%** (48 req 低流量) — avg 200=52.1s, 502=153.0s
    - 502: all_tiers_exhausted×6, NVStream_IncompleteRead×11, stream_absolute_cap×3, NVAnthCollect_IncompleteRead×1
    - tier: pexec_conn_RD×19(k2重灾), IntegrateRD×15, integrate_conn_RD×7, 429×9, pexec_SSLEOF×4, pexec_500×1
    - per-key: k2 pexec fid=3b9748d8 conn_RD×18 (最差), k1/k3 integrate IntegrateRD 集中; k0/k4 pexec success×12 健康
  - dsv4p_nv: 389×200/18×429/18×502 = SR **91.5%** (425 req 高流量, 主力稳定)
- **错误分类 (6h, 无新错误类型)**: all_tiers_exhausted/NVStream_IncompleteRead/stream_absolute_cap/NVAnthCollect_IncompleteRead + tier pexec_conn_RD/IntegrateRD/429/SSLEOF — 全 NVCF 上游连接/配额副作用, 非 nv_gw 可控
- **dsv4p 延迟**: avg 7.2s, max 32.2s, ttfb 6.8s, finish tool_calls×49/stop×18/length×7 (无 zombie)
- **buffer/wait/keymanager 日志**: docker logs --since 30m = 0 行 (最后日志 19:56 CST, NV-STREAM-ABS-CAP 150s 截断 + Broken pipe)
- **根因**: glm5_2_nv 6h SR 60.4% 低流量下 NVCF 上游连接断开 (k2 pexec 3b9748d8 重灾), 但 cc4101 fallback dsv4p 兜底 → 用户可见 SR 100%, fb 6.25% 达标

### 验证: NOP 无需 restart
- `curl /health`: nv_gw ok(5keys, glm5_2_nv/dsv4p_nv/kimi_nv) + cc4101 ok(primary=glm5_2_nv) + dsv4p_nv40066 ok(5keys) — 全 ok
- `docker ps`: nv_gw Up 4h, cc4101 Up 5h, dsv4p_nv40066 Up 5h, nv_gw_stable Up 43h, logs_db Up 4d — 全 Up
- 配置零漂移 (R661 baseline):
  - nv_gw: NVU_DISABLE_MS_FALLBACK=1, buffer 5×90s=450s, UPSTREAM_TIMEOUT=90, TIER_COOLDOWN_S=180, TIER_TIMEOUT_BUDGET_S=180, NVU_TIER_BUDGET_GLM5_2_NV=120
  - cc4101: PRIMARY=glm5_2_nv→nv_gw:40006, FALLBACK=dsv4p_nv→dsv4p_nv40066:40066, STREAM_TOTAL=470, HEADER=400, UPSTREAM_IDLE=150, PRIMARY_SKIP_S=30, FAIL_THRESHOLD=3
  - per-key: NV_GLM52_KEY_FID_BIND=0:0;2:1;4:2, NV_GLM52_KEY_MODE_BIND=0:pexec_us_rr;1:integrate_us_rr;2:pexec_us_rr;3:integrate_us_rr;4:pexec_us_rr

## 下一步
- 持续监控 cc2 SR + fallback 触发率 (目标 SR99%+ fb<10%)
- glm5_2_nv k2 pexec fid=3b9748d8 连续 RemoteDisconnected×18 重灾区 — 若持续恶化可考虑切 k2 到 b1b22d03 (k0/k4 用 b1b22d03 success×12 健康), 但需更多数据
- 若 cc2 流量持续恢复后 fallback 率 >10% 再深入查 glm5_2_nv tier
- R661 post-restart ~43h+ 仍无新错误类型, 配置稳定

## 参数快照 (无变化, 沿用 R661)
- nv_gw: NVU_DISABLE_MS_FALLBACK=1, buffer 5×90s=450s, UPSTREAM_TIMEOUT=90, TIER_COOLDOWN_S=180
  - per-key FID bind: NV_GLM52_KEY_FID_BIND=0:0;2:1;4:2 (k0/k2/k4 pexec fid1/2/3)
  - per-key mode bind: NV_GLM52_KEY_MODE_BIND=0:pexec_us_rr;1:integrate_us_rr;2:pexec_us_rr;3:integrate_us_rr;4:pexec_us_rr
- cc4101: PRIMARY=glm5_2_nv→nv_gw:40006, FALLBACK=dsv4p_nv→dsv4p_nv40066:40066, STREAM_TOTAL=470, HEADER=400, UPSTREAM_IDLE=150
- deadline 链: 90s×5=450s buffer < 470s cc4101 < 600s API < 900s idle
