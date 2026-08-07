# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: **R1138 (NOP 巡检轮/不改码 — 30min 主链零表面错误 (错误分类空), cc2-primary
> 200|107=100% SR, 全 caller dsv4f0731_nv 133/133=100.0%; tier 错误仅 empty_200 1× (k2)
> + RD 3× (k0/k2/k4) 共 4 次, 单点分布式 transient self-heal, 低频下沉稳态,
> buffer 含 1 次 execute_failed 5s backoff attempt-2 自愈 (25.5s) 其余 direct flush,
> fallback 0% (133 行 0 触发))**
> cc4101-primary (主 nv_gw:40006) 实测 30min = **0 行非-200** — 主链全绿
> 非-200 归属: **无 (0 行, 全 caller)** — 零表面错误
> fallback: 0% (30min cc_requests 133 行 fallback_triggered=0, 未走 ms_gw)
> tier 错误: 30min empty_200 1× (k2) + NVCFPexecRemoteDisconnected 3× (k0/k2/k4), 共 4 次,
> 各 key/time 分散单点 self-heal 未上浮 (低频下沉稳态, 延续 [[ssleof-error-transient-egress-blip]])
> buffer: 1× execute_failed attempt-1 失败 → 5s backoff → attempt-2 success_text (25.5s),
> 单点 self-heal 未上浮; 余全 attempt-1 direct flush (无 WAIT/无新 exhaust)
> 容器 (/health 实测 2026-08-08 session): nv_gw 200 (5 key, pexec 5 模型), cc4101 200 (primary dsv4f0731_nv)
> 上轮: R1137 (NOP, 主链零表面错误 100% SR)

## 本轮 (R1138) 改动 + 依据 + 验证

### 改动: 无 (NOP。30min 全 caller 零表面错误 (错误分类空), cc2-primary 200|107 = 100% SR,
### 全 caller dsv4f0731_nv 133/133 = 100.0%。tier 错误仅 4 次非-success (k2 empty_200
### + k0/k2/k4 各 1× RD), 分布式单点 self-heal 未上浮, 低频下沉稳态。buffer 含 1 次
### execute_failed attempt-2 5s backoff 自愈, fallback 0%。cc2 范围无配置回归 → 不改码)

### 依据 (本 session 轮前注入 + 实查 2026-08-08)

- **30min cc2-primary (nv_requests 实查)**: `200|107` = **0 行非-200, 100% SR** — 主链全绿。
- **30min 错误分类 (实查)**: **空 (0 行)** — 无 surface 错误。
- **30min 全 caller SR (注入)**: dsv4f0731_nv `133/133 = 100.0%` (cc4101-primary 107 + hermes 26)。
- **30min nv_tier_attempts 非-success (实查)**: empty_200 1× (k2) + NVCFPexecRemoteDisconnected 3×
  (k0/k2/k4 各 1×), 共 4 次, 各 key/time 分散单点 self-heal, 无同 key 连续复发, 未上浮 surface。
  低频下沉稳态 (延续 [[ssleof-error-transient-egress-blip]])。
- **buffer 日志 (实查)**: 1 次 execute_failed attempt-1 失败 (req 2e42c974) → 5s backoff →
  attempt-2 success_text (elapsed 25590ms), 单点 self-heal 未上浮 (同源 transient);
  余全 attempt-1 direct flush (verdict success_text/success_tool_call), 无 WAIT/无新 exhaust。
- **fallback (实查)**: 30min 133 行, fallback_triggered 0 = **0%** — 未触发 ms_gw。
- **容器 /health (实查)**: nv_gw 200 (5 key, pexec 5 模型), cc4101 200 (primary dsv4f0731_nv)。

### 本轮数据

| 指标 | 值 | 状态 |
|---|---|---|
| cc2 主链 (40006) 30min | **200|107 = 0 行非-200, 100% SR** | ✅ 零表面错误 |
| cc2 专属错误分类 | 空 (0 行) | ✅ |
| 全 caller SR (30min) | dsv4f0731_nv 133/133 = 100.0% | ✅ |
| fallback 触发率 | 0% (30min 133 行, 未走 ms_gw) | ✅ |
| per-key tier 错误 | empty_200 1× (k2) + RD 3× (k0/k2/k4), 共 4 次, 单点分布式 self-heal 未上浮 | ✅ (低频下沉) |
| buffer | 1× execute_failed attempt-2 5s backoff 自愈 (25.5s), 余 attempt-1 direct flush | ✅ |
| container /health | nv_gw 200, cc4101 200 | ✅ |

## 下一步
- 延续 NOP。主链滚动 30min 零表面错误、fallback 0%、buffer 常态 direct flush + 低频单点
  self-heal, 无参数可调。
- 持续观察 tier 分布式单点 self-heal (empty_200/RD/execute_failed), 若有同 key 连续复发
  再查 mihomo 对应线路。