# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: R696 (NOP 巡检, 2026-08-03 18:45 CST)
> 上轮: R695 (NOP, cc2 16req SR100% fb6.25%)

## 本轮 (R696) 改了什么 + 依据 + 验证

### 改动: 不改码 (NOP)

### 依据 (30min 窗口实测 18:13-18:43 CST = 10:13-10:43 UTC)
- **cc2 (cc_requests)**: 16req 全 200, **SR 100%**, fallback 1/16 = **6.25%** (< 10% 目标 ✅)
- nv_gw 全量: dsv4p_nv 96.1% (49/51), glm5_2_nv 61.5% (8/13) — 但**5×502 全非 cc2 管辖**
- **NVStream_IncompleteRead ×5 全部是 openclaw/hermes 的请求**:
  - 18:23:43 (144s) → openclaw k4, 18:23:49 (33s) → openclaw k4 retry
  - 18:27:44 (67s) → hermes k3, 18:29:44 (117s) → hermes k1, 18:32:41 (124s) → hermes k3
  - 全部 content_flushed=0c, ttfb_recorded=False — NVCF 上游 TTFB 前断连, 非配置问题
- cc2 请求在 nv_gw 走 buffer rotation (NVU_BUFFER_CALLERS 匹配), 无 CALLER_BIND, 无 IncompleteRead
- tier attempts: k2(pexec) 8×RemoteDisconnected+4×429+2×success, k3(integrate) 3×success+1×RD, k0/k1/k4 各 IntegrateRD
- KeyManager: k3/k4 RemoteDisconnected penalty=5s no conn_count ×7 — 快速恢复生效
- 无 BUFFER-/WAIT- 日志
- R661 post-restart ~41h+ 无 NVAnthCollect_IncompleteRead 再现

### 验证: NOP 无需 restart
- `curl /health`: nv_gw ok(5keys) + cc4101 ok + dsv4p_nv40066 ok(5keys)
- `docker ps`: nv_gw Up 3h, cc4101 Up 3h, dsv4p_nv40066 Up 3h, nv_gw_stable Up 41h — 全 Up
- 配置实测无漂移:
  - NVU_DISABLE_MS_FALLBACK=1, buffer 5×90s=450s, UPSTREAM_TIMEOUT=90, TIER_COOLDOWN_S=180
  - NV_GLM52_KEY_FID_BIND=0:0;2:1;4:2, NV_GLM52_KEY_MODE_BIND=0:pexec_us_rr;1:integrate_us_rr;2:pexec_us_rr;3:integrate_us_rr;4:pexec_us_rr

## 下一步
- 持续监控 cc2 流量 SR + fallback 触发率 (目标 SR99%+ fb<10%)
- glm5_2_nv 全量 SR 61.5% — 但 5×502 全非 cc2, 关注是否蔓延到 cc4101-primary
- NVStream_IncompleteRead 是 NVCF 上游间歇断连, 非 nv_gw 可控
- 等 NVAnthCollect_IncompleteRead 是否再现 (R661 修复窗口 ~41h+ clean)

## 参数快照 (无变化, 沿用 R661)
- nv_gw: NVU_DISABLE_MS_FALLBACK=1, buffer 5×90s=450s, UPSTREAM_TIMEOUT=90, TIER_COOLDOWN_S=180
  - per-key FID bind: NV_GLM52_KEY_FID_BIND=0:0;2:1;4:2 (k0/k2/k4 pexec fid1/2/3)
  - per-key mode bind: NV_GLM52_KEY_MODE_BIND=0:pexec_us_rr;1:integrate_us_rr;2:pexec_us_rr;3:integrate_us_rr;4:pexec_us_rr
- cc4101: PRIMARY=glm5_2_nv→nv_gw:40006, FALLBACK=dsv4p_nv→dsv4p_nv40066:40066, STREAM_TOTAL=470, HEADER=400, UPSTREAM_IDLE=150
- deadline 链: 90s×5=450s buffer < 470s cc4101 < 600s API < 900s idle
