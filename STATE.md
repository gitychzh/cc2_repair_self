# R661 — collect 传输中断 → buffer 5key 重试 (R651 阈值首次触发后实施)

> 时间: 2026-08-03 16:03 CST (改) / 16:03+ (验证)
> 上轮: R660 (NOP 巡检, IncompleteRead 阈值第五轮复核未触发)

## 本轮改了什么 + 依据 + 验证

### 阈值触发 (R651 既定, 本轮首次触发)
R651 立的阈值: **150min 回查 IncompleteRead >= 2 个不同 request_id** 才构成"持续故障".
R651-R654+R660 五轮复核始终只 1 个 request_id (c1297569 单次事件), 阈值未触发.

**R661 复核 (150min 回查 ~07:00-09:00 UTC)**:
- `98ac8c50` @ 06:51:27 UTC, 36755ms, NVStream_IncompleteRead
- `bcc03ca7` @ 07:51:07 UTC, 32714ms, NVStream_IncompleteRead
- **两个独立 request_id, 间隔 60min → 阈值首次触发**, 持续故障模式确认.

### Gap 定位 (R649 既定, R661 实施)
- **位置**: `handlers.py:1719 _collect_stream_to_anth` (非流式 collect 路径).
- **现象**: `execute_request` 成功 (NVCF 连上+流开始) 但读流途中因 IncompleteRead/RemoteDisconnected/
  ConnectionResetError/OSError/timeout 中断 → 直接 502, 不触发 buffer 5key 重试.
- **为何不触发**: handlers.py:910 非流式 buffer retry 条件是 `not result.success` (execute_request 失败).
  collect 中断发生在 `execute_request` 成功**之后**, 与 :910 条件互斥, 落在盲区.

### 改动 (最小侵入, 镜像现有 NV-NONSTREAM-BUFFER-RETRY 模式)
**文件**: `/opt/cc-infra/proxy/nv-gw/gateway/handlers.py` (备份: `handlers.py.bak.R661`)

1. **签名加守护参数**: `_collect_stream_to_anth(..., _collect_buf_retried=False)` — 防递归.
2. **插入 transport-interrupt buffer retry 块** (handlers.py:1853, R1716 ms_gw fallback 块之前):
   - **触发条件** (窄, 仅传输中断类, 不误伤 zombie/empty/content_filter):
     - `_collect_err.startswith("NVAnthCollect_")` 且 `!= "NVAnthCollect_"`
     - `oai_body is not None`, `not _collect_buf_retried`, `caller in NVU_BUFFER_CALLERS`
   - **动作**: 清 collect 残留 error → `BufferStreamSession(is_nonstream=True).run()` 重跑 NVCF 5key
     → 成功则 buffer 内部 `_synthesize_nonstream_json` + `_send_json` 给 CC.
   - **失败兜底**: buffer 全败 → 恢复 error_type → 落 R1716 ms_gw fallback 块 (ms disabled 不触发) → 502.
   - **层级**: buffer retry (NVCF keys) 在 ms fallback 之前 (NVCF 优先, ms 最后).
   - **当前**: `NVU_DISABLE_MS_FALLBACK=1` / `NVU_MS_FALLBACK_ENABLED=0` → ms 块不触发, buffer 是唯一重试.

### 验证
- `python3 -c "import ast; ast.parse(open('handlers.py').read())"` → **ast parse ok**
- `docker compose restart nv_gw` → **Container nv_gw Started**
- `curl /health` → **ok, nv_num_keys=5, nvcf_pexec_models=[kimi_nv,dsv4p_nv,glm5_2_nv], default=glm5_2_nv**
- `docker ps` → nv_gw Up, cc4101 Up, dsv4p_nv40066 Up, logs_db Up, nv_gw_stable Up 38h
- `docker logs nv_gw --since 1m` → **无 error/traceback/import 失败**, ProbeWorker started 正常
- 配置无漂移: `NVU_DISABLE_MS_FALLBACK=1`, `NVU_BUFFER_CALLERS=cc4101-primary,openclaw2`

## 基线 (R661 实测, ~15:53-16:03 CST)
- cc2 (cc4101-primary/glm5_2_nv) 30min: 4 req 全 200 (SR=100.0%, 请求量低)
- **150min IncompleteRead 回查**: 2 个独立 request_id (98ac8c50 + bcc03ca7) → **阈值触发**
- dsv4p_nv 30min: 18 req 15×200+2×429+1×502 (SR=83.3%, 配额型, all_tiers_exhausted×2)
- deadline 链: 6h stream_total_deadline=0 (健康)
- tier 错误: pexec_success×2 + 429_nv_rate_limit×1 + pexec_SSLEOFError×1 (k2/k4 短惩罚)
- cc4101-fallback 0 次 (本轮 cc2 全 200 无需 fallback)

## 下一步
- **本轮已改码 (R651 阈值触发后实施) + 已验证 (编译/重启/health ok)**
- **持续观察点**:
  1. **重点**: cc2 路径 IncompleteRead 再现时是否触发 `NV-ANTH-COLLECT-BUFRETRY` → 200 救回
     - buffer 救回 → cc2 SR 从 90% 升至 100%, 改动生效
     - buffer 也败 (`NV-ANTH-COLLECT-BUFRETRY-FAIL`) → NVCF 持续劣化, 需更深排查
  2. 150min 回查 IncompleteRead 是否回归单次事件 (改后应减少, buffer 救回不再落 502)
  3. dsv4p_nv 配额型 429 全挂 (持续, NVCF 无 retry-after 头)
  4. deadline 链健康 (6h=0), 持续监控
- **建议维持**: 联系 NVCF 侧评估 dsv4p_nv 账户配额扩容 / 提供 retry-after 头

## 参数快照 (R661 实测无变化, 沿用 R660 docker exec env)
- nv_gw: NVU_DISABLE_MS_FALLBACK=1, UPSTREAM_TIMEOUT=90, TIER_COOLDOWN_S=180,
  KEY_COOLDOWN_S=30, NV_INTEGRATE_KEY_COOLDOWN_S=90, MIN_OUTBOUND_INTERVAL_S=10,
  NVU_FORCE_STREAM_UPGRADE=0, NVU_FORCE_STREAM_UPGRADE_TIMEOUT=150,
  NVU_BUFFER_MAX_RETRIES=5, NVU_BUFFER_TIMEOUT_STAIRS=90,90,90,90,90,
  NVU_BUFFER_TOTAL_DEADLINE_S=450, NVU_BUFFER_CALLERS=cc4101-primary,openclaw2,
  NVU_PEER_FB_SKIP_MODELS=glm5_2_nv,dsv4p_nv, NVU_CALLER_KEY_MAP=hermes:2;openclaw:3;opencode:4,
  NVU_KEYMGR_429_BASE_COOLDOWN=120, NVU_KEYMGR_429_MAX_COOLDOWN=600,
  NVU_KEYMGR_CONN_BASE_COOLDOWN=30, NVU_KEYMGR_CONN_FAIL_THRESHOLD=3,
  NVU_KEYMGR_CONN_LONG_COOLDOWN=120, NVU_KEYMGR_CONN_MAX_COOLDOWN=60,
  TIER_TIMEOUT_BUDGET_S=180, NVU_MS_FALLBACK_ENABLED=0
- cc4101: PRIMARY_UPSTREAM_URL=http://nv_gw:40006/v1/messages, PRIMARY_UPSTREAM_MODEL=glm5_2_nv,
  FALLBACK_UPSTREAM_URL=http://dsv4p_nv40066:40066/v1/messages (非 ms_gw), FALLBACK_UPSTREAM_MODEL=dsv4p_nv,
  CC4101_STREAM_TOTAL_DEADLINE_S=470, PRIMARY_HEADER_TIMEOUT=400,
  CC4101_PRIMARY_SKIP_S=30, CC4101_PRIMARY_FAIL_THRESHOLD=3,
  UPSTREAM_TIMEOUT=130, UPSTREAM_IDLE_TIMEOUT=150
- 链路: cc2(cc4101:4101) → nv_gw(40006, glm5_2_nv) → 5key(k0-k4)×5 US IP(hysteria2) → NVCF
  cc4101 fallback → dsv4p_nv40066(40066, 独立 dsv4p 容器) → NVCF
- deadline 链: UPSTREAM_TIMEOUT=90s < TIER_TIMEOUT_BUDGET=180s < buffer 90s×5=450s < cc4101 470s < SDK 500s idle
- 注: STATE R626-R647 env 快照过时, R648 起以 docker exec env 实测为准

## 风险评估 (为何安全)
1. **窄触发**: 仅 `NVAnthCollect_*` 传输中断类错误触发, 不误伤 zombie/empty/content_filter
   (模型端问题, 重试同请求无收益).
2. **双守护**: `_collect_buf_retried=True` 防递归; buffer 内部 `_synthesize_nonstream_json`
   不回调 `_collect_stream_to_anth` (无递归路径).
3. **层级正确**: buffer retry (NVCF keys) 在 ms_gw fallback 之前.
4. **失败兜底**: buffer 全败 → 恢复 error_type → 落 R1716 → 502 (退化到改前行为, 不会更差).
5. **幂等**: buffer 用原 `oai_body` 重发, NVCF 无状态推理, 重发安全; 非流式 `_send_json` 一次无重复响应.
