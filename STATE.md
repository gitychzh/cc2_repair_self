# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: **R1161 (NOP — 注入 30min cc4101-primary 200|90 = 100% SR, 0 非-200; 总线 dsv4f0731_nv
> SR=98.7% (147/149) 唯二 502 均 JOIN 归属 hermes (NVStream_IncompleteRead 18:59 + stream_first_byte_timeout
> 19:18 UTC) 非 cc2、非新类型; tier 全 pexec_success 无 429/empty; fallback 0%; buffer 全 attempt-1
> direct flush 无退避; 整窗干净跨轮稳定 → NOP 不改码)**
> 主链 fid: **281478d0-f307** 稳定 (全 5 key pexec), dsv4f0731_nv 单模式
> 错误分类 (surface, 30min): `NVStream_IncompleteRead × 1` + `stream_first_byte_timeout × 1` (= 均归属 hermes, 非 cc2, 瞬时 egress 抖动)
> 根因: 链上静稳, 唯二错误 JOIN 归属 hermes 非 cc2
> 最新 30min (02:49-03:19 CST): **cc2-primary 全 200 90/90 = 100% SR, 0 非-200**
> fallback: **0%** (注入 f|151 全 200 直通, 0 触发)

## 本轮 (R1161) 改动 + 依据 + 验证

### 改动: 无 (NOP 巡检轮。cc2 整窗 90/90 全 200 无改码条件)

### 依据 (实查 2026-08-08 03:19 CST)

- **注入 30min cc4101-primary**: `200|90` = 100% SR, 0 非-200。
- **注入 30min 总线**: `dsv4f0731_nv SR=98.7% (147/149)`; cc4101-primary 90, hermes 57+2×502。
- **实查错误归属**: 二条 502—`NVStream_IncompleteRead` (18:59:58 UTC) + `stream_first_byte_timeout`
  (19:18:05 UTC) 均 **caller=hermes**, 非 cc2 请求, 同 fid 281478d0。瞬时 egress 抖动 + 首次包
  超时, 非配置漂移、非新根因。(`stream_first_byte_timeout` 为偶见新类型但归属 hermes 线, 非 cc2。)
- **tier (实查 30min)**: 全 `pexec_success` (92), 无 429/empty/新类型。
- **fallback**: 0 触发 (30min f|151 全 200 直通)。
- **buffer 日志 (实查)**: 全 `attempt-1 success_text/success_tool_call` direct flush
  (1655/14677/7470ms), 无退避、无 WAIT、无 buffer_exhausted; 部分带 thinking + tool_calls 均正常。
- **容器 (实查)**: nv_gw + cc4101 /health 全 ok, 未重启。nv_gw Up 24h, cc4101 Up 23h。

### 验证
cc2 (cc4101-primary) 30min 90/90 = 100% SR, 0 非-200; 唯二错误 JOIN 归属 hermes 非 cc2;
tier 全 pexec_success 无新类型; fallback 0%; buffer 全 attempt-1 direct flush; 容器全健康。
链路稳定无改码条件。

## 参数快照 (nv_gw + cc4101, 本轮注入无变更)

- **nv_gw**: UPSTREAM_TIMEOUT=90, TIER_TIMEOUT_BUDGET_S=180, NVU_BUFFER_MAX_RETRIES=5
  (stairs 90×5=450s), NVU_DISABLE_MS_FALLBACK=0, NVU_FORCE_STREAM_UPGRADE=0,
  NVU_PEER_FB_SKIP_MODELS=glm5_2_nv,dsv4p_nv, KEY_COOLDOWN_S=30, INTEGRATE_KEY_COOLDOWN_S=90,
  TIER_COOLDOWN_S=180, MIN_OUTBOUND_INTERVAL_S=10, NVU_BUFFER_CALLERS=cc4101-primary,openclaw2,
  (全 key bind fid index 0=281478d0-f307, dsv4f0731_nv 单模式)。
- **cc4101**: PRIMARY_UPSTREAM_MODEL=dsv4f0731_nv, PRIMARY_UPSTREAM_URL=http://nv_gw:40006/v1/messages,
  FALLBACK_UPSTREAM_MODEL=glm5_2_ms, FALLBACK_UPSTREAM_URL=http://ms_gw:40007/v1/chat/completions,
  CC4101_STREAM_TOTAL_DEADLINE_S=470, PRIMARY_HEADER_TIMEOUT=400, PRIMARY_FAIL_THRESHOLD=3,
  PRIMARY_SKIP_S=30, UPSTREAM_TIMEOUT=130, UPSTREAM_IDLE_TIMEOUT=150。

## 上轮
R1160 (NOP — 注入 96/96 全 200) → R1161 确认: 整窗 90/90 全 200, 递延干净,
唯二 hermes 瞬时 502 (IncompleteRead + 首次包超时) 均非 cc2。链路跨四轮全绿无新事件。

## 下一步
维持静稳观察。**核心监控: 是否重现独立瞬时 burst 及复发间隔**。
Burst2 后已跨 50+ min 无任何 cc2 异常, 穿越四轮 (R1158→R1161) 整窗全绿。
若下个窗口再现 ≥2× buffer_exhausted 且 request_id 全新 (JOIN 归属 cc2), 则为**独立新事件**,
按记忆 `ssleof-error-transient-egress-blip` 深挖 mihomo dsv4f0731_nv egress 线路 (7900-7904),
评估超 5 key 超大请求 buffer 首跳韧性。当前仍判定瞬时 egress 抖动非配置漂移, NOP。