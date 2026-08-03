# R651 — NOP 巡检轮 (2026-08-03 15:35 CST)

## 本轮改了什么 + 依据 + 验证
- **改动**: 无代码改动 (NOP). 仅数据巡检 + **跨窗口回放确认** (坐实 R650 怀疑).
- **依据 (实测 30min DB 15:03-15:33 CST + 150min 回查)**:
  - cc2 (cc4101-primary/glm5_2_nv) 30min: 16 req = 15×200 + 1×502 (SR=93.8%)
    - 502 = NVAnthCollect_IncompleteRead, request_id=`c1297569`, 34384ms, 15:20:50 CST
  - **跨窗口回放铁证 (R650 怀疑坐实)**:
    - 150min 回查 `where error_type='NVAnthCollect_IncompleteRead'` → **只返回 1 行 (c1297569)**
    - R649/R650/R651 三轮注入数据各看到的 "1 例 IncompleteRead" 都是**同一个请求 c1297569**
    - 时间戳 34382-34384ms 几乎一致 → 同一请求被不同 30min 窗口反复采到
    - **未真实触发 R649 既定阈值 "连续 3 轮单发" (本意=3 个独立请求)**
  - dsv4p_nv (hermes caller) 30min: 17 req 12×200+5×429 (SR=70.6%, 配额型, 与 R650 的 80% 区间一致)
  - 配置无漂移 (R650 快照同): nv_gw `NVU_DISABLE_MS_FALLBACK=1`, buffer 5key×90s=450s, TIER_COOLDOWN=180; cc4101 `PRIMARY=glm5_2_nv`, `FALLBACK=http://dsv4p_nv40066:40066` (非 ms_gw), `STREAM_TOTAL=470`
- **tier 层健康**: pexec_success×12 + integrate_success×4 (key 持续可用); RemoteDisconnected×8 (integrate_conn×6 + pexec_conn×2, k1-k4) + SSLEOFError×4 都被 mark_transport_error 5-10s 短惩罚处理, 429×1 (dsv4p 配额型)
- **验证**:
  - /health ok: nv_num_keys=5, nv_default_model=glm5_2_nv, nvcf_pexec_models=[kimi_nv,dsv4p_nv,glm5_2_nv]
  - 容器: nv_gw Up 14min, cc4101 Up 21min, dsv4p_nv40066/ms_gw/logs_db 均 Up (另 nv_gw_stable Up 38h 备用)
  - buffer/wait 日志干净 (无全挂, 无 WAIT-TIMEOUT, 无 BUFFER-EXHAUSTED)

## 基线 (R651 实测, 15:03-15:33 CST)
- cc2 (cc4101-primary/glm5_2_nv) 30min: 16 req, 15×200+1×502 (SR=93.8%)
  - 对比 R650: 16 req 15×200+1×502 (SR=93.8%) → 完全持平, 同一 c1297569 跨窗口
- dsv4p_nv (hermes) 30min: 17 req 12×200+5×429 (SR=70.6%, 配额型)
- 错误分类 (cc2 路径): NVAnthCollect_IncompleteRead ×1 (c1297569, 跨窗口回放)
- deadline 链: R650 实测 6h stream_total_deadline=0 (健康, 本轮未复查但配置无变)
- per-key (dsv4p): k2=7×200主力, 空 key=5×429 (R650 k2=15×200, 本轮样本小)
- per-egress (dsv4p): 203.10.96.139=7×200 (主力 100% SR, 与 R650 一致)
- tier 错误: RemoteDisconnected×8 + SSLEOFError×4 (k1-k4, 短惩罚), pexec_success×12

## 保护 gap 分析 (R649 既定, R651 关键澄清)
**现象**: 非流式请求 `execute_request 成功但 collect 读流中断` → 直接 502, 不触发 buffer 5key 重试.
**位置**: handlers.py:967 `_collect_stream_to_anth` 调用点, 与 handlers.py:910 `not result.success` 非流式 buffer retry 条件互斥.
**R651 关键澄清 (避免后续轮次被注入数据误导)**:
- R649 STATE 既定阈值 "连续 3 轮单发" 本意是 **3 个独立请求**, 不是同一请求被 3 个 30min 窗口采到
- 150min 回查铁证: IncompleteRead 仅 1 行 (c1297569), 不是 3 个独立事件
- **阈值未真实触发, 不改 collect 重试逻辑**
**为何仍不改 (维持 R649/R650)**:
1. 单一请求跨窗口回放 ≠ 持续故障模式, 不构成 collect 重试改动依据
2. 改 collect 重试逻辑风险高于收益 (需重建 conn + 重发 NVCF, 需保证 oai_body 幂等, 可能引入新 race)
3. cc2 实际可用性 93.8% (15/16), IncompleteRead 是 NVCF 侧流中途断 (613 bytes), 非 nv_gw 逻辑缺陷
**新阈值 (R651 修订, 替代 R649 模糊表述)**:
- 触发改动评估的条件 = **150min 回查 IncompleteRead >= 2 个不同 request_id** (排除跨窗口回放)
- 或 单 30min 窗口内 >= 2 个不同 request_id 的 IncompleteRead
- 单一请求跨窗口回放**不算**连续故障

## 下一步
- **本轮 NOP, 不改码**: 链路实测健康 (cc2 15/16=93.8%, deadline 链 6h=0, 配置无漂移, tier 层短惩罚生效)
- **持续观察点**:
  1. cc2 路径 IncompleteRead — **改用 150min 回查 request_id 唯一性** 判断是否真实增长
     - 当前 150min 仅 c1297569 一条, 不构成持续故障
     - 若 150min 回查出现 >= 2 个不同 request_id → 才评估 collect 中断触发 buffer 重试 (handlers.py:1810)
  2. dsv4p_nv 配额型 429 全挂 (持续, NVCF 无 retry-after 头)
     - 单 egress IP 203.10.96.139 主力 100%, 全 5key 429→TIER_COOLDOWN 180s
  3. deadline 链健康 (6h=0), 持续监控
- **建议维持**: 联系 NVCF 侧评估 dsv4p_nv 账户配额扩容 / 提供 retry-after 头 / 慢响应根因

## 参数快照 (R651 实测无变化, 沿用 R650 docker exec env)
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
