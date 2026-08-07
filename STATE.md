# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: **R1167 (NOP 巡检 — 实查 30min cc4101-primary 200|101 = 100% SR, 0 非-200; 总线
> dsv4f0731_nv SR=99.4% (165/166) 唯一 502 为 `stream_first_byte_timeout` JOIN 归属 hermes 非 cc2、
> 非新类型; tier 全 pexec_success (101) 无 429/empty; fallback 0%; buffer 全 attempt-1
> direct flush 无退避无 WAIT; 整窗全绿跨十轮 → NOP 不改码)**
> 主链 fid: **281478d0-f307** 稳定 (全 5 key pexec), dsv4f0731_nv 单模式
> 错误分类 (surface, 30min): `stream_first_byte_timeout × 1` (= 归属 hermes 非 cc2, 瞬时首次包超时)
> 根因: 链上静稳, 唯一错误 JOIN 归属 hermes 非 cc2
> 最新 30min (03:15-03:45 CST): **cc2-primary 全 200 101/101 = 100% SR, 0 非-200**
> fallback: **0%** (总线 102 直通全 200, 0 触发)

## 本轮 (R1167) 改动 + 依据 + 验证

### 改动: 无 (NOP 巡检轮。cc2 整窗 101/101 全 200 无改码条件)

### 依据 (注入链路分析 2026-08-08 03:45 CST + 实查 30min + 容器健康)

- **实查 30min cc4101-primary**: `200|101` = 100% SR, 0 非-200。
- **注入 30min 总线**: `101×200(cc4101-primary) + 64×200(hermes) + 1×502(hermes)` = SR 99.4% (165/166)。
- **错误归属 (注入+实查)**: 唯一 502—`stream_first_byte_timeout` avg 83.2s
  均 `caller=hermes` 归属 hermes 非 cc2 请求, 同 R1162-R1165 签名:
  瞬时首次包超时 (first-byte), 非配置漂移、非新根因。
- **tier (注入 30min)**: 全 `pexec_success` (23/18/18/21/21=101), 无 429/empty/新类型,
  fid 全 281478d0-f307。
- **fallback (实查)**: 0 触发 (102 total, 总线全 200 直通)。
- **buffer 日志**: 全 attempt-1 direct flush (e.g. req fa921c27 attempt 1/5 verdict
  success_tool_call elapsed 8s), 无退避、无 WAIT、无 buffer_exhausted。
- **容器 (实查)**: nv_gw + cc4101 /health 全 ok, 未重启。

### 验证
cc2 (cc4101-primary) 实查 101/101 = 100% SR, 0 非-200; fallback 直查 0%;
tier 全 pexec_success 无新类型; buffer 全 attempt-1 direct flush 无退避无 WAIT;
容器全健康。链路稳定无改码条件。

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
R1166 (NOP — 实查 102/102 全 200) → R1167 确认: 实查 101/101 全 200, 唯一 hermes 瞬时 502
(首次包超时) 非 cc2。链路跨十轮全绿无新事件。

## 下一步
维持静稳观察。**核心监控: 是否重现独立瞬时 burst 及复发间隔**。
Burst2 后已跨 ~180+ min 无任何 cc2 异常, 穿越十轮 (R1158→R1167) 整窗全绿。
若下个窗口再现 ≥2× buffer_exhausted 且 request_id 全新 (JOIN 归属 cc2), 则为**独立新事件**,
按记忆 `ssleof-error-transient-egress-blip` 深挖 mihomo dsv4f0731_nv egress 线路 (7900-7904),
评估超 5 key 超大请求 buffer 首跳韧性。当前仍判定瞬时 egress 抖动非配置漂移, NOP。