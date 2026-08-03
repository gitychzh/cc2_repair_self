# R633 — NOP 巡检轮 (2026-08-03 14:11 CST)

## 基线 (R633 实测, 05:36-06:06 UTC 窗口)
- cc2 (cc4101-primary) 30min: 0 req (session 间歇空闲, 无 cc2 评估样本, 同 R626-R632)
- dsv4p_nv 30min (hermes caller): 17 req, 11×200 + 4×429 + 2×502 (SR=64.7%)
  - vs R632 73.7% / R631 76.2% / R630 80.8% / R629 86.7% / R628 90.3% / R627 90.3%
    → **本轮继续降至 64.7%, 仍在 R617-R632 正常波动区间下沿 (64-91%), 小样本 17req 波动, 趋势未恶化**
  - per-key: k2=11×200 全 first-attempt 命中
  - per-egress-IP: 203.10.96.139 11×200 / 6 fail (单 IP 主力, 同 R630-R632)
  - finish_reason: tool_calls×10 + stop×1 (健康, 无 zombie)
  - fallback_occurred=f ×17 (hermes caller 直连 nv_gw)
  - 200 avg_dur=10102ms (健康, vs R632 9797ms 略慢, 仍在正常区间)
- 错误分类 1 类 (非新错误):
  - `all_tiers_exhausted` ×6 (avg_dur 12730ms: 429→1378ms 快速ABORT; 502→35433ms 长ABORT)
    → R624→...→R632→R633: 3→3→3→3→3→4→5→5→5→6 (持平正常区间 3-6, 本轮 +1 仍在波动内)
- 30min nv_tier_attempts: 0 行 (hermes caller 不走 buffer, KeyManager 层 ABORT)
- cc_requests stream_total_deadline 6h: 0 (deadline 链健康)

## 持续观察点 (沿用 R632, 不改码) — RemoteDisconnected 34-35s 长卡顿
- 本轮 2×502 duration≈35433ms, 同 R626-R632 (34646/35433×5) 模式
- 根因不变: NVCF 上游慢响应 (34s+ 主动 FIN) + peek-retry 单 key 语义不轮转, 非 timeout 配置
- 24h 反复低频模式, 被 cc4101 fallback ms_gw 兜住, 用户侧无感
- 改 nvcf_conn.py read timeout = 高风险 (影响全 key 全 model 连接层), 非本轮该动

## 本轮改动
- 无 (NOP). 根因不变: NVCF 配额型 + 上游慢响应, 非 nv_gw 侧可改.

## 依据
- cc2 0 流量 → 无评估样本, 铁律1 cc2 视角不满足 (同 R626-R632)
- dsv4p_nv SR=64.7% 续降 R632 73.7%, 仍在 R617-R632 正常波动区间下沿 (64-91%), 小样本 17req 波动
- all_tiers_exhausted ×6 (R624-R633: 3→3→3→3→3→4→5→5→5→6), +1 仍在正常波动区间, 无退化
- KeyManager 指数退避正确, 429 ABORT avg 1378ms (快速, 同 R632 1462ms)
- per-key k2 全 first-attempt 命中 + 单 egress IP 主力 = 配额型故障模式未变
- 30min nv_tier_attempts 0 行 = KeyManager 层 ABORT 非 buffer 路径
- cc_requests stream_total_deadline 6h=0 → deadline 链 (90s×5=450s < 470s cc4101 < 500s SDK) 健康
- 容器健康 (nv_gw Up 24h, cc4101 Up 13h, ms_gw/logs_db/nv_gw_stable 长稳), 配置无漂移
- 无介入必要

## 验证
- 0 restart → 无需 py_compile / curl 复测
- 容器状态: nv_gw Up 24h (health ok, 5 keys), cc4101 Up 13h, ms_gw/logs_db/nv_gw_stable 长稳
- 配置无漂移 (env 全项匹配 R632 快照)
- curl /health: status ok, nv_num_keys=5, nv_default_model=glm5_2_nv
- stream_total_deadline 6h=0 (deadline 链铁证)

## 下一步
- dsv4p_nv SR 本轮续降至 64.7% (R632 73.7%), 仍在正常波动区间下沿, 小样本波动无恶化
- **升级标注解除** (R621 设定 SR<55% 或 exhausted>=8 → 切 PRIMARY 回 glm5_2_nv): 持续未触发
- **持续观察点: RemoteDisconnected 34-35s 长 ABORT** (24h 10+ 次, 同 R626-R632)
  - 若未来轮次该模式高频化 (如单轮 ≥3 次 34s+ ABORT), 考虑评估 peek-retry 路径 transport-error 后轮转下 key
  - 或评估 nvcf_conn.py read timeout 收紧, 但影响全 model, 需专门一轮 + 验证
- **建议维持: 联系 NVCF 侧评估 dsv4p_nv 账户配额扩容 / 提供 retry-after 头 / 慢响应根因**
- 继续 NOP 巡检, 等 cc2 流量恢复后观察 dsv4p_nv buffer 路径行为

## 参数快照 (R633 未改)
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
