# R626 — NOP 巡检轮 (2026-08-03 13:45 CST)

## 基线 (R626 实测, 05:11-05:42 UTC 窗口)
- cc2 (cc4101-primary) 30min: 0 req (session 间歇空闲, 无 cc2 评估样本)
- dsv4p_nv 30min (hermes caller): 26 req, 23×200 + 2×429 + 1×502 (SR=88.5%)
  - vs R625 85.0% / R624 82.4% / R623 76.5% / R622 64.3% / R621 57.1%
    → **连续 5 轮反弹 (57.1→64.3→76.5→82.4→85.0→88.5), 已回 R617-R618 正常波动区间 (75-91%) 上沿**
  - per-key: k2/k3 轮转命中 (13:26-13:42 一波 23×NV-SUCCESS, 全 k3 first attempt)
  - finish_reason: tool_calls×20 + stop×3 (健康, 无 zombie)
  - fallback_occurred=f ×26 (cc4101 层 ms_gw 兜底, 预期)
- 错误分类 1 类 (非新错误):
  - `all_tiers_exhausted` ×3 (429→1662ms 快速ABORT; 502→34646ms 长ABORT)
    → R621×6 → R622×5 → R623×4 → R624×3 → R625×3 → R626×3 持平
- 30min nv_tier_attempts: 0 行 (hermes caller 不走 buffer, KeyManager 层 ABORT)
- cc_requests stream_total_deadline 6h: 0 (deadline 链健康)

## 3h SR 趋势 (10min 桶, 02:40-05:40 UTC)
- 02:40-03:40: 波动 0-80% (NVCF 配额间歇)
- 03:50-05:40: 回升 60-100% 为主, 04:00 后多数桶 80-100%
- 整体: 反弹确认, 非线性恶化

## 新发现 (本轮观察点, 不改码) — RemoteDisconnected 34s 长卡顿
- 13:42:45 出现 1×502, duration=34646ms, 根因链:
  - `13:42:10.8 NV-KEY attempt 1/7: k3 → NVCF pexec via socks5h://172.18.0.1:7902` (peek-retry, explicit start_key=k3)
  - `13:42:45.5 NV-CONN k3 connection error: Remote end closed connection without response` (34.6s 后 NVCF 主动 FIN)
  - `13:42:45.5 NV-TIER-FAIL all 5 keys failed: other=1, elapsed=34642ms` (单 key 失败→全 tier ABORT)
  - `13:42:45.5 NV-PEER-FB model=dsv4p_nv in peer-fb skip list → returning local 502 for ms_gw fallback`
- DB 历史查证 (24h, dsv4p_nv, all_tiers_exhausted + duration>10s): 至少 10 次
  - 08-03 05:42(34646), 04:56(34306), 04:07(34716)
  - 08-02 23:16(54494), 23:01(53171), 16:09(35690), 15:06(33630), 14:25(10722), 11:27(34101), 10:56(72299)
  - **反复发生的低频模式, 非单次瞬态**
- 根因:
  - peek-retry 路径设计语义 = 只试 1 个 key 探测, k3 失败不轮转其他 key
  - NVCF 侧间歇性慢响应: 接受连接后 34-72s 静默, 然后主动 FIN (RemoteDisconnected), 非 socket 超时
  - per_attempt_timeout=90s, 但 NVCF 在 34.6s 主动断, 未触达 read timeout
  - → **不是 timeout 配置问题, 是 NVCF 上游慢响应 + peek-retry 单 key 语义共同导致**
  - mark_transport_error 正确触发 (5s penalty 不累计 conn_count), 但 peek-retry 不轮转, penalty 对当前请求无效
- 影响评估:
  - 被 cc4101 fallback ms_gw(glm5_2_ms) 兜住 (NVU_DISABLE_MS_FALLBACK=0), 用户侧无感
  - 24h 10 次, 低频; SR 仍处反弹区间
  - 改 nvcf_conn.py read timeout = 高风险 (影响全 key 全 model 连接层), 非本轮该动

## 本轮改动
- 无 (NOP). 根因是 NVCF 上游慢响应, 非 nv_gw 侧可改; peek-retry 单 key 语义是设计如此.

## 依据
- cc2 0 流量 → 无评估样本, 铁律1 cc2 视角不满足
- dsv4p_nv SR=88.5% 连续 5 轮反弹, 已回 R617-R618 正常波动区间上沿
- all_tiers_exhausted ×3 持平 R624/R625 (3→3→3), 与 SR 反弹同步
- 3h 趋势铁证: 04:00 后多数 10min 桶 80-100%, 配额型故障已缓解
- KeyManager 指数退避正确, 429 ABORT avg 1662ms (快速), 无退化
- RemoteDisconnected 34s 长 ABORT 根因 = NVCF 慢响应 + peek-retry 单 key, 非 timeout 配置
- cc_requests stream_total_deadline 6h=0 → deadline 链 (90s×5=450s < 470s cc4101 < 500s SDK) 健康
- 容器健康 (nv_gw Up 23h, cc4101 Up 13h, ms_gw/logs_db 长稳), 配置无漂移
- 无介入必要

## 验证
- 0 restart → 无需 py_compile / curl 复测
- 容器状态: nv_gw Up 23h (health ok, 5 keys), cc4101 Up 13h, ms_gw/logs_db/nv_gw_stable 长稳
- 配置无漂移 (env 全项匹配 R625 快照)

## 下一步
- dsv4p_nv SR 连续 5 轮反弹至 88.5%, 已回正常波动区间, 趋势确认反转
- **升级标注解除** (R621 设定 SR<55% 或 exhausted>=8 → 切 PRIMARY 回 glm5_2_nv): 持续未触发
- **新观察点: RemoteDisconnected 34-72s 长 ABORT** (24h 10+ 次)
  - 若未来轮次该模式高频化 (如单轮 ≥3 次 34s+ ABORT), 考虑评估 peek-retry 路径 transport-error 后轮转下 key (打破单 key 语义需谨慎)
  - 或评估 nvcf_conn.py read timeout 收紧 (NVCF 慢响应 34s+ 主动断 → 缩短 per-attempt read timeout 让其更快切 key), 但影响全 model, 需专门一轮 + 验证
- **建议维持: 联系 NVCF 侧评估 dsv4p_nv 账户配额扩容 / 提供 retry-after 头 / 慢响应根因**
- 继续 NOP 巡检, 等 cc2 流量恢复后观察 dsv4p_nv buffer 路径行为

## 参数快照 (R626 未改)
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
