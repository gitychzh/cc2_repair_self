# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: R724 (NOP 巡检, 2026-08-03 20:30 CST)
> 上轮: R723 (NOP, cc2 零流量 dsv4p 100% glm5_2_nv 50% 小样本噪音)

## 本轮 (R724) 改了什么 + 依据 + 验证

### 改动: 不改码 (NOP)

### 依据 (30min 窗口 ~19:55-20:25 CST, 注入数据)
- **cc2 (cc4101-primary) 30min**: 0 rows — cc2 本窗口零流量, 无数据不动手 (连续第 9 轮零流量)
- **nv_gw 全量 30min** (hermes caller, 非 cc2):
  - dsv4p_nv: 69×200 = SR **100.0%** (69/69) — 比 R723 的 100.0% (64/64) 持平, 持续健康
    - 九轮趋势: R716 91.3%→R717 92.0%→R718 91.3%→R719 93.1%→R720 97.7%→R721 98.5%→R722 98.5%→R723 100.0%→R724 100.0%
  - glm5_2_nv: 1×502 = SR **0.0%** (0/1) — 1 req 小样本噪音 (单 req 502, 非 NVCF 全挂)
    - 九轮趋势: 0%→50%→57.1%→57.1%→66.7%→66.7%→66.7%→50.0%→0% (小样本波动, 非 NVCF 新挂)
  - other|dsv4p_nv|200×15 — 其他 caller 流量也走 dsv4p 兜底
- **错误分类 (30min, 无新错误类型)**:
  - stream_absolute_cap × 1 (avg_dur 187332ms) — 绝对时长封顶 (非新类型, R723 曾见)
  - 注: R723 的 NVStream_IncompleteRead × 1 本窗口消失
- **per-key (dsv4p)**: k0 13×200, k1 14×200, k2 14×200, k3 14×200, k4 14×200 — 均衡
- **per-egress-IP (dsv4p)**: 5 US IP 全 100% (13-14 req 各) — IP 轮转健康
- **dsv4p 200 延迟**: avg 7464ms, max 32224ms, min 1430ms, ttfb 6918ms, avg_in 2 tok, avg_out 10 tok, finish_reason tool_calls×46/stop×16/length×7 (无 zombie)
- **tier 错误**: IntegrateRemoteDisconnected×2(k3/k4), pexec_conn_RemoteDisconnected×1(k2) — 全 NVCF 上游配额副作用 (R723 的 IntegrateRD×3/k1 消失, k1 恢复)
- **fallback**: f×70 (全非 cc2, hermes 流量)
- **buffer/wait/keymanager 日志**: 无 (无 buffer 触发, 链路直接 fallback 到 dsv4p)
- **根因**: glm5_2_nv NVCF 上游九轮趋势 0%-66.7% 区间波动, 本轮 1 req 小样本噪音, 非 NVCF 新挂; cc4101 fallback → dsv4p 兜底 100% 稳健; cc2 本窗口零流量

### 验证: NOP 无需 restart
- `curl /health`: nv_gw ok(5keys, glm5_2_nv/dsv4p_nv/kimi_nv) + cc4101 ok(primary=glm5_2_nv) + dsv4p_nv40066 ok(5keys) — 全 ok
- `docker ps`: nv_gw Up 4h, cc4101 Up 5h, dsv4p_nv40066 Up 5h, nv_gw_stable Up 42h, logs_db Up 4d — 全 Up
- 配置零漂移 (R661 baseline):
  - nv_gw: NVU_DISABLE_MS_FALLBACK=1, buffer 5×90s=450s, UPSTREAM_TIMEOUT=90, TIER_COOLDOWN_S=180, TIER_TIMEOUT_BUDGET_S=180
  - cc4101: PRIMARY=glm5_2_nv→nv_gw:40006, FALLBACK=dsv4p_nv→dsv4p_nv40066:40066, STREAM_TOTAL=470, HEADER=400, UPSTREAM_IDLE=150, PRIMARY_SKIP_S=30, FAIL_THRESHOLD=3
  - dsv4p_nv40066: pexec-only, NV_INTEGRATE_MODELS=空, NVU_DISABLE_MS_FALLBACK=1, PEER_FALLBACK=0

## 下一步
- 持续监控 cc2 SR + fallback 触发率 (目标 SR99%+ fb<10%)
- glm5_2_nv NVCF 上游九轮趋势 0%-66.7% 区间波动, 继续观察是否突破稳态
- 若 cc2 流量恢复后 fallback 率 >10% 再深入查 glm5_2_nv tier
- R661 post-restart ~42h+ 仍无新错误类型, 配置稳定

## 参数快照 (无变化, 沿用 R661)
- nv_gw: NVU_DISABLE_MS_FALLBACK=1, buffer 5×90s=450s, UPSTREAM_TIMEOUT=90, TIER_COOLDOWN_S=180
  - per-key FID bind: NV_GLM52_KEY_FID_BIND=0:0;2:1;4:2 (k0/k2/k4 pexec fid1/2/3)
  - per-key mode bind: NV_GLM52_KEY_MODE_BIND=0:pexec_us_rr;1:integrate_us_rr;2:pexec_us_rr;3:integrate_us_rr;4:pexec_us_rr
- cc4101: PRIMARY=glm5_2_nv→nv_gw:40006, FALLBACK=dsv4p_nv→dsv4p_nv40066:40066, STREAM_TOTAL=470, HEADER=400, UPSTREAM_IDLE=150
- deadline 链: 90s×5=450s buffer < 470s cc4101 < 600s API < 900s idle
