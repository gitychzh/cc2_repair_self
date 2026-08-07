# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: **R1134 (NOP 巡检轮/不改码 — 30min 主链零表面错误 (错误分类空), cc2-primary
> 200|116=100% SR, 全 caller dsv4f0731_nv 138/138=100.0%; tier 错误仅 empty_200 1× (k1)
> + RD 1× (k2) 共 2 次, 单点分布式 transient self-heal 收敛于上轮 (5× RD + 2× empty_200),
> fallback 0% (f 137), buffer 全 attempt-1 直接 flush 无 WAIT/无新 exhaust)**
> cc4101-primary (主 nv_gw:40006) 实测 30min = **0 行非-200** — 主链全绿
> 非-200 归属: **无 (0 行, 全 caller)** — 零表面错误
> fallback: 0% (30min f 137 fallback_triggered, 未走 ms_gw)
> tier 错误: 30min empty_200 1× (k1) + NVCFPexecRemoteDisconnected 1× (k2), 共 2 次,
> 分布式单点 self-heal 未上浮 (收敛于上轮 7 次, 下沉稳态)
> buffer: 新窗口无 WAIT/无新 exhaust (全 attempt-1 success_text/success_tool_call flush)
> SSLEOF/RD: 延续 [[ssleof-error-transient-egress-blip]] 模式, 极低频 steady background 且下沉
> 容器 (/health 实测 2026-08-08 session): nv_gw 200 (5 key, pexec 5 模型), cc4101 200 (primary dsv4f0731_nv)
> 上轮: R1133 (NOP, 主链零表面错误 100% SR)

## 本轮 (R1134) 改动 + 依据 + 验证

### 改动: 无 (NOP。30min 全 caller 零表面错误 (错误分类空), cc2-primary 200|116 = 100% SR,
### 全 caller dsv4f0731_nv 138/138 = 100.0%。tier 错误仅 2 次非-success (k1 empty_200 + k2 RD),
### 分布式单点 self-heal 未上浮且收敛于上轮 7 次。fallback 0%, buffer 全 attempt-1 direct flush。
### cc2 范围无配置回归 → 不改码)

### 依据 (本 session 轮前注入 + 实查 2026-08-08)

- **30min cc2-primary (nv_requests 注入)**: `200|116` = **0 行非-200, 100% SR** — 主链全绿。
- **30min 错误分类 (cc2-primary)**: **空 (0 行)** — 无 surface 错误。
- **30min 全 caller SR**: dsv4f0731_nv `138/138 = 100.0%` (cc4101-primary 116 + hermes 22)。
- **30min nv_tier_attempts 非-success**: 注入数据 empty_200 1× (k1) + NVCFPexecRemoteDisconnected 1× (k2),
  共 2 次, 各 key/time 分散单点 self-heal, 无 multi-key 连续复发, 未上浮 surface。
  较上轮 (R1133: 5× RD + 2× empty_200 = 7 次) **收敛**, 维持下沉稳态。
- **buffer 日志 (实查)**: 无 WAIT、无新 exhaust — 全 attempt-1 direct flush
  (verdict=success_text/success_tool_call, flush 953b~15096b, elapsed 1.7s~13.8s)。
- **fallback (30min)**: f 137 = **0%** — 未触发 ms_gw。
- **容器 /health (实查)**: nv_gw 200 (proxy_role passthrough, 5 key, pexec 5 模型),
  cc4101 200 (primary dsv4f0731_nv) — 全链路健康。

### 本轮数据

| 指标 | 值 | 状态 |
|---|---|---|
| cc2 主链 (40006) 30min | **200|116 = 0 行非-200, 100% SR** | ✅ 零表面错误 |
| cc2 专属错误分类 | 空 (0 行) | ✅ |
| 全 caller SR (30min) | dsv4f0731_nv 138/138 = 100.0% | ✅ |
| fallback 触发率 | 0% (30min f 137, 未走 ms_gw) | ✅ |
| per-key tier 错误 | empty_200 1× (k1) + RD 1× (k2), 共 2 次, 单点分布式 self-heal 未上浮 | ✅ (收敛, 低于上轮 7 次) |
| buffer | 无 WAIT/无新 exhaust (全 attempt-1 direct flush) | ✅ |
| container /health | nv_gw 200, cc4101 200 | ✅ |

## 下一步
- 延续 NOP。主链滚动 30min 零表面错误、fallback 0%, 无参数可调。
- **观测 RD/empty_200 下沉趋势**: 本轮 tier 非-success 2 次, 收敛于上轮 7 次
  ([[ssleof-error-transient-egress-blip]] 延续, 下沉稳态)。若回升尖峰 (>30 次/30min)
  或同 key 多请求连续复发 RD, 再查该 key 对应 mihomo 端口线路。
- **ms_gw**: ms 链不可调, fallback 0% 未触发, 无需动作。

## 参数快照 (2026-08-08)
- nv_gw: NVU_DISABLE_MS_FALLBACK=0, UPSTREAM_TIMEOUT=90, KEY_COOLDOWN_S=30,
  NV_INTEGRATE_KEY_COOLDOWN_S=90, TIER_TIMEOUT_BUDGET_S=180, TIER_COOLDOWN_S=180,
  NVU_FORCE_STREAM_UPGRADE=0, NVU_FORCE_STREAM_UPGRADE_TIMEOUT=150, MIN_OUTBOUND_INTERVAL_S=10,
  NVU_PEER_FB_SKIP_MODELS=glm5_2_nv,dsv4p_nv, NVU_CALLER_KEY_MAP=hermes:2;openclaw:3;opencode:4,
  NVU_BUFFER_CALLERS=cc4101-primary,openclaw2
- cc4101: PRIMARY_UPSTREAM_URL=http://nv_gw:40006/v1/messages, PRIMARY_UPSTREAM_MODEL=dsv4f0731_nv,
  FALLBACK_UPSTREAM_MODEL=glm5_2_ms, CC4101_STREAM_TOTAL_DEADLINE_S=470, PRIMARY_HEADER_TIMEOUT=400,
  PRIMARY_UPSTREAM_TIMEOUT=130, CC4101_PRIMARY_FAIL_THRESHOLD=3, CC4101_PRIMARY_SKIP_S=30