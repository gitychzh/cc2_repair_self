# R647 — NOP 巡检轮 (2026-08-03 15:07 CST)

## 本轮改了什么 + 依据 + 验证
- **改动**: 无 (NOP). 根因不变: NVCF 账户级配额耗尽 (429 无 retry-after), 非 nv_gw 侧可改.
- **依据**: dsv4p_nv SR=84.6% (26req 22×200+2×429+2×502) -6.0pp vs R646 90.6%, 仍在 R617-R646 正常波动区间 (37-91%) 内, 6h 趋势回落非突变 (06:56 90.6%→本轮 84.6%), 无新错误模式. all_tiers_exhausted ×3 (+1 vs R646 的 ×2) 持平正常区间 3-6 下沿. NVStream_IncompleteRead ×1 — **连续 4 轮单发 (R644→R645→R646→R647), 阈值 >=3/30min 未触及 (1 例/30min), 但连续性从 3→4 轮, 持续观察点强化**. per-key k2=21×200+1×502 全 first-attempt 命中, 空 key=2×429+1×502. 单 egress IP 203.10.96.139 主力 22×95% SR, 空 IP=3×失败 = 配额型故障模式未变. 502×2 peer-fb skip (NVU_PEER_FB_SKIP_MODELS 含 dsv4p_nv) → 本地 502, cc4101 ms_gw 兜底, 设计正确非 nv_gw 故障. cc2 (cc4101-primary) 0 req (session 间歇空闲, 同 R626-R646, 铁律1 cc2 视角不满足).
- **验证**: 0 restart → 无需 py_compile / curl 复测. 容器 nv_gw Up 25h, cc4101 Up 14h, ms_gw Up 4d, logs_db Up 4d. /health ok: nv_num_keys=5, nvcf_pexec_models=[kimi_nv,dsv4p_nv,glm5_2_nv], nv_default_model=glm5_2_nv. 配置无漂移 (env 全项匹配 R646 快照, NVU_DISABLE_MS_FALLBACK=0/ms_gw fallback 已恢复). stream_total_deadline 6h=0.

## 基线 (R647 实测, 06:40-07:05 UTC 窗口, = 14:40-15:05 CST)
- cc2 (cc4101-primary) 30min: 0 req (session 间歇空闲, 无 cc2 评估样本, 同 R626-R646)
- dsv4p_nv 30min (hermes caller): 26 req, 22×200 + 2×429 + 2×502 (SR=84.6%)
  - vs R646 90.6% / R645 89.3% / R644 83.3% / R643 85.7% / R642 78.9% / R641 70.6% / R639 61.5% / R634-R637 连续 4 轮 37.5%
  - **-6.0pp vs R646 (90.6%), 仍在正常波动区间 (37-91%) 内, 6h 趋势回落非突变, 配额型故障模式未变**
  - per-key: k2=21×200 + 1×502 全 first-attempt 命中, 空 key=2×429 + 1×502
  - per-egress-IP: 203.10.96.139 主力 22×95% SR, 空 IP=3×失败, 134.195.101.194=1×200
  - finish_reason: tool_calls×19 + stop×3 (健康, 无 zombie)
  - 200 avg_dur=10325ms (max 26953, min 3876, avg_ttfb=10138), 略低于 R646 11334ms 量级
- 错误分类 2 类 (无新模式):
  - `all_tiers_exhausted` ×3 (avg 2737ms) — 429+502 NVCF 慢响应/配额, peer-fb skip → 本地 502, cc4101 ms_gw 兜底
    (R624→R646: 3→...→3→4→5→5→5→5→5→5→4→3→3→2→2, +1 回到 3, 持平正常区间 3-6 下沿, 趋势向好)
  - `NVStream_IncompleteRead` ×1 (avg 36755ms) — 502 路径不完整流读, NVCF 慢响应子类型
    **连续 4 轮单发 (R644→R645→R646→R647), 阈值 >=3/30min 未触及 (1 例/30min), 但连续性强化为持续观察点**
- 30min nv_tier_attempts: 0 行 (hermes caller 不走 buffer, KeyManager 层 ABORT)
- cc_requests stream_total_deadline 6h: 0 (deadline 链健康, 铁证)

## 6h dsv4p_nv SR 趋势
- 23:00 52.2% → 00:00 42.1% → 01:00 29.4% → 02:00 59.1% → 03:00 56.5% → 04:00 86.8% → 05:00 76.3% → 06:00 53.8% → 06:56 R645 89.3% → 07:01 R646 90.6% → 07:05 本轮 84.6%
- 波动 29-91%, 本轮 84.6% 为 6h 上沿回落, 配额型故障模式未变 (NVCF 账户级配额耗尽, 429 无 retry-after, 全 5key 429 → TIER_COOLDOWN 180s)

## 下一步
- dsv4p_nv SR 84.6% (-6.0pp vs R646, 6h 上沿回落), 仍在正常波动区间内, 趋势向好, 无突变恶化
- **升级标注解除** (R621: SR<55% 或 exhausted>=8 → 切 PRIMARY 回 glm5_2_nv):
  - 01:00 单小时触及 29.4%, 但非持续 (04:00 86.8%, 06:56 89.3%, 07:01 90.6%, 07:05 84.6%), cc2 视角 0 样本 → 不触发
- **持续观察点**:
  1. **dsv4p_nv 配额型 429 全挂** (24h+ 持续, 单 egress IP 主力, NVCF 无 retry-after 头)
     - 若未来 SR 持续 <55% (连续 3+ 小时) 或 exhausted>=8 → 评估切 PRIMARY 回 glm5_2_nv
     - 或评估多 egress IP 轮换 (当前单 IP 203.10.96.139 主力 22/26=85%, 配额可能绑 IP)
  2. **NVStream_IncompleteRead 连续性演变** (R644→R645→R646→R647 连续 4 轮 1 例/30min)
     - 当前阈值 >=3/30min 未触及, 但连续 4 轮单发 = 子类型稳定存在非偶发
     - 若升级为 >=3/30min 或 avg_dur 持续 >36s → 评估 NVCF 慢响应根因 / buffer 不完整流读处理
- **建议维持: 联系 NVCF 侧评估 dsv4p_nv 账户配额扩容 / 提供 retry-after 头 / 慢响应根因**
- 继续 NOP 巡检, 等 cc2 流量恢复后观察 dsv4p_nv buffer 路径行为

## 参数快照 (R647 未改)
- nv_gw: NVU_DISABLE_MS_FALLBACK=0, UPSTREAM_TIMEOUT=90, TIER_COOLDOWN_S=180,
  KEY_COOLDOWN_S=30, NV_INTEGRATE_KEY_COOLDOWN_S=90, MIN_OUTBOUND_INTERVAL_S=10,
  NVU_FORCE_STREAM_UPGRADE=0, NVU_FORCE_STREAM_UPGRADE_TIMEOUT=150,
  NVU_BUFFER_MAX_RETRIES=5, NVU_BUFFER_CALLERS=cc4101-primary,openclaw2,
  NVU_PEER_FB_SKIP_MODELS=glm5_2_nv,dsv4p_nv, NVU_MS_FALLBACK_MODELS=glm5_2_nv,
  NVU_TIER_BUDGET_GLM5_2_NV=120, TIER_TIMEOUT_BUDGET_S=180
- cc4101: FALLBACK_UPSTREAM_URL=http://ms_gw:40007/v1/chat/completions,
  CC4101_STREAM_TOTAL_DEADLINE_S=470, PRIMARY_HEADER_TIMEOUT=400,
  CC4101_PRIMARY_SKIP_S=30, CC4101_PRIMARY_FAIL_THRESHOLD=3,
  PRIMARY_UPSTREAM_MODEL=dsv4p_nv, PRIMARY_UPSTREAM_URL=http://nv_gw:40006/v1/messages,
  FALLBACK_UPSTREAM_MODEL=glm5_2_ms, UPSTREAM_TIMEOUT=130, UPSTREAM_IDLE_TIMEOUT=150
- 链路: cc2(cc4101:4101) → nv_gw(40006, dsv4p_nv) → 5key(k0-k4)×5 US IP(hysteria2) → NVCF
- deadline 链: UPSTREAM_TIMEOUT=90s < NVU_TIER_BUDGET=120-180s < buffer 90s×5=450s < cc4101 470s < SDK 500s idle
