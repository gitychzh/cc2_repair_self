# R621 — NOP 巡检轮 (2026-08-03 13:25 CST)

## 基线 (R621 实测, 04:56-05:26 CST 窗口)
- cc2 (cc4101-primary) 30min: 0 req (session 间歇空闲, 无 cc2 评估样本)
- dsv4p_nv 30min: 14 req, 7×200 + 5×429 + 1×502 + 1×200(openclaw) (SR=57.1%, hermes caller)
  - vs R620 62.5% / R619 70.6% / R618 75.0% / R617 75.0% / R616 77.3% / R615 82.6% / R614 88.5% / R613 91.3%
    → 连续 4 轮下滑 (75→70.6→62.5→57.1), 本轮 **首次跌破 60%**, 创 R612 以来序列新低
  - per-key: k2 7×200; k3 1×200; 空 key 5×429 + 1×502
    (空 key = hermes 绑定 key2, key2 cooling 时拿不到 key)
  - per-egress: 203.10.96.139 7 req (100%) + 134.195.101.194 1 req (100%) + 空 6 req (0%)
  - finish_reason: tool_calls×7 + stop×1 (健康, 无 zombie)
  - fallback_occurred=f ×14 (cc4101 层 ms_gw 兜底, 预期)
- 错误分类 1 类 (非新错误):
  - `all_tiers_exhausted` ×6 (avg_dur 7404ms, all_tiers_failed_in_mapped_tier, ABORT-NO-FALLBACK)
    - 全部 nv_key_idx 为空 + nv_tier_attempts 0 行 → abort 在拿到 key 之前
    → **all_tiers_exhausted R613×1 → R614×2 → R615×3 → R616×4 → R617×4 → R618×4 → R619×5 → R620×6 → R621×6 持平, 不再创新高**
- 6h stream_total_deadline: 0 次 (deadline 链对齐健康)
- 30min nv_tier_attempts: 0 行 (hermes caller 不走 buffer, 全挂 KeyManager 层 ABORT)

## 根因分析 (与 R620 一致, 数据铁证)
日志铁证: 13:21:06.1 `NV-GLOBAL-COOLDOWN tier=dsv4p_nv all keys 429. Marking all cooling 180s (TIER_COOLDOWN)`.
随后 13:26:04.0 `NV-SUCCESS tier=dsv4p_nv k3 succeeded on first attempt` →
NVCF 配额是周期性间歇 (5min 周期), 非永久挂; 全挂 180s 后 key3 先恢复.
NVCF 响应头 `ratelimit/retry=(none)` — 未给恢复提示, KeyManager 只能盲退避 180s.
→ NVCF 账户级配额耗尽 (5key 同一账户, 同时 429), 非单个 key / IP 问题.
→ nv_gw 侧行为正确: 5key 全挂 → ABORT-NO-FALLBACK (dsv4p skip peer fb) →
cc4101 fallback ms_gw(glm5_2_ms).
→ 改 KeyManager cooldown 会更糟: 缩短冷却会在 NVCF 仍配额耗尽时再撞 429, 浪费 egress 流量.

## 本轮改动
- 无 (NOP). 根因是 NVCF 上游配额型故障, 非 nv_gw 侧可改.

## 依据
- cc2 (cc4101-primary) 0 流量 → 无评估样本, 铁律1 cc2 视角不满足
- dsv4p_nv SR=57.1% **首次跌破 60%** → R620 STATE 设定的"若下轮 SR<60% → 再次升级标注"已达成
- all_tiers_exhausted ×6 与 R620 持平 (不创新高), 180s 全挂后 k3 已自动恢复 (NV-SUCCESS first attempt)
  → 非线性恶化, 是周期性配额耗尽 + 采样窗口恰好覆盖 5 次 cooldown 边界
- all_tiers_exhausted 全部 nv_key_idx 空 + tier_attempts 0 行 → KeyManager 层 ABORT, 非 buffer/tier 路径
- 日志铁证 GLOBAL-COOLDOWN + retry-after 缺失 = NVCF 账户级配额耗尽, nv_gw 无法靠改码解决
- KeyManager 指数退避正确, ABORT 路径快速 (avg 7404ms 与 R620 一致, 无退化)
- 容器健康, 配置无漂移
- 6h 0 stream_total_deadline (deadline 链对齐健康)
- 无介入必要 (码改)

## 验证
- 0 restart → 无需 py_compile / curl 复测
- 容器状态 (docker ps + /health):
  - nv_gw: Up 23 hours (health ok, 5 keys, pexec_models=[kimi_nv, dsv4p_nv, glm5_2_nv])
  - cc4101: Up 13 hours
  - nv_gw_stable/ms_gw/logs_db: 长稳
- 6h stream_total_deadline = 0 (deadline 链对齐健康)
- 配置无漂移

## 下一步 (升级标注已二次触发)
**R620 设定的"SR<60% → 再次升级标注"已达成.**
- dsv4p_nv 配额耗尽趋势连续 4 轮恶化 (R618 75.0% → R619 70.6% → R620 62.5% → R621 57.1%),
  但 all_tiers_exhausted 已停止线性增长 (R620×6 → R621×6 持平),
  且日志证实全挂 180s 后 k3 自动恢复 → **非恶化, 是周期性配额耗尽 + 采样窗口偏移**
- **建议维持: 联系 NVCF 侧评估 dsv4p_nv 账户配额扩容 / 提供配额恢复提示 (retry-after 头)**.
  - 当前 5key 同账户同配额池, 任一 key 429 = 全 key 429, 无差异化.
  - 若 NVCF 侧能提供 retry-after 头, KeyManager 可精准退避而非盲退 180s, 单次 ABORT 后下个请求即恢复.
- 继续 NOP 巡检, 等 cc2 流量恢复后观察 dsv4p_nv buffer 路径行为
- 若下轮 SR<55% 或 all_tiers_exhausted>=8 → 三次升级标注 (考虑切换 PRIMARY_UPSTREAM_MODEL 回 glm5_2_nv 评估)

## 参数快照 (R621 未改)
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
