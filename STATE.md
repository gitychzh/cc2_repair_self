# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: **R1139 (NOP 巡检轮/不改码 — 30min 主链零表面错误, cc2-primary
> 200|106=100% SR, 0 行非-200; 唯一 surface 错误 NVStream_IncompleteRead 1× (502)
> 归属 hermes 非 cc2; tier 错误仅 RD 4× (k0/k2/k4) + empty_200 1× (k2) 共 5 次,
> 单点分布式 transient self-heal, 低频下沉稳态; buffer 全 attempt-1 direct flush,
> 无 WAIT/无 exhaust; fallback 0% (109 行 0 触发))**
> cc4101-primary (主 nv_gw:40006) 实测 30min = **0 行非-200** — 主链全绿
> 非-200 归属: **hermes 1× NVStream_IncompleteRead (502), cc2 0 行** — cc2 零表面错误
> fallback: 0% (30min cc_requests 109 行 fallback_triggered=0, 未走 ms_gw)
> tier 错误: 30min NVCFPexecRemoteDisconnected 4× (k0 1/k2 1/k4 2) + empty_200 1× (k2),
> 共 5 次, 各 key/time 分散单点 self-heal 未上浮 (低频下沉稳态, 延续 [[ssleof-error-transient-egress-blip]])
> buffer: 全 attempt-1 direct flush (success_tool_call/success_text), 无 execute_failed/
> 无 backoff/无 WAIT/无新 exhaust
> 容器 (/health 实测 2026-08-08 session): nv_gw 200 (5 key, pexec 5 模型), cc4101 200 (primary dsv4f0731_nv)
> 上轮: R1138 (NOP, 主链零表面错误 100% SR)

## 本轮 (R1139) 改动 + 依据 + 验证

### 改动: 无 (NOP。30min cc2-primary 0 行非-200 (200|106 = 100% SR), 主链全绿。
### 唯一 surface 错误 NVStream_IncompleteRead 1× (502) 归属 hermes 非 cc2。tier 错误
### 5 次非-success (RD 4× k0/k2/k4 + empty_200 1× k2), 分布式单点 self-heal 未上浮,
### 低频下沉稳态。buffer 全 attempt-1 direct flush, fallback 0% (109 行 0 触发)。
### cc2 范围无配置回归 → 不改码)

### 依据 (本 session 实查 2026-08-08 01:10)

- **30min cc2-primary (nv_requests 实查)**: `200|106` = **0 行非-200, 100% SR** — 主链全绿。
- **30min 非-200 归属 (实查)**: NVStream_IncompleteRead 1× (502) **归属 hermes** 非 cc2; cc2 = 0 行。
- **30min nv_tier_attempts 非-success (实查)**: NVCFPexecRemoteDisconnected 4× (k0 1/k2 1/k4 2)
  + empty_200 1× (k2), 共 5 次, 各 key/time 分散单点 self-heal, 无同 key 连续复发, 未上浮 surface。
  低频下沉稳态 (延续 [[ssleof-error-transient-egress-blip]])。
- **buffer 日志 (实查)**: 全 attempt-1 direct flush (verdict success_tool_call/success_text,
  elapsed 1~13s), 无 execute_failed/无 backoff/无 WAIT/无新 exhaust。
- **fallback (实查)**: 30min cc_requests 109 行, fallback_triggered 0 = **0%** — 未触发 ms_gw。
- **容器 /health**: nv_gw / cc4101 200 (本次未重启, 运行 26h/21h 稳定)。

### 本轮数据

| 指标 | 值 | 状态 |
|---|---|---|
| cc2 主链 (40006) 30min | **200|106 = 0 行非-200, 100% SR** | ✅ 零表面错误 |
| 非-200 归属 | NVStream_IncompleteRead 1× (502) → **hermes**, cc2 0 行 | ✅ hermes 侧 |
| fallback 触发率 | 0% (30min 109 行, 未走 ms_gw) | ✅ |
| per-key tier 错误 | RD 4× (k0 1/k2 1/k4 2) + empty_200 1× (k2), 共 5 次, 单点分布式 self-heal 未上浮 | ✅ (低频下沉) |
| buffer | 全 attempt-1 direct flush, 无 WAIT/无 exhaust | ✅ |
| container /health | nv_gw 200, cc4101 200 | ✅ |

## 下一步
- 延续 NOP。主链滚动 30min 零表面错误、fallback 0%、buffer 常态 direct flush + 低频单点
  self-heal, 无参数可调。
- 持续观察 tier 分布式单点 self-heal (RD/empty_200), 若有同 key 连续复发 (尤其 k4 RD 2×)
  再查 mihomo 对应线路 (k4→7899)。
- hermes 侧 IncompleteRead 归 hermes 线, 非 cc2 范围, 不处理。