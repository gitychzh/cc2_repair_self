# R617 — NOP 巡检轮 (2026-08-03 13:11 CST)

## 基线 (R617 实测, 04:36-05:06 CST 窗口)
- cc2 (cc4101-primary) 30min: 0 req (session 间歇空闲, 无 cc2 评估样本)
- dsv4p_nv 30min: 20 req, 15×200 + 3×502 + 2×429 (SR=75.0%, hermes caller)
  - vs R616 77.3% / R615 82.6% / R614 88.5% / R613 91.3% / R612 85.0%
    → NVCF 配额波动区间 (75-91%), 趋势性下滑仍在区间内
  - per-key: k2 命中 14×200 + 1×502 IncompleteRead (36373ms); k3 1×200; 空 key 2×429 + 2×502
  - per-egress: 203.10.96.139 15 req (93ms avg) + 134.195.101.194 1 req + 空 4 req
  - finish_reason: tool_calls×13 + stop×2 (健康)
  - fallback_occurred=f ×20 (cc4101 层 ms_gw 兜底, 预期)
- 错误分类 2 类 (均非新错误):
  - `all_tiers_exhausted` ×4 (avg_dur 11204ms, all_tiers_failed_in_mapped_tier, ABORT-NO-FALLBACK)
    - 全部 nv_key_idx 为空 + nv_tier_attempts 0 行 → abort 在拿到 key 之前
      (NVU_CALLER_KEY_MAP=hermes:2 绑定 key2, key2 cooling 时 hermes 拿不到 key)
  - `NVStream_IncompleteRead` ×1 (36373ms, k2 SSL EOF, RETRYABLE)
- 6h stream_total_deadline: 0 次 (deadline 链对齐健康)
- 30min nv_tier_attempts: 0 行 (hermes caller 不走 buffer, 全挂 KeyManager 层 ABORT)

## 根因分析 (与 R616 一致)
日志铁证: 12:41 / 13:01 / 13:06 / 13:11 四次 `NV-GLOBAL-COOLDOWN tier=dsv4p_nv all keys 429,
Marking all cooling 180s`. 5key 同账户连环 429, NVCF 响应头 `ratelimit/retry=(none)` —
未给恢复提示, KeyManager 只能盲退避.
→ NVCF 账户级配额耗尽 (5key 同一账户, 同时 429), 非单个 key / IP 问题.
→ nv_gw 侧行为正确: 5key 全挂 → ABORT-NO-FALLBACK (dsv4p skip peer fb) →
cc4101 fallback ms_gw(glm5_2_ms).
→ 改 KeyManager cooldown 会更糟: 缩短冷却会在 NVCF 仍配额耗尽时再撞 429, 浪费 egress 流量.

## 本轮改动
- 无 (NOP). 根因是 NVCF 上游配额型故障, 非 nv_gw 侧可改.

## 依据
- cc2 (cc4101-primary) 0 流量 → 无评估样本, 铁律1 cc2 视角不满足
- dsv4p_nv 75.0% SR 在 R612-R616 历史波动区间 (75-91%), 非新低, 属 NVCF 账户配额波动
- all_tiers_exhausted 全部 nv_key_idx 空 + tier_attempts 0 行 → KeyManager 层 ABORT, 非 buffer/tier 路径
- 日志铁证 4 次 GLOBAL-COOLDOWN + retry-after 缺失 = NVCF 账户级配额耗尽, nv_gw 无法靠改码解决
- KeyManager 指数退避正确, ABORT 路径快速 (2-5s), 无退化
- NVStream_IncompleteRead ×1: 30min 单次瞬态, 与 R612-R616 同模式
- 容器健康, 配置无漂移
- 无介入必要

## 验证
- 0 restart → 无需 py_compile / curl 复测
- 容器状态 (docker ps + /health):
  - nv_gw: Up 23 hours (health ok, 5 keys, pexec_models=[kimi_nv, dsv4p_nv, glm5_2_nv])
  - cc4101: Up 12 hours
  - nv_gw_stable/ms_gw/logs_db: 长稳
- 6h stream_total_deadline = 0 (deadline 链对齐健康)
- 配置无漂移

## 下一步
- 继续 NOP 巡检, 等 cc2 流量恢复后观察 dsv4p_nv buffer 路径行为
- 关注 NVStream_IncompleteRead 是否从单次瞬态转为模式性 (>=3/30min)
- all_tiers_exhausted 次数 R613×1 → R614×2 → R615×3 → R616×4 → R617×4 持平:
  若下轮 >=5 + 全挂窗口持续 → 评估是否 NVCF 账户配额持续收紧 (非 nv_gw 可控)
- dsv4p_nv 小时级 SR <60% + cc2 流量恢复 → 评估是否需联系 NVCF 侧扩容配额 (非码改)

## 参数快照 (R617 未改)
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
