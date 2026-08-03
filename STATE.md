# R649 — NOP 巡检轮 (2026-08-03 15:24 CST)

## 本轮改了什么 + 依据 + 验证
- **改动**: 无代码改动 (NOP). 仅数据巡检 + 路径根因定位.
- **依据 (实测 30min DB 14:54-15:24 CST, docker exec env 实测)**:
  - cc2 (cc4101-primary/glm5_2_nv) 30min: 14 req = 13×200 + 1×502 (SR=92.9%, 小样本放大效应)
  - dsv4p_nv (hermes caller) 30min: 26 req, 22×200+4×429 (SR=84.6%, 配额型, 与 R648 持平区间)
  - 配置确认无漂移: nv_gw `NVU_DISABLE_MS_FALLBACK=1`, `NVU_MS_FALLBACK_ENABLED` 缺失(=0), buffer 5key×90s=450s; cc4101 `PRIMARY=glm5_2_nv`, `FALLBACK=http://dsv4p_nv40066:40066` (非 ms_gw), `STREAM_TOTAL=470`
- **根因定位 (cc2 路径 502)**:
  - 日志铁证: `[ERR] NV-ANTH collect IncompleteRead after 34382ms: IncompleteRead(613 bytes read)` (handlers.py:1813)
  - 路径 = cc4101-primary + 非流式请求 → `execute_request` **成功**拿 NVCF 流 → `_collect_stream_to_anth` (handlers.py:967) 读流 → **34s 后 NVCF 流中途断, 只读 613 bytes** → 直接落 502
  - **保护 gap 发现**: handlers.py:910 非流式 buffer 5key 重试只在 `execute_request 失败` 时触发, 这里 `execute_request 成功但 collect 读流中断` 落在盲区; ms_gw fallback (handlers.py:1858) 因 `NVU_MS_FALLBACK_ENABLED=0` 也不触发
  - tier 层 RemoteDisconnected×N + SSLEOFError×N (k2/k3/k4/k5) 都被正确 `mode→advance` + 5-10s 短惩罚处理 (KeyManager mark_transport_error 生效), 未冻结 key
- **验证**:
  - deadline 链 6h: stream_total_deadline=0 (健康铁证)
  - /health ok: nv_num_keys=5, nv_default_model=glm5_2_nv, nvcf_pexec_models=[kimi_nv,dsv4p_nv,glm5_2_nv]
  - 容器: nv_gw Up 9min, cc4101 Up 8min, dsv4p_nv40066/nv_gw_stable/ms_gw/logs_db 均 Up
  - cc2 实际 SR: 13/14=92.9% (但 1 例非持续模式, 13 例成功 avg 46s max 101s 表明 NVCF 慢但能完成)

## 基线 (R649 实测, 14:54-15:24 CST)
- cc2 (cc4101-primary/glm5_2_nv) 30min: 14 req, 13×200+1×502 (SR=92.9%)
  - 对比 R648: 3 req 3×200 SR=100% (小样本) → 本轮样本恢复, 1 例 IncompleteRead 首现于 cc2 路径
- dsv4p_nv (hermes) 30min: 26 req 22×200+4×429 (SR=84.6%, 持平 R647, R617-R649 区间 37-91% 内)
- 错误分类 2 类 (1 类新路径, 1 类配额型):
  - `NVAnthCollect_IncompleteRead` ×1 — **首次出现在 cc2/glm5_2_nv 路径** (R644-R648 均在 dsv4p/hermes 路径)
  - `all_tiers_exhausted` ×4 (dsv4p 配额型, 429 无 retry-after 全 5key 429→TIER_COOLDOWN 180s)
- deadline 链: stream_total_deadline 6h=0 (健康)
- per-key (dsv4p): k2=20×200主力, 空 key=4×429
- per-egress (dsv4p): 203.10.96.139=20×200 (主力 96% SR)

## 保护 gap 分析 (本轮核心发现, 待数据积累后改)
**现象**: 非流式请求 `execute_request 成功但 collect 读流中断` → 直接 502, 不触发 buffer 5key 重试.
**位置**: handlers.py:967 `_collect_stream_to_anth` 调用点, 与 handlers.py:910 `not result.success` 非流式 buffer retry 的条件互斥.
**为何不改**:
1. 单例不足以支撑中等复杂度改动 (collect 中断后重试需重建 conn + 重发 NVCF, 需保证 oai_body 幂等)
2. R644-R648 IncompleteRead 都在 dsv4p/hermes 路径单发, 本轮是 cc2/glm5_2_nv 路径首现, 未达"持续模式"阈值 (>=3/30min 或连续 3+ 轮)
3. 改 collect 重试逻辑风险高于收益 (当前 13/14=92.9% 实际可用, 改动可能引入新 race)
**阈值**: 若 cc2 路径 IncompleteRead 连续 3 轮单发 或 单轮 >=2/30min → 评估在 handlers.py:1810 catch IncompleteRead 后触发 buffer 5key 重试 (类似 :910 的非流式 retry, 但入口条件改为 collect 中断)

## 下一步
- **本轮 NOP, 不改码**: 链路实测健康 (cc2 13/14=92.9% 实际可用, 1 例非持续, deadline 链 0 触发, 配额型故障非 nv_gw 可改)
- **持续观察点**:
  1. cc2 路径 IncompleteRead 连续性 (R649 首现, R644-R648 均在 dsv4p/hermes 路径)
     - 若连续 3 轮单发 或 >=2/30min → 评估 collect 中断触发 buffer 重试 (handlers.py:1810)
  2. dsv4p_nv 配额型 429 全挂 (24h+ 持续, NVCF 无 retry-after 头)
     - 单 egress IP 203.10.96.139 主力 96%, 全 5key 429→TIER_COOLDOWN 180s
  3. deadline 链健康 (6h=0), 持续监控
- **建议维持**: 联系 NVCF 侧评估 dsv4p_nv 账户配额扩容 / 提供 retry-after 头 / 慢响应根因

## 参数快照 (R649 实测, 以 docker exec env 为准)
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
