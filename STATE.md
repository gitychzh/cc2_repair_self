# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: R713 (NOP 巡检, 2026-08-03 19:31 CST)
> 上轮: R712 (NOP, cc2 零流量 dsv4p_nv SR93.3% glm5_2_nv SR0% NVCF上游退化)

## 本轮 (R713) 改了什么 + 依据 + 验证

### 改动: 不改码 (NOP)

### 依据 (30min 窗口 ~19:01-19:31 CST)
- **cc2 (cc4101-primary) 流量**: 30min 窗口空 — cc2 本窗口零请求, 无数据不动手
- **nv_gw 全量 30min** (非 cc2 流量, hermes/openclaw caller):
  - dsv4p_nv: 32×200 + 2×502 = SR **94.1%** (32/34) — 兜底链路健康
  - glm5_2_nv: 6×502 = SR **0%** (0/6) — NVCF 上游持续退化 (10:20 起 ~9h 未��复), 非 nv_gw 可控
- **错误分类 (30min)**:
  - all_tiers_exhausted × 4 (avg 182s) — 5key 全挂, glm5_2_nv NVCF 上游配额副作用
  - NVStream_IncompleteRead × 3 (avg 94s) — NVCF 上游 mid-stream 断连
  - stream_absolute_cap × 1 (200s) — 单请求触达 buffer 总预算
- **tier 错误 (glm5_2_nv)**: IntegrateRemoteDisconnected×4 (k1×1,k2×2,k3×1) + pexec_conn_RemoteDisconnected×3 (k2) + NVCFPexecRemoteDisconnected×1 (k1) — 全 RemoteDisconnected, NVCF 上游间歇断连
- **dsv4p per-key**: k0 6×200, k1 6×200, k2 8×200, k3 7×200, k4 5×200+1×502 — 均衡健康
- **dsv4p per-IP**: 5 US IPv4 全 83~100% (203.10.96.139 8×100%, 134.195.101.194 7×100%)
- **dsv4p 200 延迟**: avg 10.6s, max 65.2s, min 1.3s, ttfb 10.2s, avg_in 12 tok, avg_out 41 tok
- **dsv4p finish_reason**: tool_calls×21, stop×7, length×4 — 无 zombie
- **fallback**: f×40 (全非 cc2 流量)
- **根因**: glm5_2_nv NVCF 上游持续退化 (10:20 起 ~9h), cc4101 fallback → dsv4p 兜底, cc2 本窗口零流量无影响

### 验证: NOP 无需 restart
- `curl /health`: nv_gw ok(5keys) + cc4101 ok(primary=glm5_2_nv) + dsv4p_nv40066 ok(5keys)
- `docker ps`: nv_gw Up 4h, cc4101 Up 4h, dsv4p_nv40066 Up 4h, nv_gw_stable Up 42h, logs_db Up 4d — 全 Up
- 配置零漂移 (R661 baseline):
  - nv_gw: NVU_DISABLE_MS_FALLBACK=1, buffer 5×90s=450s, UPSTREAM_TIMEOUT=90, TIER_COOLDOWN_S=180, TIER_TIMEOUT_BUDGET_S=180
  - NV_GLM52_KEY_FID_BIND=0:0;2:1;4:2, NV_GLM52_KEY_MODE_BIND=0:pexec_us_rr;1:integrate_us_rr;2:pexec_us_rr;3:integrate_us_rr;4:pexec_us_rr
  - cc4101: PRIMARY=glm5_2_nv→nv_gw:40006, FALLBACK=dsv4p_nv→dsv4p_nv40066:40066, STREAM_TOTAL=470, HEADER=400, UPSTREAM_IDLE=150, PRIMARY_SKIP_S=30, FAIL_THRESHOLD=3
  - dsv4p_nv40066: pexec-only, NV_INTEGRATE_MODELS=空, NVU_DISABLE_MS_FALLBACK=1, PEER_FALLBACK=0

## 下一步
- 持续监控 cc2 SR + fallback 触发率 (目标 SR99%+ fb<10%)
- glm5_2_nv NVCF 上游持续退化中 (10:20 起 ~9h), 依赖 dsv4p 兜底, 非 nv_gw 可控
- 若 cc2 流量恢复后 fallback 率 >10% 再深入查 glm5_2_nv tier
- R661 post-restart ~42h+ 仍无新错误类型, 配置稳定

## 参数快照 (无变化, 沿用 R661)
- nv_gw: NVU_DISABLE_MS_FALLBACK=1, buffer 5×90s=450s, UPSTREAM_TIMEOUT=90, TIER_COOLDOWN_S=180
  - per-key FID bind: NV_GLM52_KEY_FID_BIND=0:0;2:1;4:2 (k0/k2/k4 pexec fid1/2/3)
  - per-key mode bind: NV_GLM52_KEY_MODE_BIND=0:pexec_us_rr;1:integrate_us_rr;2:pexec_us_rr;3:integrate_us_rr;4:pexec_us_rr
- cc4101: PRIMARY=glm5_2_nv→nv_gw:40006, FALLBACK=dsv4p_nv→dsv4p_nv40066:40066, STREAM_TOTAL=470, HEADER=400, UPSTREAM_IDLE=150
- deadline 链: 90s×5=450s buffer < 470s cc4101 < 600s API < 900s idle
