# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: R707 (NOP 巡检, 2026-08-03 19:00 CST)
> 上轮: R706 (NOP, cc2 16req SR100% fb6.25%)

## 本轮 (R707) 改了什么 + 依据 + 验证

### 改动: 不改码 (NOP)

### 依据 (30min 窗口实测 ~10:20-10:50 UTC = 18:20-18:50 CST)
- **cc2 (cc4101-primary)**: 本窗口零流量 (caller=cc4101-primary 空), 无数据不动手
- **dsv4p_nv 全量**: 43req, 42×200, SR **97.7%** (1×NVStream_IncompleteRead = hermes 非cc2管辖)
  - per-key: k0=9×200, k1=8×200, k2=7×200, k3=7×200, k4=11×200, 1×502
  - per-egress-IP: 5 IP 全 100% SR (134.195.101.120=11, 180=9, 188=8, 194=7, 203.10.96.139=7)
  - avg_dur=15805ms, max=64964ms, min=1078ms, ttfb=15150ms, avg_in=3tok, avg_out=7tok
  - finish_reason: tool_calls×35, stop×6, length×1 (无 zombie)
- **glm5_2_nv 全量**: 10req, 4×200, SR **40%** (6×502 全 hermes 非cc2管辖)
- **错误分类 (nv_requests)**:
  - NVStream_IncompleteRead ×3 (avg_dur 103631ms) — NVCF 上游 stream 中断
  - all_tiers_exhausted|all_tiers_failed_in_mapped_tier ×3 (avg_dur 182087ms) — glm5_2_nv 5key 全败
  - stream_absolute_cap ×1 (avg_dur 239878ms) — 超总预算
- **tier attempts (glm5_2_nv, 全非cc2)**:
  - k0: IntegrateRemoteDisconnected ×2
  - k1: IntegrateRemoteDisconnected ×1
  - k2 (pexec fid3b9748d8): pexec_conn_RemoteDisconnected ×6 + IntegrateRemoteDisconnected ×1 + NVCFPexecRemoteDisconnected ×1 + 429_nv_rate_limit ×1 + pexec_success ×2
  - k3 (pexec): NVCFPexecRemoteDisconnected ×2 + 429_nv_rate_limit ×1
  - k4 (integrate): IntegrateRemoteDisconnected ×2
- **fallback**: 53req 全 f=53 (0% fb_triggered, 全 hermes/openclaw 流量非cc2)
- **buffer/wait/keymgr 日志**: 无 BUFFER-/WAIT- 日志
- R661 post-restart ~41h+ 无 NVAnthCollect_IncompleteRead 再现

### 验证: NOP 无需 restart
- `curl /health`: nv_gw ok(5keys) + cc4101 ok + dsv4p_nv40066 ok(5keys)
- `docker ps`: nv_gw Up 3h, cc4101 Up 4h, dsv4p_nv40066 Up 4h, nv_gw_stable Up 41h, logs_db Up 4d — 全 Up
- 配置实测无漂移:
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
