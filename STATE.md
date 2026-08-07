# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: **R1145 (NOP 巡检轮/不改码 — 30min 主链零表面错误, cc2-primary
> 200|113=100% SR, 0 行非-200; 唯一 surface 错误 NVStream_IncompleteRead 1× (502)
> 归属 hermes 非 cc2; tier 错误 RD (k0/k1/k2/k3/k4, k4 3×) + empty_200 1× (k2) 分布式单点
> self-heal 低频下沉稳态; buffer 1× execute_failed (k4, req fabdf347) 5s backoff 后
> attempt-2 自愈成功, 其余全 direct flush 无 exhaust/无 WAIT; fallback 0% (113 行 0 触发))**
> cc4101-primary (主 nv_gw:40006) 实查 30min = **0 行非-200** — 主链全绿
> 非-200 归属: **hermes 1× NVStream_IncompleteRead (502), cc2 0 行** — cc2 零表面错误
> fallback: 0% (30min cc_requests 113 行 fallback_triggered=0, 未走 ms_gw)
> tier 错误: 30min NVCFPexecRemoteDisconnected (k0/k1/k2/k3 各 1, k4 3) + empty_200 1× (k2),
> 各 key/time 分散单点 self-heal 未上浮 (低频下沉稳态, 延续 [[ssleof-error-transient-egress-blip]])
> buffer: 30min 1× NV-BUFFER-EXEC-FAIL (k4, req fabdf347) → attempt-2/5 自愈成功 (29s);
>   其余全 attempt-1 direct flush 成功, 无 exhaust/无 WAIT
> 容器 (实查): nv_gw 22h, cc4101 22h, dsv4p_nv40066 3d, 全 /health ok 稳定未重启
> 上轮: R1144 (NOP, 主链零表面错误 100% SR)

## 本轮 (R1145) 改动 + 依据 + 验证

### 改动: 无 (NOP。30min cc2-primary 实查 0 行非-200 (200|113 = 100% SR), 主链全绿。
### 唯一 surface 错误 NVStream_IncompleteRead 1× (502) 实查 caller=hermes 非 cc2。tier 错误
### RD (k0/k1/k2/k3/k4, k4 3×) + empty_200 (k2) 分布式单点 self-heal 未上浮, 低频下沉稳态。
### buffer 1× execute_failed (k4, req fabdf347) 5s backoff 后 attempt-2 自愈成功 (29s), 其余全
### direct flush。fallback 0% (113 行 0 触发)。cc2 范围无配置回归 → 不改码)

### 依据 (本 session 轮前注入 + 实查 2026-08-08 01:50)

- **30min cc2-primary (实查)**: `200|113` = **0 行非-200, 100% SR** — 主链全绿。
- **30min 链路总览 (注入)**: cc4101-primary|dsv4f0731_nv|200|113 + hermes|200|25 + hermes|502|1。
- **30min 错误分类 (实查)**: 非-200 仅 caller=hermes 1× NVStream_IncompleteRead (502, 55.5s) — **归属 hermes** 非 cc2。
- **fallback (实查)**: 30min cc_requests 113 行, fallback_triggered=0 = **0%** — 未触发 ms_gw。
- **tier 错误 (实查)**: NVCFPexecRemoteDisconnected (k0 1/k1 1/k2 1/k3 1/k4 3) + empty_200 1× (k2),
  分散单点 self-heal 未上浮 surface, 无同 key 连续复发。
- **buffer 日志 (实查)**: 1× NV-BUFFER-EXEC-FAIL (k4, req fabdf347) → 5s backoff → attempt-2/5
  success_tool_call 自愈 (29s); 其余全 attempt-1 direct flush 成功, 无 exhaust/无 WAIT。
- **容器 (实查)**: nv_gw /health ok, nv_gw 22h, cc4101 22h, dsv4p_nv40066 3d — 稳定运行。

### 本轮数据

| 指标 | 值 | 状态 |
|---|---|---|
| cc2 主链 (40006) 30min | **200|113 = 0 行非-200, 100% SR** | ✅ 零表面错误 |
| 非-200 归属 | NVStream_IncompleteRead 1× (502, 55.5s) → **hermes**, cc2 0 行 | ✅ hermes 侧 |
| fallback 触发率 | 0% (30min 113 行, 未走 ms_gw) | ✅ |
| per-key tier 错误 | RD (k0/k1/k2/k3/k4, k4 3×) + empty_200 (k2), 单点分布式 self-heal 未上浮 | ✅ (低频下沉) |
| buffer | 1× execute_failed (k4, fabdf347) attempt-2 自愈; 其余 direct flush, 无 exhaust/无 WAIT | ✅ |
| container | nv_gw 22h, cc4101 22h, dsv4p_nv40066 3d | ✅ |

## 参数快照 (nv_gw + cc4101, 注入)

- nv_gw: UPSTREAM_TIMEOUT 90, NVU_DISABLE_MS_FALLBACK 0, NVU_BUFFER_CALLERS
  cc4101-primary/openclaw2, KEY_COOLDOWN_S 30, TIER_COOLDOWN_S 180, NV_INTEGRATE_KEY_COOLDOWN_S 90
- cc4101: PRIMARY_UPSTREAM_MODEL dsv4f0731_nv, PRIMARY_UPSTREAM_URL http://nv_gw:40006/v1/messages,
  FALLBACK_UPSTREAM_URL http://ms_gw:40007/v1/chat/completions, FALLBACK_UPSTREAM_MODEL glm5_2_ms,
  CC4101_STREAM_TOTAL_DEADLINE_S 470, PRIMARY_HEADER_TIMEOUT 400, CC4101_PRIMARY_FAIL_THRESHOLD 3

## 下一步
- 延续 NOP。主链滚动 30min 零表面错误、fallback 0%、buffer 无 exhaust/无 WAIT。
- 持续观察 tier RD (k4 3× 略偏高) / empty_200 分布式单点。若无同 key 多请求连续复发、
  不影响 surface (cc2 0 行非-200), 继续 NOP。若同 key RD/execute_failed 回升且浮上 surface
  (cc2 非-200 出现), 再查 mihomo 对应线路。