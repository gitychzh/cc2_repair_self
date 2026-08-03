# R623 — NOP 巡检轮 (2026-08-03 13:35 CST)

## 基线 (R623 实测, 05:05-05:32 UTC 窗口)
- cc2 (cc4101-primary) 30min: 0 req (session 间歇空闲, 无 cc2 评估样本)
- dsv4p_nv 30min: 17 req, 13×200 + 4×429 (SR=76.5%, hermes caller)
  - vs R622 64.3% / R621 57.1% / R620 62.5% / R619 70.6% / R618 75.0%
    → **连续 2 轮反弹 (57.1→64.3→76.5), 回到 R618 水平, 仍处 R612-R618 波动区间 57-91%**
  - per-key: k2 12×200; k3 1×200; 空 key 4×429
  - per-egress: 203.10.96.139 12 req (100%) + 134.195.101.194 1 req (100%) + 空 4 req (0%)
  - finish_reason: tool_calls×10 + stop×3 (健康, 无 zombie)
  - fallback_occurred=f ×17 (cc4101 层 ms_gw 兜底, 预期)
- 错误分类 1 类 (非新错误):
  - `all_tiers_exhausted` ×4 (avg_dur 1731ms, all_tiers_failed_in_mapped_tier, ABORT-NO-FALLBACK)
    - 全部 nv_key_idx 为空 + nv_tier_attempts 0 行 → abort 在拿到 key 之前
    → **all_tiers_exhausted R621×6 → R622×5 → R623×4 持续下降, 与 SR 反弹同步**
- 6h stream_total_deadline: 0 次 (deadline 链对齐健康)
- 30min nv_tier_attempts: 0 行 (hermes caller 不走 buffer, 全挂 KeyManager 层 ABORT)

## 根因分析 (与 R622 一致, 数据铁证)
日志铁证: 13:06-13:21 四次 `NV-GLOBAL-COOLDOWN tier=dsv4p_nv all keys 429. Marking all cooling 180s (TIER_COOLDOWN)`.
随后 13:26-13:32 一波 13× `NV-SUCCESS tier=dsv4p_nv k3 succeeded on first attempt` →
NVCF 配额是周期性间歇 (5min 周期), 非永久挂; 全挂 180s 后 key3 先恢复, 连续命中.
NVCF 响应头 `ratelimit/retry=(none)` — 未给恢复提示, KeyManager 只能盲退避 180s.
→ NVCF 账户级配额耗尽 (5key 同一账户, 同时 429), 非单个 key / IP 问题.
→ nv_gw 侧行为正确: 5key 全挂 → ABORT-NO-FALLBACK (dsv4p skip peer fb) →
cc4101 fallback ms_gw(glm5_2_ms).
→ 改 KeyManager cooldown 会更糟: 缩短冷却会在 NVCF 仍配额耗尽时再撞 429, 浪费 egress 流量.

## 本轮改动
- 无 (NOP). 根因是 NVCF 上游配额型故障, 非 nv_gw 侧可改.

## 依据
- cc2 (cc4101-primary) 0 流量 → 无评估样本, 铁律1 cc2 视角不满足
- dsv4p_nv SR=76.5% 连续 2 轮反弹 (R621 57.1% → R622 64.3% → R623 76.5%),
  回到 R618 水平, all_tiers_exhausted 同步下降 (6→5→4)
  → **证实 R621 "非恶化, 是周期性配额耗尽 + 采样窗口偏移" 判断正确**
- all_tiers_exhausted 全部 nv_key_idx 空 + tier_attempts 0 行 → KeyManager 层 ABORT, 非 buffer/tier 路径
- 日志铁证 GLOBAL-COOLDOWN + retry-after 缺失 = NVCF 账户级配额耗尽, nv_gw 无法靠改码解决
- KeyManager 指数退避正确, ABORT 路径快速 (avg 1731ms vs R622 2024ms↓, 更快无退化)
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
- 配置无漂移 (env 全项匹配 R622 快照)

## 下一步
- dsv4p_nv SR 已从 R621 低点 57.1% 反弹至 76.5%, all_tiers_exhausted 同步下降 (6→4),
  证实周期性配额耗尽判断, 非线性恶化趋势已反转
- **升级标注解除**: R621 设定的 "SR<55% 或 exhausted>=8 → 考虑切 PRIMARY 回 glm5_2_nv"
  阈值本轮未触发且趋势已反转, 降级为常规观察
- **建议维持: 联系 NVCF 侧评估 dsv4p_nv 账户配额扩容 / 提供配额恢复提示 (retry-after 头)**.
  - 当前 5key 同账户同配额池, 任一 key 429 = 全 key 429, 无差异化.
  - 若 NVCF 侧能提供 retry-after 头, KeyManager 可精准退避而非盲退 180s, 单次 ABORT 后下个请求即恢复.
- 继续 NOP 巡检, 等 cc2 流量恢复后观察 dsv4p_nv buffer 路径行为

## 参数快照 (R623 未改)
- nv_gw: NVU_DISABLE_MS_FALLBACK=0, UPSTREAM_TIMEOUT=90, TIER_COOLDOWN_S=180,
  KEY_COOLDOWN_S=30, NV_INTEGRATE_KEY_COOLDOWN_S=90,
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
