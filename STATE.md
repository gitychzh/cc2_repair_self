# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: R718 (NOP 巡检, 2026-08-03 19:58 CST)
> 上轮: R717 (NOP, cc2 零流量 dsv4p92.0% glm5_2_nv50% NVCF上游缓慢恢复)

## 本轮 (R718) 改了什么 + 依据 + 验证

### 改动: 不改码 (NOP)

### 依据 (30min 窗口 ~19:28-19:58 CST, 注入数据)
- **cc2 (cc4101-primary) 30min**: 0 rows — cc2 本窗口零流量, 无数据不动手
- **nv_gw 全量 30min** (hermes caller, 非 cc2):
  - dsv4p_nv: 21×200 + 2×502 = SR **91.3%** (21/23) — 兜底链路健康
  - glm5_2_nv: 4×200 + 3×502 = SR **57.1%** (4/7) — 持续小幅恢复 (R715 0%→R716 0%→R717 50%→R718 57.1%), NVCF 上游缓慢恢复中
- **错误分类 (30min, 无新错误类型)**:
  - all_tiers_exhausted × 3 (all_tiers_failed_in_mapped_tier, avg_dur 126s) — 5key 全挂, NVCF 上游配额副作用
  - NVStream_IncompleteRead × 1 (avg_dur 78s) — mid-stream 断流
  - stream_absolute_cap × 1 (avg_dur 187s) — 绝对时长封顶 (非新类型, R713 曾见)
- **per-key (dsv4p)**: k0 5×200, k1 5×200, k2 4×200, k3 4×200, k4 3×200 — 均衡
- **per-egress-IP (dsv4p)**: 5 US IP 全 100% (3~5 req 各) — IP 轮转健康
- **dsv4p 200 延迟**: avg 12.6s, max 28.7s, min 4.7s, ttfb 11.6s, finish_reason tool_calls×19/stop×2 (无 zombie)
- **tier 错误**: IntegrateRemoteDisconnected×3(k1/k3/k4), pexec_500×1(k2), pexec_conn_RemoteDisconnected×4(k2), pexec_success×1(k2) — 全 NVCF 上游配额副作用, 非 nv_gw 可控
- **fallback**: f×30 (全非 cc2, hermes 流量)
- **buffer/wait/keymanager 日志**: 无 (无 buffer 触发, 链路直接 fallback 到 dsv4p)
- **根因**: glm5_2_nv NVCF 上游缓慢恢复中 (四轮趋势 0%→57.1%), cc4101 fallback → dsv4p 兜底, cc2 本窗口零流量

### 验证: NOP 无需 restart
- `curl /health`: nv_gw ok(5keys, glm5_2_nv/dsv4p_nv/kimi_nv) + cc4101 ok(primary=glm5_2_nv) + dsv4p_nv40066 ok(5keys) — 全 ok
- `docker ps`: nv_gw Up 4h, cc4101 Up 5h, dsv4p_nv40066 Up 5h, nv_gw_stable Up 42h, logs_db Up 4d — 全 Up
- 配置零漂移 (R661 baseline):
  - nv_gw: NVU_DISABLE_MS_FALLBACK=1, buffer 5×90s=450s, UPSTREAM_TIMEOUT=90, TIER_COOLDOWN_S=180, TIER_TIMEOUT_BUDGET_S=180
  - NV_GLM52_KEY_FID_BIND=0:0;2:1;4:2, NV_GLM52_KEY_MODE_BIND=0:pexec_us_rr;1:integrate_us_rr;2:pexec_us_rr;3:integrate_us_rr;4:pexec_us_rr
  - cc4101: PRIMARY=glm5_2_nv→nv_gw:40006, FALLBACK=dsv4p_nv→dsv4p_nv40066:40066, STREAM_TOTAL=470, HEADER=400, UPSTREAM_IDLE=150, PRIMARY_SKIP_S=30, FAIL_THRESHOLD=3
  - dsv4p_nv40066: pexec-only, NV_INTEGRATE_MODELS=空, NVU_DISABLE_MS_FALLBACK=1, PEER_FALLBACK=0

## 下一步
- 持续监控 cc2 SR + fallback 触发率 (目标 SR99%+ fb<10%)
- glm5_2_nv NVCF 上游缓慢恢复中 (0%→57.1% 四轮趋势), 继续观察是否恢复到稳态
- 若 cc2 流量恢复后 fallback 率 >10% 再深入查 glm5_2_nv tier
- R661 post-restart ~42h+ 仍无新错误类型, 配置稳定

## 参数快照 (无变化, 沿用 R661)
- nv_gw: NVU_DISABLE_MS_FALLBACK=1, buffer 5×90s=450s, UPSTREAM_TIMEOUT=90, TIER_COOLDOWN_S=180
  - per-key FID bind: NV_GLM52_KEY_FID_BIND=0:0;2:1;4:2 (k0/k2/k4 pexec fid1/2/3)
  - per-key mode bind: NV_GLM52_KEY_MODE_BIND=0:pexec_us_rr;1:integrate_us_rr;2:pexec_us_rr;3:integrate_us_rr;4:pexec_us_rr
- cc4101: PRIMARY=glm5_2_nv→nv_gw:40006, FALLBACK=dsv4p_nv→dsv4p_nv40066:40066, STREAM_TOTAL=470, HEADER=400, UPSTREAM_IDLE=150
- deadline 链: 90s×5=450s buffer < 470s cc4101 < 600s API < 900s idle
