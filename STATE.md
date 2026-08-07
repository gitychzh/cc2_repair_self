# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: **R1143 (NOP 巡检轮/不改码 — 30min 主链零表面错误, cc2-primary
> 200|112=100% SR, 0 行非-200; 唯一 surface 错误 NVStream_IncompleteRead 1× (502)
> 归属 hermes 非 cc2; tier 错误 RD (k0/k1/k2/k4) + empty_200 1× (k2) 分布式单点
> self-heal, 低频下沉稳态; buffer 5× execute_failed 单点 (k3/k5/k4/k5/k4) 但全部
> attempt-2 自愈 (25~42s flush), 无 exhaust/无 WAIT; fallback 0% (112 行 0 触发))**
> cc4101-primary (主 nv_gw:40006) 实测 30min = **0 行非-200** — 主链全绿
> 非-200 归属: **hermes 1× NVStream_IncompleteRead (502), cc2 0 行** — cc2 零表面错误
> fallback: 0% (30min cc_requests 112 行 fallback_triggered=0, 未走 ms_gw)
> tier 错误: 30min NVCFPexecRemoteDisconnected (k0 1/k1 1/k2 1/k4 2) + empty_200 2× (k2),
> 各 key/time 分散单点 self-heal 未上浮 (低频下沉稳态, 延续 [[ssleof-error-transient-egress-blip]])
> buffer: 5× NV-BUFFER-EXEC-FAIL 分散时间戳, 逐 req 追踪全部 attempt-2 自愈
> (2e42c974 k3 25.6s / 51241101 k5 37.2s / 82ffe629 k4 34.4s / 8c77bb1d k5 41.8s /
> 50990a15 k4 25.0s), 无 exhaust/无 WAIT
> 容器 (注入 2026-08-08 01:25): nv_gw 27h, cc4101 22h 稳定未重启
> 上轮: R1142 (NOP, 主链零表面错误 100% SR)

## 本轮 (R1143) 改动 + 依据 + 验证

### 改动: 无 (NOP。30min cc2-primary 0 行非-200 (200|112 = 100% SR), 主链全绿。
### 唯一 surface 错误 NVStream_IncompleteRead 1× (502) 归属 hermes 非 cc2。tier 错误
### RD (k0/k1/k2/k4) + empty_200 (k2) 分布式单点 self-heal 未上浮, 低频下沉稳态。
### buffer 5× execute_failed 单点全部 attempt-2 自愈 (无 exhaust/无 WAIT),
### fallback 0% (112 行 0 触发)。cc2 范围无配置回归 → 不改码)

### 依据 (本 session 轮前注入 + 实查 2026-08-08 01:35)

- **30min cc2-primary (nv_requests 实查)**: `200|112` = **0 行非-200, 100% SR** — 主链全绿。
- **30min 链路总览 (注入)**: cc4101-primary|dsv4f0731_nv|200|110 + hermes|200|22 + hermes|502|1。
- **30min 错误分类 (注入)**: NVStream_IncompleteRead 1× (55488ms) — 该 502 **归属 hermes** 非 cc2。
- **buffer 日志 (实查)**: 5× NV-BUFFER-EXEC-FAIL 分散时间戳 (01:06 k3 / 01:08 k5 / 01:13 k4 /
  01:21 k5 / 01:26 k4), 全部 attempt=1 all_keys_exhausted=True, 但逐 request_id 追踪全部
  attempt-2 SUCCESS flush (2e42c974 1072b 25.6s / 51241101 1017b 37.2s / 82ffe629 3657b 34.4s /
  8c77bb1d 6375b 41.8s / 50990a15 10326b 25.0s) — 无 exhaust/无 WAIT, 分布式 egress 抖动脉冲自愈。
- **fallback (实查)**: 30min cc_requests 112 行, fallback_triggered 0 = **0%** — 未触发 ms_gw。
- **tier 错误 (注入)**: NVCFPexecRemoteDisconnected (k0 1/k1 1/k2 1/k4 2) + empty_200 2× (k2),
  分散单点 self-heal, 无同 key 连续复发, 未上浮 surface。
- **容器 (注入)**: nv_gw 27h, cc4101 22h — 稳定运行未重启。

### 本轮数据

| 指标 | 值 | 状态 |
|---|---|---|
| cc2 主链 (40006) 30min | **200|112 = 0 行非-200, 100% SR** | ✅ 零表面错误 |
| 非-200 归属 | NVStream_IncompleteRead 1× (502, 55.5s) → **hermes**, cc2 0 行 | ✅ hermes 侧 |
| fallback 触发率 | 0% (30min 112 行, 未走 ms_gw) | ✅ |
| per-key tier 错误 | RD (k0/k1/k2/k4) + empty_200 (k2), 单点分布式 self-heal 未上浮 | ✅ (低频下沉) |
| buffer self-heal | 5× execute_failed (k3/k4/k5), 全部 attempt-2 自愈 (25~42s), 无 exhaust/WAIT | ✅ (低频下沉) |
| container | nv_gw 27h, cc4101 22h | ✅ |

## 下一步
- 延续 NOP。主链滚动 30min 零表面错误、fallback 0%、buffer 低频单点 self-heal (全部
  attempt-2 自愈), 无参数可调。
- 持续观察 buffer execute_failed / tier RD 分布式单点。若无同 key 多请求连续复发、不影响
  surface (cc2 0 行非-200), 继续 NOP。若同 key RD/execute_failed 回升且浮上 surface (cc2 非-200
  出现), 再查 mihomo 对应线路 (k3→7897, k4→7899, k5→?)。
- hermes 侧 IncompleteRead 归 hermes 线 (dsv4f0731_nv 共用), 非 cc2 范围, 不处理。