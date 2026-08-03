# R644 — NOP 巡检轮 (2026-08-03 14:54 CST)

## 基线 (R644 实测, 06:25-06:50 UTC 窗口)
- cc2 (cc4101-primary) 30min: 0 req (session 间歇空闲, 无 cc2 评估样本, 同 R626-R643)
- dsv4p_nv 30min (hermes caller): 24 req, 20×200 + 1×429 + 3×502 (SR=83.3%)
  - vs R643 85.7% / R642 78.9% / R641 70.6% / R639 61.5% / R634-R637 连续 4 轮 37.5%
    → **本轮 -2.4pp vs R643 (85.7%), 仍在 R617-R643 正常波动区间 (37-91%) 内, 无突变恶化**
    → 6h 趋势: 29-87% 波动, 04:00 回升 86.8%, 06:50 本轮 83.3%, 配额型故障模式未变
  - per-key: k2=20×200 全 first-attempt 命中, 空 key=1×429+2×502
  - per-egress-IP: 203.10.96.139 主力 21×全命中, 空 IP=3×失败
  - finish_reason: tool_calls×18 + stop×2 (健康, 无 zombie)
  - 200 avg_dur=11312ms (max 34819, min 3654, avg_ttfb=10958), 持平 R643 11485ms 量级
- 错误分类 2 类 (无新模式):
  - `all_tiers_exhausted` ×3 (avg_dur 14470ms)
    - 含 429×1 快速 ABORT (avg 2718ms) + 502×2 avg 20346ms 慢响应 (NVCF 慢, peer-fb skip)
    → R624→...→R634-R643: 3→...→3→4→5→5→5→5→5→5→4→3→3 (持平正常区间 3-6, 持平 R643, 趋势向好)
  - `NVStream_IncompleteRead` ×1 (avg_dur 36755ms)
    → 502 路径里的不完整流读, NVCF 慢响应/连接中断子类型, **1 例单发, 不构成新模式**
    → 36755ms 已超单次 90s UPSTREAM_TIMEOUT 边界, 属于 stream 途中的不完整读
- 30min nv_tier_attempts: 0 行 (hermes caller 不走 buffer, KeyManager 层 ABORT)
- cc_requests stream_total_deadline 6h: 0 (deadline 链健康, 铁证)

## 6h dsv4p_nv SR 趋势
- 23:00 52.2% → 00:00 42.1% → 01:00 29.4% → 02:00 59.1% → 03:00 56.5% → 04:00 86.8% → 05:00 76.3% → 06:00 53.8% → 06:50 83.3%(本轮)
- 波动 29-87%, 模式不变: NVCF 账户级配额耗尽 (429 无 retry-after, 全 5key 429 → TIER_COOLDOWN 180s)
- 04:00 回升 86.8%, 06:50 本轮 83.3% → 配额型故障模式确认, 非 nv_gw 侧可改

## 持续观察点 (沿用 R643, 不改码) — dsv4p_nv 配额型 429 全挂
- 6h SR 波动 29-87%, 04:00 回升 86.8%, 06:50 本轮 83.3% → 非 nv_gw 侧可改
- 01:00 单小时 SR=29.4% 触及 R621 升级阈值, 但非持续 + cc2 视角 0 样本 → 不触发回切
- KeyManager 指数退避正确 (429 count decay >300s → reset → 180s)
- 全 5key 429 → TIER_COOLDOWN 180s 全挂, 被 cc4101 fallback ms_gw(glm5_2_ms) 兜住, 用户侧无感
- 429 resp headers: ratelimit/retry=(none) — NVCF 不提供 retry-after, 配额型 429 确认
- 502×2 (avg 20346ms 慢) = NVCF 慢响应, peer-fb skip → 本地 502 返, cc4101 ms_gw 兜底, 设计正确
- NVStream_IncompleteRead ×1 = 502 路径的不完整流读, NVCF 慢响应子类型, 单发偶发, 非 nv_gw 故障

## 本轮改动
- 无 (NOP). 根因不变: NVCF 账户级配额耗尽 (429 无 retry-after), 非 nv_gw 侧可改.

## 依据
- cc2 0 流量 → 无评估样本, 铁律1 cc2 视角不满足 (同 R626-R643)
- dsv4p_nv SR=83.3% -2.4pp vs R643 (85.7%), 仍在正常波动区间 (37-91%) 内, 无突变恶化
- 6h SR 趋势 29-87% 波动, 04:00 回升 86.8%, 06:50 本轮 83.3% → 配额型故障模式确认
- all_tiers_exhausted ×3 持平 R643, 仍在正常波动区间 3-6, 无退化
- NVStream_IncompleteRead ×1 = 502 路径的不完整流读, NVCF 慢响应子类型, 单发偶发, 不构成新模式
- KeyManager 指数退避正确, 429 ABORT avg 2718ms (持平 R643 量级)
- per-key k2 全 first-attempt 命中 + 单 egress IP 203.10.96.139 主力 = 配额型故障模式未变
- 30min nv_tier_attempts 0 行 = KeyManager 层 ABORT 非 buffer 路径, hermes caller 不走 buffer
- stream_total_deadline 6h=0 → deadline 链 (90s×5=450s < 470s cc4101 < 500s SDK) 健康
- 502×2 peer-fb skip → cc4101 ms_gw 兜底, 设计正确, 非 nv_gw 故障
- 容器全稳, 配置无漂移, 无介入必要

## 验证
- 0 restart → 无需 py_compile / curl 复测
- 容器状态 (实测): nv_gw Up 24h, cc4101 Up 14h, ms_gw Up 4d, logs_db Up 4d
- /health ok: status=ok, nv_num_keys=5, nvcf_pexec_models=[kimi_nv,dsv4p_nv,glm5_2_nv], nv_default_model=glm5_2_nv
- 配置无漂移 (env 全项匹配 R643 快照, NVU_DISABLE_MS_FALLBACK=0/ms_gw fallback 已恢复)
- stream_total_deadline 6h=0 (deadline 链铁证)

## 下一步
- dsv4p_nv SR 83.3% (-2.4pp vs R643), 仍在正常波动区间内, 无突变恶化, 趋势向好
- **升级标注解除** (R621: SR<55% 或 exhausted>=8 → 切 PRIMARY 回 glm5_2_nv):
  - 01:00 单小时触及 29.4%, 但非持续 (04:00 86.8%, 06:50 83.3%), cc2 视角 0 样本 → 不触发
- **持续观察点: dsv4p_nv 配额型 429 全挂** (24h+ 持续, 单 egress IP 主力, NVCF 无 retry-after 头)
  - 若未来 SR 持续 <55% (连续 3+ 小时) 或 exhausted>=8 → 评估切 PRIMARY 回 glm5_2_nv
  - 或评估多 egress IP 轮换 (当前单 IP 203.10.96.139 主力, 配额可能绑 IP)
  - 关注 NVStream_IncompleteRead 是否从单发演变为模式 (当前 1 例, 阈值待定: >=3/30min)
- **建议维持: 联系 NVCF 侧评估 dsv4p_nv 账户配额扩容 / 提供 retry-after 头 / 慢响应根因**
- 继续 NOP 巡检, 等 cc2 流量恢复后观察 dsv4p_nv buffer 路径行为

## 参数快照 (R644 未改)
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
