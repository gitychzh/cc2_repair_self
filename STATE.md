# R638 — NOP 巡检轮 (2026-08-03 14:31 CST)

## 基线 (R638 实测, 06:00-06:31 UTC 窗口)
- cc2 (cc4101-primary) 30min: 0 req (session 间歇空闲, 无 cc2 评估样本, 同 R626-R637)
- dsv4p_nv 30min (hermes caller): 12 req, 7×200 + 4×429 + 1×502 (SR=58.3%)
  - vs R637 37.5% / R636 37.5% / R635 37.5% / R634 37.5% / R633 64.7% / R632 73.7% / R631 76.2% / R630 80.8% / R629 86.7% / R628 90.3%
    → **本轮回升 +20.8pp vs R634-R637 连续4轮 37.5%, 仍在 R617-R637 正常波动区间 37-91% 内, 趋势未恶化**
  - per-key: k2=7×200 全 first-attempt 命中 (06:05×3 + 06:30×4), 空 key=5×429+502
  - per-egress-IP: 203.10.96.139 主力 (单 IP, 同 R630-R637)
  - finish_reason: tool_calls×6 + stop×1 (健康, 无 zombie)
  - 200 avg_dur=10739ms (持平 R634-R637 量级 9634ms)
- 错误分类 1 类 (非新错误): `all_tiers_exhausted` ×5 (429×4 avg 1725ms 快速 ABORT + 502×1 avg 34830ms 慢)
  - R624-R637: 3→...→6→5→5→5→5, 本轮 5 持平 R634-R637, 仍在正常区间 3-6
- 30min nv_tier_attempts: 0 行 (hermes caller 不走 buffer, KeyManager 层 ABORT)
- cc_requests stream_total_deadline 6h: 0 (deadline 链健康)

## 6h dsv4p_nv SR 趋势 (小时桶, 实测)
- 23:00 52.2% → 00:00 42.1% → 01:00 29.4% → 02:00 59.1% → 03:00 56.5% → 04:00 86.8% → 05:00 76.3% → 06:00 53.8%(部分)
- 波动 29-87%, 模式不变: NVCF 账户级配额耗尽 (429 无 retry-after)
- 04:00 回升 86.8% (高时段配额刷新) → 配额型故障模式确认, 非 nv_gw 侧可改
- 本轮 06:00 回升到 53.8-58.3% (vs R637 06:00 37.5%) → 配额恢复中

## 本轮改动
- 无 (NOP). 根因不变: NVCF 账户级配额耗尽 (429 无 retry-after), 非 nv_gw 侧可改.

## 依据
- cc2 0 流量 → 铁律1 cc2 视角不满足 (同 R626-R637)
- dsv4p_nv SR=58.3% 回升 +20.8pp vs R634-R637 连续4轮 37.5%, 仍在正常波动区间内, 趋势未恶化
- 6h SR 29-87% 波动, 04:00 回升 86.8% → 配额型故障模式确认
- all_tiers_exhausted ×5 持平 R634-R637, 仍在正常区间 3-6, 无退化
- KeyManager 指数退避正确 (日志铁证: 14:20/14:25 429 count decay >300s → reset → 180s,
  全 key 429 触发 TIER_COOLDOWN 180s global)
- 30min nv_tier_attempts 0 行 = KeyManager 层 ABORT 非 buffer 路径
- stream_total_deadline 6h=0 → deadline 链健康
- 502×1 (06:31, 34830ms 慢) = NVCF 慢响应 (other=1 非 429 非 timeout), peer-fb skip
  (NVU_PEER_FB_SKIP_MODELS=dsv4p_nv) → 本地 502 返, cc4101 层 ms_gw(glm5_2_ms) 兜底
  → 设计正确, 非 nv_gw 故障
- 容器全稳, 配置无漂移, 无介入必要

## 验证
- 0 restart → 无需 py_compile / curl 复测
- 容器: nv_gw Up 24h (/health ok, 5 keys, nv_default_model=glm5_2_nv),
  cc4101 Up 14h, nv_gw_stable Up 37h, ms_gw Up 4d, logs_db Up 4d
- 配置无漂移 (env 全项匹配 R637 快照)
- stream_total_deadline 6h=0 (deadline 链铁证)
- KeyManager 日志铁证: 14:20/14:25 429 count decay + 指数退避正确,
  全 key 429 → TIER_COOLDOWN 180s global 正确触发

## 下一步
- dsv4p_nv SR 回升 58.3% (vs R634-R637 37.5%), 仍在正常波动区间内, 无恶化
- **升级标注解除** (R621: SR<55% 或 exhausted>=8 → 切 PRIMARY 回 glm5_2_nv):
  - 01:00 单小时 29.4% 触及, 但非持续 (04:00 回升 86.8%), cc2 视角 0 样本 → 不触发
- **持续观察点: dsv4p_nv 配额型 429 全挂** (24h+, 单 egress IP 主力, NVCF 无 retry-after)
  - 若未来 SR 持续 <55% (连续 3+ 小时) 或 exhausted>=8 → 评估切 PRIMARY 回 glm5_2_nv
  - 或评估多 egress IP 轮换 (单 IP 203.10.96.139 主力, 配额可能绑 IP)
- **建议维持: 联系 NVCF 侧评估 dsv4p_nv 配额扩容 / 提供 retry-after 头 / 慢响应根因**
- 继续 NOP 巡检, 等 cc2 流量恢复后观察 dsv4p_nv buffer 路径行为

## 参数快照 (R638 未改)
- nv_gw: NVU_DISABLE_MS_FALLBACK=0, UPSTREAM_TIMEOUT=90, TIER_COOLDOWN_S=180,
  KEY_COOLDOWN_S=30, NV_INTEGRATE_KEY_COOLDOWN_S=90, MIN_OUTBOUND_INTERVAL_S=10,
  NVU_FORCE_STREAM_UPGRADE=0, NVU_FORCE_STREAM_UPGRADE_TIMEOUT=150,
  NVU_BUFFER_MAX_RETRIES=5, NVU_BUFFER_CALLERS=cc4101-primary,openclaw2,
  NVU_PEER_FB_SKIP_MODELS=glm5_2_nv,dsv4p_nv, NVU_MS_FALLBACK_MODELS=glm5_2_nv,
  NVU_CALLER_KEY_MAP=hermes:2;openclaw:3;opencode:4,
  NVU_BUFFER_TIMEOUT_STAIRS=90,90,90,90,90, NVU_BUFFER_TOTAL_DEADLINE_S=450,
  NVU_BUFFER_PING_INTERVAL_S=30, TIER_TIMEOUT_BUDGET_S=180,
  NVU_KEYMGR_429_BASE_COOLDOWN=120, NVU_KEYMGR_429_MAX_COOLDOWN=600,
  NVU_KEYMGR_CONN_BASE_COOLDOWN=30, NVU_KEYMGR_CONN_FAIL_THRESHOLD=3,
  NVU_KEYMGR_CONN_LONG_COOLDOWN=120, NVU_KEYMGR_CONN_MAX_COOLDOWN=60
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
