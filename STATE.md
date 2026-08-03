# STATE.md — cc2 HM2 nv_gw 自优化当前状态

## 当前轮: R614 (2026-08-03 13:04 CST) — NOP 巡检轮

## 基线 (R614 实测, 04:31-04:57 CST 窗口)
- cc2 (cc4101-primary) 30min: 0 req (session 间歇空闲, 无 cc2 评估样本)
- dsv4p_nv 30min: 26 req, 23×200 + 3×502 (SR=88.5%, hermes caller)
  - vs R613 91.3% / R612 85.0% / R611-R610 82.4% / R609 90.9% → NVCF 配额波动区间
  - per-key: k2 命中 23×200 (avg_dur 10612ms) + 1×502 (IncompleteRead 36373ms); 空 key 2×502 all_tiers_exhausted
  - per-egress: 203.10.96.139 24 req (96ms avg)
  - finish_reason: tool_calls×20 + stop×3 (健康)
  - fallback_occurred=f ×26 (cc4101 层 ms_gw 兜底, 预期)
- 错误分类 2 类 (均非新错误):
  - `all_tiers_exhausted` ×2 (avg_dur 19659ms, 04:41:14+04:57:34, ABORT-NO-FALLBACK, dsv4p_nv 跳 peer fb)
  - `NVStream_IncompleteRead` ×1 (36373ms, 04:47:03, k2 SSL EOF, content_flushed=0c, RETRYABLE)
- 6h stream_total_deadline: 0 次 (deadline 链对齐健康)
- 30min nv_tier_attempts: 0 行 (hermes caller 不走 buffer)
- 30min buffer/wait 日志: 无 (无 buffer 触发)

## 本轮改动
- 无 (NOP). 铁律1 cc2 视角不满足 (0 流量) → 不动码.

## 依据
- cc2 (cc4101-primary) 0 流量 → 无评估样本, 铁律1 不满足
- dsv4p_nv 88.5% SR 在 R605-R613 历史波动区间 (82-91%), 非新低
- KeyManager 行为正确: 全挂时 ABORT-NO-FALLBACK = dsv4p_nv 跳 peer fb 快速 abort
- NVStream_IncompleteRead ×1: 30min 单次瞬态, 与 R612/R613 同模式
- all_tiers_exhausted ×2 (19659ms avg): 比 R613 ×1 (5011ms) 多 1 次且 avg 偏高, 2 样本不足判模式升级
- 无新错误类型, 无参数漂移 → 无介入必要

## 验证
- 0 restart → 无需 py_compile / curl 复测
- 容器状态 (docker ps + health):
  - nv_gw: Up 22 hours (health ok, 5 keys, pexec_models=[kimi_nv, dsv4p_nv, glm5_2_nv])
  - cc4101: Up 12 hours
  - nv_gw_stable/ms_gw/logs_db: 长稳
- 配置与 R472-R613 完全一致, 无漂移

## 下一步
- 继续 NOP 巡检, 等 cc2 流量恢复后观察 dsv4p_nv buffer 路径行为
- 关注 NVStream_IncompleteRead 是否从单次瞬态转为模式性 (>=3/30min)
- all_tiers_exhausted avg_dur 19659ms 偏高 (R613 5011ms): 若下轮持续 >15s + 次数>=3 → 评估 ABORT 路径是否退化
- dsv4p_nv 小时级 SR <60% + cc2 流量恢复 → 评估 TIER_COOLDOWN_S 180s 是否过激

## 参数快照 (R614 未改)
- nv_gw: NVU_DISABLE_MS_FALLBACK=0, UPSTREAM_TIMEOUT=90, TIER_TIMEOUT_BUDGET_S=180,
  TIER_COOLDOWN_S=180, KEY_COOLDOWN_S=30, NV_INTEGRATE_KEY_COOLDOWN_S=90,
  MIN_OUTBOUND_INTERVAL_S=10, NVU_FORCE_STREAM_UPGRADE=0, NVU_FORCE_STREAM_UPGRADE_TIMEOUT=150,
  NVU_BUFFER_MAX_RETRIES=5, NVU_BUFFER_CALLERS=cc4101-primary,openclaw2,
  NVU_PEER_FB_SKIP_MODELS=glm5_2_nv,dsv4p_nv, NVU_MS_FALLBACK_MODELS=glm5_2_nv,
  NVU_CALLER_KEY_MAP=hermes:2;openclaw:3;opencode:4,
  NVU_BUFFER_TIMEOUT_STAIRS=90,90,90,90,90, NVU_BUFFER_TOTAL_DEADLINE_S=450,
  NVU_BUFFER_PING_INTERVAL_S=30
- cc4101: FALLBACK_UPSTREAM_URL=http://ms_gw:40007/v1/chat/completions,
  FALLBACK_UPSTREAM_MODEL=glm5_2_ms, PRIMARY_UPSTREAM_MODEL=dsv4p_nv,
  PRIMARY_UPSTREAM_URL=http://nv_gw:40006/v1/messages,
  CC4101_STREAM_TOTAL_DEADLINE_S=470, PRIMARY_HEADER_TIMEOUT=400,
  CC4101_PRIMARY_SKIP_S=30, CC4101_PRIMARY_FAIL_THRESHOLD=3,
  UPSTREAM_TIMEOUT=130, UPSTREAM_IDLE_TIMEOUT=150

## Fallback 配置实测
- nv_gw: NVU_DISABLE_MS_FALLBACK=0 (ms fallback 启用, 仅覆盖 glm5_2_nv)
- NVU_MS_FALLBACK_MODELS=glm5_2_nv (不含 dsv4p_nv)
- NVU_PEER_FB_SKIP_MODELS=glm5_2_nv,dsv4p_nv (dsv4p_nv 跳过 peer fallback)
- → dsv4p_nv 全挂时 nv_gw 裸返 429/502, cc4101 层 ms_gw(glm5_2_ms) 兜底
