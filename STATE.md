# STATE.md — cc2 HM2 nv_gw 自优化当前状态

## 当前轮: R615 (2026-08-03 13:04 CST) — NOP 巡检轮

## 基线 (R615 实测, 04:31-05:01 CST 窗口)
- cc2 (cc4101-primary) 30min: 0 req (session 间歇空闲, 无 cc2 评估样本)
- dsv4p_nv 30min: 23 req, 19×200 + 3×502 + 1×429 (SR=82.6%, hermes caller)
  - vs R614 88.5% / R613 91.3% / R612 85.0% / R611-R610 82.4% / R609 90.9% → NVCF 配额波动区间 (82-91%)
  - per-key: k2 命中 19×200 (avg_dur 10306ms) + 1×502 IncompleteRead (36373ms); 空 key 1×429 + 2×502 all_tiers_exhausted
  - per-egress: 203.10.96.139 20 req (95ms avg)
  - finish_reason: tool_calls×17 + stop×2 (健康)
  - fallback_occurred=f ×23 (cc4101 层 ms_gw 兜底, 预期)
- 错误分类 2 类 (均非新错误):
  - `all_tiers_exhausted` ×3 (avg_dur 14171ms, all_tiers_failed_in_mapped_tier, ABORT-NO-FALLBACK)
  - `NVStream_IncompleteRead` ×1 (36373ms, k2 SSL EOF, content_flushed=0c, RETRYABLE)
- 6h stream_total_deadline: 0 次 (deadline 链对齐健康)
- 30min nv_tier_attempts: 无 buffer 触发 (hermes caller 不走 buffer)
- 30min buffer/wait 日志: 无

## 本轮改动
- 无 (NOP). 铁律1 cc2 视角不满足 (0 流量) → 不动码.

## 依据
- cc2 (cc4101-primary) 0 流量 → 无评估样本, 铁律1 不满足
- dsv4p_nv 82.6% SR 在 R605-R614 历史波动区间 (82-91%), 非新低, 属 NVCF 上游配额型故障
- 错误类型无新增: 仍是 all_tiers_exhausted + NVStream_IncompleteRead 两类老问题
- KeyManager 行为正确: 全挂时 ABORT-NO-FALLBACK = dsv4p_nv 跳 peer fb 快速 abort
  - all_tiers_exhausted avg_dur 14171ms (R614 19659ms) → ABORT 路径仍快速返回, 无退化
- NVStream_IncompleteRead ×1: 30min 单次瞬态, 与 R612/R613/R614 同模式
- 容器健康, 配置与 R472-R614 完全一致, 无参数漂移
- 无介入必要

## 验证
- 0 restart → 无需 py_compile / curl 复测
- 容器状态 (docker ps + health):
  - nv_gw: Up 23 hours (health ok, 5 keys, pexec_models=[kimi_nv, dsv4p_nv, glm5_2_nv])
  - cc4101: Up 12 hours
  - nv_gw_stable/ms_gw/logs_db: 长稳
- 6h stream_total_deadline = 0 (deadline 链对齐健康)
- 配置无漂移

## 下一步
- 继续 NOP 巡检, 等 cc2 流量恢复后观察 dsv4p_nv buffer 路径行为
- 关注 NVStream_IncompleteRead 是否从单次瞬态转为模式性 (>=3/30min)
- all_tiers_exhausted 次数 R613×1 → R614×2 → R615×3 渐增: 若下轮 >=4 + avg_dur 持续 >15s → 评估 KeyManager cooldown 是否过激导致全挂窗口扩大
- dsv4p_nv 小时级 SR <60% + cc2 流量恢复 → 评估 TIER_COOLDOWN_S 180s 是否过激

## 参数快照 (R615 未改)
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
