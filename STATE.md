# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: R708 (NOP 巡检, 2026-08-03 19:08 CST)
> 上轮: R707 (NOP, cc2 零流量)

## 本轮 (R708) 改了什么 + 依据 + 验证

### 改动: 不改码 (NOP)

### 依据 (60min 窗口实测 ~10:05-11:05 UTC = 18:05-19:05 CST)
- **cc2 (cc4101-primary)**: 60min 窗口 nv_requests 中 caller=cc4101-primary **零行**, 无数据不动手
- **cc4101 真实 SR (cc_requests 表, 含 fallback)**: 16req 全 200, SR **100%**, fb=6.25%(1/16<10%目标), max_dur=101s 无 deadline 超时
- **nv_gw 全量 60min by caller×model×status** (全非cc2管辖):
  - hermes|dsv4p_nv|200×72|502×4 (SR 94.7%)
  - hermes|glm5_2_nv|200×7|502×9 (SR 43.8%)
  - openclaw|dsv4p_nv|200×25|502×1 (SR 96.2%)
  - openclaw|glm5_2_nv|200×1|502×2 (SR 33.3%)
  - other|dsv4p_nv|200×1
- **60min nv_requests 错误分类**:
  - NVStream_IncompleteRead ×10 — NVCF 上游 stream 中断
  - all_tiers_exhausted ×5 — glm5_2_nv 5key 全败
  - stream_absolute_cap ×1 — 超总预算
- **60min nv_tier_attempts 错误**:
  - pexec_conn_RemoteDisconnected ×12, IntegrateRemoteDisconnected ×9, 429_nv_rate_limit ×6
  - NVCFPexecRemoteDisconnected ×5, pexec_success ×3, integrate_success ×3, integrate_conn_RemoteDisconnected ×1
  - 全是 NVCF 上游 RemoteDisconnected/429 配额副作用, 非 nv_gw 可控
- **最近 30min nv_gw 日志 (19:04-19:05)**:
  - k3 (pexec fid3b9748d8) RemoteDisconnected → KeyMgr penalty=5s no conn_count 快速恢复生效
  - NV-STREAMBREAK-STATE: content_flushed=444c ttfb_recorded=True — mid-stream 断, 已 graceful close
  - 无 BUFFER-/WAIT- 日志
- R661 post-restart ~41h+ 仍无 NVAnthCollect_IncompleteRead 再现

### 验证: NOP 无需 restart
- `curl /health`: nv_gw ok(5keys) + cc4101 ok + dsv4p_nv40066 ok(5keys)
- `docker ps`: nv_gw Up 3h, cc4101 Up 4h, dsv4p_nv40066 Up 4h, nv_gw_stable Up 41h, logs_db Up 4d — 全 Up
- 配置实测无漂移 (R707 已确认):
  - NVU_DISABLE_MS_FALLBACK=1, buffer 5×90s=450s, UPSTREAM_TIMEOUT=90, TIER_COOLDOWN_S=180
  - NV_GLM52_KEY_FID_BIND=0:0;2:1;4:2, NV_GLM52_KEY_MODE_BIND=0:pexec_us_rr;1:integrate_us_rr;2:pexec_us_rr;3:integrate_us_rr;4:pexec_us_rr

## 下一步
- 持续监控 cc2 流量 SR + fallback 触发率 (目标 SR99%+ fb<10%)
- glm5_2_nv tier RemoteDisconnected/429 是 NVCF 上游间歇断连+配额, 非 nv_gw 可控
- 关注 NVStream_IncompleteRead 是否蔓延到 cc4101-primary (目前 cc2 零流量, 未蔓延)
- R661 post-restart ~41h+ 仍无 NVAnthCollect_IncompleteRead 再现

## 参数快照 (无变化, 沿用 R661)
- nv_gw: NVU_DISABLE_MS_FALLBACK=1, buffer 5×90s=450s, UPSTREAM_TIMEOUT=90, TIER_COOLDOWN_S=180
  - per-key FID bind: NV_GLM52_KEY_FID_BIND=0:0;2:1;4:2 (k0/k2/k4 pexec fid1/2/3)
  - per-key mode bind: NV_GLM52_KEY_MODE_BIND=0:pexec_us_rr;1:integrate_us_rr;2:pexec_us_rr;3:integrate_us_rr;4:pexec_us_rr
- cc4101: PRIMARY=glm5_2_nv→nv_gw:40006, FALLBACK=dsv4p_nv→dsv4p_nv40066:40066, STREAM_TOTAL=470, HEADER=400, UPSTREAM_IDLE=150
- deadline 链: 90s×5=450s buffer < 470s cc4101 < 600s API < 900s idle
