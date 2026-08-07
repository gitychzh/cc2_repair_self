# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: **R1131 (NOP 巡检轮/不改码 — 30min 主链零表面错误 (错误分类空), cc2-primary
> 200|118=100% SR, 最近独立 10min 42/42=100% 全绿自愈; tier 错误 5× RD + 2× empty_200 全
> 单请求分布式一次性 self-heal 未上浮 (较上轮 8× RD 略降, 维持稳态); fallback 0%
> (0/1841); buffer 全 attempt-1 direct flush success 无 WAIT/无新 exhaust)**
> cc4101-primary (主 nv_gw:40006) 实测 30min = **0 行非-200** — 主链全绿
> — 最近独立 10min **42/42 = 100% SR, 零非-200** → 主链连续全绿自愈
> 非-200 归属: **无 (0 行, 全 caller)** — 6d1ecf8c blip (R1125~R1130 已闭合) 持续出窗,
> 无新表面错误
> fallback: 0% (30min 0/1841 fallback_triggered, 未走 ms_gw)
> tier 错误: 30min 5× NVCFPexecRemoteDisconnected (k0×2, k1×1, k3×1, k4×1)
> + 2× empty_200 (k1×1, k2×1), 各 key/time 分散单点 self-heal 未上浮 (较上轮 8× RD 略降, 稳态)
> buffer: 新窗口全 attempt-1 direct flush success (07a3fad6=12s / 6b608d60=3.7s / 08a5f569=18s)
> 无 WAIT/无新 exhaust
> SSLEOF/RD: 延续 [[ssleof-error-transient-egress-blip]] 模式, 全分布式单点 steady background
> 容器 (/health 实测 2026-08-08 ~00:38 CST): nv_gw 200 (5 key, pexec 5 模型), cc4101 200 (primary dsv4f0731_nv)
> 上轮: R1130 (NOP, 6d1ecf8c blip 正式闭合 30min 零表面错误)

## 本轮 (R1131) 改动 + 依据 + 验证

### 改动: 无 (NOP。30min 全 caller 零表面错误 (错误分类空), cc2-primary 200|118 = 100% SR,
### 最近独立 10min 42/42 = 100% SR 全绿自愈。tier 错误 5× RD + 2× empty_200 全单请求分布式
### 一次性 self-heal 未上浮, 较上轮 8× RD 略降维持稳态。fallback 0%, buffer 全 attempt-1
### direct flush 无 WAIT/无新 exhaust。cc2 范围无配置回归 → 不改码)

### 依据 (本 session 实拉 2026-08-08 ~00:38 CST / 16:38 UTC)

- **30min cc2-primary (nv_requests)**: `200|118` = **0 行非-200, 100% SR** — 主链全绿。
- **最近独立 10min (cc4101-primary)**: `42/42` = **100% SR, 零非-200** — 连续全绿自愈。
- **30min 错误分类 (cc2-primary)**: **空 (0 行)** — 无 surface 错误。
- **30min 全 caller SR**: dsv4f0731_nv `136/136 = 100.0%` (cc2-primary 119 + hermes 17)。
- **30min nv_tier_attempts 非-success**: 注入数据 5× NVCFPexecRemoteDisconnected (k0×2,k1×1,k3×1,k4×1)
  + empty_200×2 (k1×1,k2×1), 各 key/time 分散单点 self-heal, 无 multi-key 连续复发, 未上浮 surface。
  较上轮 8× RD 略降, 维持 steady background。
- **buffer 日志 (实查)**: 全 attempt-1 direct flush success
  (07a3fad6=12s / 6b608d60=3.7s / 08a5f569=18s, verdict=success_tool_call / success_text),
  无 WAIT、无新 exhaust。
- **fallback_triggered (30min cc_requests)**: 0 / 1841 total = **0%** — 未触发 ms_gw。
- **容器 /health (实查 2026-08-08 ~00:38 CST)**: nv_gw 200 (5 key, pexec 5 模型),
  cc4101 200 (primary dsv4f0731_nv) — 全链路健康。

### 本轮数据

| 指标 | 值 | 状态 |
|---|---|---|
| cc2 主链 (40006) 30min | **200|118 = 0 行非-200, 100% SR** | ✅ 零表面错误 |
| 最近独立 10min | **42/42 = 100% SR, 零非-200** | ✅ 主链连续全绿自愈 |
| cc2 专属错误分类 | 空 (0 行) | ✅ |
| 全 caller SR (30min) | dsv4f0731_nv 136/136 = 100.0% | ✅ |
| fallback 触发率 | 0% (30min 0/1841 fallback, 未走 ms_gw) | ✅ |
| per-key tier 错误 | 5× RD + 2× empty_200, 全单请求分布式 self-heal 未上浮 | ✅ (稳态, 较上轮 8× 略降) |
| buffer | 全 attempt-1 direct flush success (3~18s), 无 WAIT/无新 exhaust | ✅ |
| container /health | nv_gw 200, cc4101 200 | ✅ |

## 下一步
- 延续 NOP。主链滚动 30min 零表面错误、最近 10min 42/42 全绿、fallback 0%, 无参数可调。
- **观测 RD/SSLEOF 下沉趋势**: 本轮 tier RD 5× 较上轮 (8×) 略降, 全分布式单点 steady background
  ([[ssleof-error-transient-egress-blip]] 延续)。若回升尖峰 (>30 次/30min) 或同 key 多请求
  连续复发 RD, 再查该 key 对应 mihomo 端口线路。
- **ms_gw**: ms 链不可调, fallback 0% 未触发, 无需动作。