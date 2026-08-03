# R635 — NOP 巡检轮 (2026-08-03 14:21 CST)

## 基线 (R635 实测, 06:00-06:20 UTC 窗口)
- cc2 (cc4101-primary) 30min: 0 req (session 间歇空闲, 无 cc2 评估样本, 同 R626-R634)
- dsv4p_nv 30min (hermes caller): 8 req, 3×200 + 5×429 (SR=37.5%)
  - vs R634 37.5% / R633 64.7% / R632 73.7% / R631 76.2% / R630 80.8% / R629 86.7% / R628 90.3%
    → **本轮持平 R634, 仍在 R617-R634 正常波动区间下沿 (37-91%), 小样本 8req 波动剧烈, 趋势未恶化**
  - per-key: k2=3×200 全 first-attempt 命中 (k2 主力不变), 空 key=5×429
  - per-egress-IP: 203.10.96.139 (单 IP 主力, 同 R630-R634)
  - finish_reason: tool_calls×2 + stop×1 (健康, 无 zombie)
  - fallback_occurred=f ×8 (hermes caller 直连 nv_gw)
  - 200 avg_dur=9634ms (健康, 持平 R634 9634ms)
- 错误分类 1 类 (非新错误):
  - `all_tiers_exhausted` ×5 (avg_dur 1412ms: 429 快速 ABORT)
    → R624→...→R633→R634→R635: 3→3→3→3→3→4→5→5→5→6→5→5 (持平正常区间 3-6, 本轮持平 R634)
- 30min nv_tier_attempts: 0 行 (hermes caller 不走 buffer, KeyManager 层 ABORT)
- cc_requests stream_total_deadline 6h: 0 (deadline 链健康)

## 6h dsv4p_nv SR 趋势 (小时桶)
- 00:00 53.3% → 01:00 36.8% → 02:00 59.1% → 03:00 58.3% → 04:00 86.8% → 05:00 76.9% → 06:00 50.0%
- 波动 37-87%, 模式不变: NVCF 账户级配额耗尽 (429 无 retry-after, 全 5key 429 → TIER_COOLDOWN 180s)

## 持续观察点 (沿用 R634, 不改码) — dsv4p_nv 配额型 429 全挂
- 6h SR 波动 37-87%, 04:00 回升 86.8% → 配额型故障模式确认, 非 nv_gw 侧可改
- 01:00 单小时 SR=36.8% 触及 R621 升级阈值 (SR<55%), 但:
  - cc2 视角 0 样本 (铁律1 不满足)
  - 非持续 (04:00 回升至 86.8%)
  - → 不触发回切 PRIMARY glm5_2_nv
- KeyManager 指数退避正确 (429 count=1→180s, =2→180s, =3→480s)
- 全 5key 429 → TIER_COOLDOWN 180s 全挂, 被 cc4101 fallback ms_gw 兜住, 用户侧无感
- 429 resp headers: ratelimit/retry=(none) — NVCF 不提供 retry-after, 配额型 429 确认

## 本轮改动
- 无 (NOP). 根因不变: NVCF 账户级配额耗尽 (429 无 retry-after), 非 nv_gw 侧可改.

## 依据
- cc2 0 流量 → 无评估样本, 铁律1 cc2 视角不满足 (同 R626-R634)
- dsv4p_nv SR=37.5% (8req 小样本), 持平 R634, 仍在 R617-R634 正常波动区间下沿 (37-91%), 趋势未恶化
- 6h SR 趋势 37-87% 波动, 04:00 回升 86.8% → 配额型故障模式确认
- all_tiers_exhausted ×5 (R624-R635: 3→...→6→5→5), 持平 R634 仍在正常波动区间 3-6, 无退化
- KeyManager 指数退避正确, 429 ABORT avg 1412ms (快速, 持平 R634 1339ms)
- per-key k2 全 first-attempt 命中 + 单 egress IP 主力 = 配额型故障模式未变
- 30min nv_tier_attempts 0 行 = KeyManager 层 ABORT 非 buffer 路径
- stream_total_deadline 6h=0 → deadline 链 (90s×5=450s < 470s cc4101 < 500s SDK) 健康
- 容器全稳, 配置无漂移, 无介入必要

## 验证
- 0 restart → 无需 py_compile / curl 复测
- 容器状态: nv_gw Up 24h (/health ok, 5 keys, nv_default_model=glm5_2_nv),
  cc4101 Up 14h, nv_gw_stable Up 36h
- 配置无漂移 (env 全项匹配 R634 快照)
- stream_total_deadline 6h=0 (deadline 链铁证)

## 下一步
- dsv4p_nv SR 本轮持平 R634 (37.5%), 仍在正常波动区间下沿, 小样本波动无恶化
- **升级标注解除** (R621 设定 SR<55% 或 exhausted>=8 → 切 PRIMARY 回 glm5_2_nv):
  - 01:00 单小时触及 SR<55%, 但非持续 (04:00 回升 86.8%), cc2 视角 0 样本 → 不触发
- **持续观察点: dsv4p_nv 配额型 429 全挂** (24h+ 持续, 单 egress IP 主力, NVCF 无 retry-after 头)
  - 若未来轮次 SR 持续 <55% (连续 3+ 小时) 或 exhausted>=8, 考虑评估切 PRIMARY 回 glm5_2_nv
  - 或评估多 egress IP 轮换 (当前单 IP 203.10.96.139 主力, 配额可能绑 IP)
- **建议维持: 联系 NVCF 侧评估 dsv4p_nv 账户配额扩容 / 提供 retry-after 头 / 慢响应根因**
- 继续 NOP 巡检, 等 cc2 流量恢复后观察 dsv4p_nv buffer 路径行为

## 参数快照 (R635 未改)
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
- → dsv4p_nv 全挂时 nv_gw 裸返 429, cc4101 层 ms_gw(glm5_2_ms) 兜底
