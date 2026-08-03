# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: R721 (NOP 巡检, 2026-08-03 20:11 CST)
> 上轮: R720 (NOP, cc2 零流量 dsv4p97.7% glm5_2_nv66.7% NVCF上游恢复停滞)

## 本轮 (R721) 改了什么 + 依据 + 验证

### 改动: 不改码 (NOP)

### 依据 (30min 窗口 ~19:41-20:11 CST, 注入数据)
- **cc2 (cc4101-primary) 30min**: 0 rows — cc2 本窗口零流量, 无数据不动手 (连续第 6 轮零流量)
- **nv_gw 全量 30min** (hermes caller, 非 cc2):
  - dsv4p_nv: 64×200 + 1×502 = SR **98.5%** (64/65) — 兜底链路继续回升 (R718 91.3%→R719 93.1%→R720 97.7%→R721 98.5%)
  - glm5_2_nv: 4×200 + 2×502 = SR **66.7%** (4/6) — 持平 R720, 六轮趋势 0%→50%→57.1%→57.1%→66.7%→66.7% 恢复停滞
- **错误分类 (30min, 无新错误类型)**:
  - NVStream_IncompleteRead × 1 (avg_dur 78s) — mid-stream 断流
  - all_tiers_exhausted × 1 (all_tiers_failed_in_mapped_tier, avg_dur 90s) — 5key 全挂
  - stream_absolute_cap × 1 (avg_dur 187s) — 绝对时长封顶 (非新类型, R713 曾见)
- **per-key (dsv4p)**: k0 13×200, k1 13×200, k2 13×200, k3 13×200, k4 12×200 — 均衡
- **per-egress-IP (dsv4p)**: 5 US IP 全 100% (12-13 req 各) — IP 轮转健康
- **dsv4p 200 延迟**: avg 7377ms, max 27511ms, min 1430ms, ttfb 6885ms, avg_in 2 tok, avg_out 11 tok, finish_reason tool_calls×44/stop×13/length×7 (无 zombie)
- **tier 错误**: IntegrateRemoteDisconnected×3(k1/k3/k4), pexec_500×1(k2), pexec_conn_RemoteDisconnected×4(k2), pexec_success×1(k2) — 全 NVCF 上游配额副作用, 非 nv_gw 可控
- **fallback**: f×71 (全非 cc2, hermes 流量)
- **buffer/wait/keymanager 日志**: 无 (无 buffer 触发, 链路直接 fallback 到 dsv4p)
- **根因**: glm5_2_nv NVCF 上游恢复停滞于 66.7% (R720 66.7%→R721 66.7% 持平), cc4101 fallback → dsv4p 兜底, cc2 本窗口零流量

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
- glm5_2_nv NVCF 上游恢复停滞于 66.7%, 继续观察是否突破稳态
- 若 cc2 流量恢复后 fallback 率 >10% 再深入查 glm5_2_nv tier
- R661 post-restart ~42h+ 仍无新错误类型, 配置稳定

## 参数快照 (无变化, 沿用 R661)
- nv_gw: NVU_DISABLE_MS_FALLBACK=1, buffer 5×90s=450s, UPSTREAM_TIMEOUT=90, TIER_COOLDOWN_S=180
  - per-key FID bind: NV_GLM52_KEY_FID_BIND=0:0;2:1;4:2 (k0/k2/k4 pexec fid1/2/3)
  - per-key mode bind: NV_GLM52_KEY_MODE_BIND=0:pexec_us_rr;1:integrate_us_rr;2:pexec_us_rr;3:integrate_us_rr;4:pexec_us_rr
- cc4101: PRIMARY=glm5_2_nv→nv_gw:40006, FALLBACK=dsv4p_nv→dsv4p_nv40066:40066, STREAM_TOTAL=470, HEADER=400, UPSTREAM_IDLE=150
- deadline 链: 90s×5=450s buffer < 470s cc4101 < 600s API < 900s idle
