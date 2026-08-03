# R650 — NOP 巡检轮 (2026-08-03 15:35 CST)

## 本轮改了什么 + 依据 + 验证
- **改动**: 无代码改动 (NOP). 仅数据巡检 + IncompleteRead 连续性追踪.
- **依据 (实测 30min DB 14:59-15:29 CST, docker exec env 实测)**:
  - cc2 (cc4101-primary/glm5_2_nv) 30min: 16 req = 15×200 + 1×502 (SR=93.8%)
    - 200 avg 42.4s (NVCF 慢但能完成), 502 = IncompleteRead 34s 后流断 613 bytes
  - dsv4p_nv (hermes caller) 30min: 25 req, 20×200+5×429 (SR=80.0%, 配额型, 与 R649 持平区间)
  - 配置确认无漂移: nv_gw `NVU_DISABLE_MS_FALLBACK=1`, buffer 5key×90s=450s, TIER_COOLDOWN=180; cc4101 `PRIMARY=glm5_2_nv`, `FALLBACK=http://dsv4p_nv40066:40066` (非 ms_gw), `STREAM_TOTAL=470`
- **IncompleteRead 连续性追踪 (R649→R650)**:
  - R649 首现 cc2/glm5_2_nv 路径 (1 例, handlers.py:1813 `[ERR] NV-ANTH collect IncompleteRead after 34382ms`)
  - R650 第 2 轮单现 (1 例, 15:20:50, 同样 34382ms 613 bytes — 时间戳几乎一致, 疑为同一请求跨窗口回放或 30min 窗口重叠)
  - **未达阈值**: R649 既定 "连续 3 轮单发 或 >=2/30min" 才评估改 collect 重试. 当前 2 轮各 1 例, 不改.
- **tier 层健康**: RemoteDisconnected×8 (k1×3+k3×3+k2×1+k4×1) + SSLEOFError×4 (k2×3+k4×1) 都被 mark_transport_error 5-10s 短惩罚处理, pexec_success×16 + integrate_success×7 表明 key 持续可用, 未冻结
- **验证**:
  - deadline 链 6h: stream_total_deadline=0 (健康铁证)
  - /health ok: nv_num_keys=5, nv_default_model=glm5_2_nv, nvcf_pexec_models=[kimi_nv,dsv4p_nv,glm5_2_nv]
  - 容器: nv_gw Up 9min, cc4101 Up 16min, dsv4p_nv40066/ms_gw/logs_db 均 Up
  - buffer/wait 日志干净 (无全挂, 无 WAIT-TIMEOUT)

## 基线 (R650 实测, 14:59-15:29 CST)
- cc2 (cc4101-primary/glm5_2_nv) 30min: 16 req, 15×200+1×502 (SR=93.8%)
  - 对比 R649: 14 req 13×200+1×502 (SR=92.9%) → 样本+2, SR 微升, IncompleteRead 仍单发
- dsv4p_nv (hermes) 30min: 25 req 20×200+5×429 (SR=80.0%, 持平 R649 的 84.6% 区间, 配额型)
- 错误分类 2 类 (与 R649 同构):
  - `NVAnthCollect_IncompleteRead` ×1 — cc2/glm5_2_nv 路径第 2 轮单现
  - `all_tiers_exhausted` ×5 (dsv4p 配额型, 429 无 retry-after 全 5key 429→TIER_COOLDOWN 180s)
- deadline 链: stream_total_deadline 6h=0 (健康)
- per-key (dsv4p): k2=15×200主力, 空 key=5×429
- per-egress (dsv4p): 203.10.96.139=15×200 (主力 100% SR)
- tier 错误: RemoteDisconnected×8 + SSLEOFError×4 (k1-k4, 短惩罚处理), pexec_success×16

## 保护 gap 分析 (R649 既定, 本轮未触发改动阈值)
**现象**: 非流式请求 `execute_request 成功但 collect 读流中断` → 直接 502, 不触发 buffer 5key 重试.
**位置**: handlers.py:967 `_collect_stream_to_anth` 调用点, 与 handlers.py:910 `not result.success` 非流式 buffer retry 条件互斥.
**为何仍不改**:
1. R649→R650 仅 2 轮各 1 例, 未达 "连续 3 轮单发" 阈值
2. 改 collect 重试逻辑风险高于收益 (需重建 conn + 重发 NVCF, 需保证 oai_body 幂等, 可能引入新 race)
3. cc2 实际可用性 93.8% (15/16), IncompleteRead 是 NVCF 侧流中途断, 非 nv_gw 逻辑缺陷
**阈值 (维持 R649)**: 若 cc2 路径 IncompleteRead 连续 3 轮单发 或 单轮 >=2/30min → 评估在 handlers.py:1810 catch IncompleteRead 后触发 buffer 5key 重试

## 下一步
- **本轮 NOP, 不改码**: 链路实测健康 (cc2 15/16=93.8%, deadline 链 0 触发, 配置无漂移, tier 层短惩罚生效)
- **持续观察点**:
  1. cc2 路径 IncompleteRead 连续性 (R649 首现, R650 第 2 轮单现)
     - 若 R651 再现 → 达 "连续 3 轮" 阈值, 评估 collect 中断触发 buffer 重试 (handlers.py:1810)
     - 注意: R649/R650 两例时间戳几乎一致 (34382ms), 需确认是否同一请求跨窗口回放
  2. dsv4p_nv 配额型 429 全挂 (持续, NVCF 无 retry-after 头)
     - 单 egress IP 203.10.96.139 主力 100%, 全 5key 429→TIER_COOLDOWN 180s
  3. deadline 链健康 (6h=0), 持续监控
- **建议维持**: ���系 NVCF 侧评估 dsv4p_nv 账户配额扩容 / 提供 retry-after 头 / 慢响应根因

## 参数快照 (R650 实测, 以 docker exec env 为准)
- nv_gw: NVU_DISABLE_MS_FALLBACK=1, UPSTREAM_TIMEOUT=90, TIER_COOLDOWN_S=180,
  KEY_COOLDOWN_S=30, NV_INTEGRATE_KEY_COOLDOWN_S=90, MIN_OUTBOUND_INTERVAL_S=10,
  NVU_FORCE_STREAM_UPGRADE=0, NVU_FORCE_STREAM_UPGRADE_TIMEOUT=150,
  NVU_BUFFER_MAX_RETRIES=5, NVU_BUFFER_TIMEOUT_STAIRS=90,90,90,90,90,
  NVU_BUFFER_TOTAL_DEADLINE_S=450, NVU_BUFFER_CALLERS=cc4101-primary,openclaw2,
  NVU_PEER_FB_SKIP_MODELS=glm5_2_nv,dsv4p_nv, NVU_CALLER_KEY_MAP=hermes:2;openclaw:3;opencode:4,
  NVU_KEYMGR_429_BASE_COOLDOWN=120, NVU_KEYMGR_429_MAX_COOLDOWN=600,
  NVU_KEYMGR_CONN_BASE_COOLDOWN=30, NVU_KEYMGR_CONN_FAIL_THRESHOLD=3,
  NVU_KEYMGR_CONN_LONG_COOLDOWN=120, NVU_KEYMGR_CONN_MAX_COOLDOWN=60,
  TIER_TIMEOUT_BUDGET_S=180
- cc4101: PRIMARY_UPSTREAM_URL=http://nv_gw:40006/v1/messages, PRIMARY_UPSTREAM_MODEL=glm5_2_nv,
  FALLBACK_UPSTREAM_URL=http://dsv4p_nv40066:40066/v1/messages (非 ms_gw), FALLBACK_UPSTREAM_MODEL=dsv4p_nv,
  CC4101_STREAM_TOTAL_DEADLINE_S=470, PRIMARY_HEADER_TIMEOUT=400,
  CC4101_PRIMARY_SKIP_S=30, CC4101_PRIMARY_FAIL_THRESHOLD=3,
  UPSTREAM_TIMEOUT=130, UPSTREAM_IDLE_TIMEOUT=150
- 链路: cc2(cc4101:4101) → nv_gw(40006, glm5_2_nv) → 5key(k0-k4)×5 US IP(hysteria2) → NVCF
  cc4101 fallback → dsv4p_nv40066(40066, 独立 dsv4p 容器) → NVCF
- deadline 链: UPSTREAM_TIMEOUT=90s < TIER_TIMEOUT_BUDGET=180s < buffer 90s×5=450s < cc4101 470s < SDK 500s idle
- 注: STATE R626-R647 env 快照过时, R648 起以 docker exec env 实测为准
