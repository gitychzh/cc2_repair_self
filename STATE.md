# R660 — NOP 巡检轮 (cc2 自优化线, 2026-08-03 15:48 CST)

## 本轮改了什么 + 依据 + 验证
- **改动**: 无代码改动 (NOP). 仅数据巡检 + R651 既定阈值第五轮复核.
- **依据 (实测 30min DB ~15:18-15:48 CST + 150min 回查)**:
  - cc2 (cc4101-primary/glm5_2_nv) 30min: 10 req = 9×200 + 1×502 (SR=90.0%)
    - 502 = NVAnthCollect_IncompleteRead, request_id=`c1297569`, 34384ms, 07:20:50 UTC
  - **150min 回查 (R651 既定阈值复核, 第五轮)**:
    - `nv_requests where error_type='NVAnthCollect_IncompleteRead'` → **仍只 1 行 (c1297569, hits=1, min=max=07:20:50)**
    - 单次事件, 非跨窗口回放增长
    - 与 R651/R652/R653/R654 四轮复核完全一致 → **阈值 (150min >= 2 个不同 request_id) 未触发, 不改 collect 重试逻辑**
  - dsv4p_nv 30min: 17 req 14×200+3×429 (SR=82.4%, 配额型, 与 R654 的 71.4% 同区间波动)
    - all_tiers_exhausted ×3 (5key 全 429→TIER_COOLDOWN 180s), NVCF 无 retry-after 头
  - cc4101-fallback 1 次 (dsv4p_nv 200) — primary 路径 1 次 502 触发 fallback, fallback 链路健康
- **tier 层健康**: pexec_success×12 + integrate_success×4 (key 持续可用); RemoteDisconnected×8 (integrate_conn×6 k1/k3 + pexec_conn×2 k2/k4) + SSLEOFError×4 (k2/k4) 都被 mark_transport_error 5-10s 短惩罚处理; 429×1 (dsv4p 配额型)
- **deadline 链**: 6h stream_total_deadline=0 (健康铁证, 与 R654 一致)
- **验证**:
  - /health ok: nv_num_keys=5, nv_default_model=glm5_2_nv, nvcf_pexec_models=[kimi_nv,dsv4p_nv,glm5_2_nv]
  - 容器: nv_gw Up 29min, cc4101 Up 35min, dsv4p_nv40066 Up 29min, ms_gw/logs_db Up 4 days, nv_gw_stable Up 38h 备用
  - 配置无漂移 (与 R654 快照一致): nv_gw NVU_DISABLE_MS_FALLBACK=1, buffer 5key×90s=450s, TIER_COOLDOWN=180; cc4101 PRIMARY=glm5_2_nv, FALLBACK=http://dsv4p_nv40066:40066, STREAM_TOTAL=470

## 基线 (R660 实测, ~15:18-15:48 CST)
- cc2 (cc4101-primary/glm5_2_nv) 30min: 10 req, 9×200+1×502 (SR=90.0%)
  - 对比 R654: 14 req 13×200+1×502 (SR=92.9%) → 同一 c1297569, SR 小幅波动 (窗口边界漂移, 请求量低)
- dsv4p_nv 30min: 17 req 14×200+3×429 (SR=82.4%, 配额型, R654 为 71.4%)
- 错误分类 (cc2 路径): NVAnthCollect_IncompleteRead ×1 (c1297569, 单次事件)
- deadline 链: 6h stream_total_deadline=0 (健康)
- tier 错误: RemoteDisconnected×8 + SSLEOFError×4 (k1-k4, 短惩罚), pexec_success×12, 429×1

## 保护 gap 分析 (R649 既定, R651 修订阈值, R660 第五轮复核未触发)
**现象**: 非流式请求 `execute_request 成功但 collect 读流中断` → 直接 502, 不触发 buffer 5key 重试.
**位置**: handlers.py:967 `_collect_stream_to_anth` 调用点, 与 handlers.py:910 `not result.success` 非流式 buffer retry 条件互斥.
**R660 复核**: 150min 回查 IncompleteRead 仍只 1 行 (c1297569, min=max=07:20:50), 未出现第 2 个独立 request_id.
**阈值 (R651 修订, R660 沿用)**:
- 触发改动评估 = **150min 回查 IncompleteRead >= 2 个不同 request_id** (排除跨窗口回放)
- 或 单 30min 窗口内 >= 2 个不同 request_id 的 IncompleteRead
- 单一请求跨窗口回放**不算**持续故障
**为何仍不改**:
1. 单次事件 (min=max=07:20:50) ≠ 持续故障模式, 不构成 collect 重试改动依据
2. 改 collect 重试逻辑风险高于收益 (需重建 conn + 重发 NVCF, 需保证 oai_body 幂等, 可能引入新 race)
3. cc2 实际可用性 90.0% (9/10), IncompleteRead 是 NVCF 侧流中途断 (613 bytes), 非 nv_gw 逻辑缺陷

## 下一步
- **本轮 NOP, 不改码**: 链路实测健康 (cc2 9/10=90.0%, deadline 链 6h=0, 配置无漂移, tier 层短惩罚生效)
- **持续观察点**:
  1. cc2 路径 IncompleteRead — **改用 150min 回查 request_id 唯一性** 判断是否真实增长
     - 当前 150min 仅 c1297569 一条 (R651-R654+R660 五轮复核一致), 不构成持续故障
     - 若 150min 回查出现 >= 2 个不同 request_id → 才评估 collect 中断触发 buffer 重试 (handlers.py:1810)
  2. dsv4p_nv 配额型 429 全挂 (持续, NVCF 无 retry-after 头)
     - SR 82.4% (14/17), all_tiers_exhausted ×3 (5key 全 429→TIER_COOLDOWN 180s)
  3. deadline 链健康 (6h=0), 持续监控
- **建议维持**: 联系 NVCF 侧评估 dsv4p_nv 账户配额扩容 / 提供 retry-after 头

## 参数快照 (R660 实测无变化, 沿用 R651 docker exec env)
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
