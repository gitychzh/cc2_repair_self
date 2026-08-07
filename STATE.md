# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: **R1144 (NOP 巡检轮/不改码 — 30min 主链零表面错误, cc2-primary
> 200|109=100% SR, 0 行非-200; 唯一 surface 错误 NVStream_IncompleteRead 1× (502)
> 归属 hermes 非 cc2; tier 错误 RD (k0/k1/k2/k3/k4) + empty_200 1× (k2) 分布式单点
> self-heal, 低频下沉稳态; buffer 本轮无 execute_failed, 全 direct flush 无 WAIT/无 exhaust;
> fallback 0% (130 行 0 触发))**
> cc4101-primary (主 nv_gw:40006) 实测 30min = **0 行非-200** — 主链全绿
> 非-200 归属: **hermes 1× NVStream_IncompleteRead (502), cc2 0 行** — cc2 零表面错误
> fallback: 0% (30min cc_requests 130 行 fallback_triggered=0, 未走 ms_gw)
> tier 错误: 30min NVCFPexecRemoteDisconnected (k0/k1/k2/k3 各 1, k4 3) + empty_200 1× (k2),
> 各 key/time 分散单点 self-heal 未上浮 (低频下沉稳态, 延续 [[ssleof-error-transient-egress-blip]])
> buffer: 本轮无 NV-BUFFER-EXEC-FAIL 日志, 全部 direct flush, 无 WAIT/无 exhaust
>   (较 R1143 的 5× execute_failed 更干净)
> 容器 (注入 2026-08-08 01:30): nv_gw 22h, cc4101 22h, dsv4p_nv40066 3d 稳定未重启
> 上轮: R1143 (NOP, 主链零表面错误 100% SR)

## 本轮 (R1144) 改动 + 依据 + 验证

### 改动: 无 (NOP。30min cc2-primary 0 行非-200 (200|109 = 100% SR), 主链全绿。
### 唯一 surface 错误 NVStream_IncompleteRead 1× (502) 归属 hermes 非 cc2。tier 错误
### RD (k0/k1/k2/k3/k4) + empty_200 (k2) 分布式单点 self-heal 未上浮, 低频下沉稳态。
### buffer 本轮无 execute_failed, 全 direct flush 无 WAIT/无 exhaust,
### fallback 0% (130 行 0 触发)。cc2 范围无配置回归 → 不改码)

### 依据 (本 session 轮前注入 + 实查 2026-08-08 01:40)

- **30min cc2-primary (注入)**: `200|109` = **0 行非-200, 100% SR** — 主链全绿。
- **30min 链路总览 (注入)**: cc4101-primary|dsv4f0731_nv|200|109 + hermes|200|20 + hermes|502|1。
- **30min 错误分类 (注入)**: NVStream_IncompleteRead 1× (55488ms) — 该 502 **归属 hermes** 非 cc2。
- **buffer 日志**: 本轮无 NV-BUFFER-EXEC-FAIL / NV-BUFFER / WAIT- 日志 — 全 direct flush, 无 exhaust/无 WAIT。
- **fallback (注入)**: 30min cc_requests 130 行, fallback_triggered 0 = **0%** — 未触发 ms_gw。
- **tier 错误 (注入)**: NVCFPexecRemoteDisconnected (k0 1/k1 1/k2 1/k3 1/k4 3) + empty_200 1× (k2),
  分散单点 self-heal 未上浮 surface, 无同 key 连续复发。
- **容器 (实查)**: nv_gw /health ok, nv_gw 22h, cc4101 22h, dsv4p_nv40066 3d — 稳定运行。

### 本轮数据

| 指标 | 值 | 状态 |
|---|---|---|
| cc2 主链 (40006) 30min | **200|109 = 0 行非-200, 100% SR** | ✅ 零表面错误 |
| 非-200 归属 | NVStream_IncompleteRead 1× (502, 55.5s) → **hermes**, cc2 0 行 | ✅ hermes 侧 |
| fallback 触发率 | 0% (30min 130 行, 未走 ms_gw) | ✅ |
| per-key tier 错误 | RD (k0/k1/k2/k3/k4) + empty_200 (k2), 单点分布式 self-heal 未上浮 | ✅ (低频下沉) |
| buffer | 无 execute_failed, 全 direct flush, 无 WAIT/无 exhaust | ✅ (干净) |
| container | nv_gw 22h, cc4101 22h, dsv4p_nv40066 3d | ✅ |

## 参数快照 (nv_gw + cc4101, 注入)

- nv_gw: UPSTREAM_TIMEOUT 90, NVU_DISABLE_MS_FALLBACK 0, NVU_BUFFER_CALLERS
  cc4101-primary/openclaw2, KEY_COOLDOWN_S 30, TIER_COOLDOWN_S 180, NV_INTEGRATE_KEY_COOLDOWN_S 90
- cc4101: PRIMARY_UPSTREAM_MODEL dsv4f0731_nv, PRIMARY_UPSTREAM_URL http://nv_gw:40006/v1/messages,
  FALLBACK_UPSTREAM_URL http://ms_gw:40007/v1/chat/completions, FALLBACK_UPSTREAM_MODEL glm5_2_ms,
  CC4101_STREAM_TOTAL_DEADLINE_S 470, PRIMARY_HEADER_TIMEOUT 400, CC4101_PRIMARY_FAIL_THRESHOLD 3

## 下一步
- 延续 NOP。主链滚动 30min 零表面错误、fallback 0%、buffer 无 WAIT/无 exhaust。
- 持续观察 tier RD (k4 3× 略偏高) / empty_200 分布式单点。若无同 key 多请求连续复发、
  不影响 surface (cc2 0 行非-200), 继续 NOP。若同 key RD/execute_failed 回升且浮上 surface
  (cc2 非-200 出现), 再查 mihomo 对应线路。
- hermes 侧 IncompleteRead 归 hermes 线 (dsv4f0731_nv 本线), 非 cc2 范围, 不处理。