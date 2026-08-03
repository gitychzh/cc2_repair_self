# R625 — NOP 巡检轮 (2026-08-03 13:40 CST)

## 基线 (R625 实测, 05:11-05:40 UTC 窗口)
- cc2 (cc4101-primary) 30min: 0 req (session 间歇空闲, 无 cc2 评估样本)
- dsv4p_nv 30min (hermes caller): 20 req, 17×200 + 3×429 (SR=85.0%)
  - vs R624 82.4% / R623 76.5% / R622 64.3% / R621 57.1% / R620 62.5%
    → **连续 4 轮反弹 (57.1→64.3→76.5→82.4→85.0), 趋势已反转, 接近 R618 波动区间上沿**
  - per-key: k2 17×200; 空 key 3×429
  - per-egress: 203.10.96.139 17 req (100%) + 空 3 req (0%)
  - finish_reason: tool_calls×14 + stop×3 (健康, 无 zombie)
  - fallback_occurred=f ×20 (cc4101 层 ms_gw 兜底, 预期)
- 错误分类 1 类 (非新错误):
  - `all_tiers_exhausted` ×3 (avg_dur 1540ms, all_tiers_failed_in_mapped_tier, ABORT-NO-FALLBACK)
    → **all_tiers_exhausted R621×6 → R622×5 → R623×4 → R624×3 → R625×3 持平, 与 SR 反弹同步**
- 30min nv_tier_attempts: 0 行 (hermes caller 不走 buffer, 全挂 KeyManager 层 ABORT)
- cc_requests stream_total_deadline 6h: 0 (deadline 链健康, 0 触发)

## 根因分析 (与 R624 一致)
按分钟趋势: 05:11/05:16/05:21 各 1×429 → 05:26-05:36 一波 17×200 (k2 first attempt)。
NVCF 配额周期性间歇 (5min 周期), 非永久挂; 全挂后 k2 自动恢复连续命中。
NVCF 响应头 `ratelimit/retry-after=(none)` — 未给恢复提示, KeyManager 只能盲退避 180s。
→ NVCF 账户级配额耗尽 (5key 同账户同配额池, 同时 429), 非单个 key/IP 问题。
→ nv_gw 侧行为正确: 5key 全挂 → ABORT-NO-FALLBACK → cc4101 fallback ms_gw(glm5_2_ms)。
→ 改 KeyManager cooldown 会更糟: 缩短冷却会在 NVCF 仍配额耗尽时再撞 429。

## 本轮改动
- 无 (NOP). 根因是 NVCF 上游配额型故障, 非 nv_gw 侧可改.

## 依据
- cc2 0 流量 → 无评估样本, 铁律1 cc2 视角不满足
- dsv4p_nv SR=85.0% 连续 4 轮反弹, all_tiers_exhausted 持平 R624 (3→3)
  → 证实 R621 "周期性配额耗尽 + 采样窗口偏移" 判断正确, 趋势持续反转
- all_tiers_exhausted 全部 nv_key_idx 空 + tier_attempts 0 行 → KeyManager 层 ABORT
- 日志铁证 GLOBAL-COOLDOWN + retry-after 缺失 = NVCF 账户级配额耗尽, nv_gw 无法改码解决
- KeyManager 指数退避正确, ABORT avg 1540ms 与 R624 持平, 无退化
- cc_requests stream_total_deadline 6h=0 → deadline 链 (90s×5=450s < 470s cc4101 < 500s SDK) 健康
- 容器健康, 配置无漂移
- 无介入必要

## 验证
- 0 restart → 无需 py_compile / curl 复测
- 容器状态: nv_gw Up 23h (health ok, 5 keys), cc4101 Up 13h, ms_gw/logs_db/nv_gw_stable 长稳
- 配置无漂移 (env 全项匹配 R624 快照)

## 下一步
- dsv4p_nv SR 从 R621 低点 57.1% 连续 4 轮反弹至 85.0%, 趋势已反转, 接近正常波动区间
- **升级标注解除** (R621 设定 SR<55% 或 exhausted>=8 → 切 PRIMARY 回 glm5_2_nv): 持续未触发
- **建议维持: 联系 NVCF 侧评估 dsv4p_nv 账户配额扩容 / 提供 retry-after 头**
- 继续 NOP 巡检, 等 cc2 流量恢复后观察 dsv4p_nv buffer 路径行为

## 参数快照 (R625 未改)
- nv_gw: NVU_DISABLE_MS_FALLBACK=0, UPSTREAM_TIMEOUT=90, TIER_COOLDOWN_S=180,
  KEY_COOLDOWN_S=30, NV_INTEGRATE_KEY_COOLDOWN_S=90, MIN_OUTBOUND_INTERVAL_S=10,
  NVU_FORCE_STREAM_UPGRADE=0, NVU_FORCE_STREAM_UPGRADE_TIMEOUT=150,
  NVU_BUFFER_MAX_RETRIES=5, NVU_BUFFER_CALLERS=cc4101-primary,openclaw2,
  NVU_PEER_FB_SKIP_MODELS=glm5_2_nv,dsv4p_nv, NVU_MS_FALLBACK_MODELS=glm5_2_nv,
  NVU_CALLER_KEY_MAP=hermes:2;openclaw:3;opencode:4,
  NVU_BUFFER_TIMEOUT_STAIRS=90,90,90,90,90, NVU_BUFFER_TOTAL_DEADLINE_S=450,
  NVU_BUFFER_PING_INTERVAL_S=30, TIER_TIMEOUT_BUDGET_S=180
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
