# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: **R1147 (NOP 巡检轮/不改码 — 30min 主链零表面错误, cc2-primary
> 200|124=100% SR, 0 行非-200; 错误分类全空; tier 错误 RD (k0/k1/k2/k3 各 1
> + k4 2) + 500_nv_error 1× (k2) + empty_200 1× (k2) 分布式单点 self-heal 低频下沉稳态,
> 全 fid 52e1ddb6 主链 未上浮; buffer 128 tx 全部 attempt-1 direct flush 成功
> 无 exhaust/无 WAIT/无 execute_failed (较 R1146 更干净); fallback 0% (124 行 0 触发))**
> cc4101-primary (主 nv_gw:40006) 实查 30min = **0 行非-200** — 主链全绿
> 错误分类: **空** (所有 caller 0 行非-200, 较 R1146 连 hermes 侧错误都无)
> fallback: 0% (30min cc_requests 124 行 fallback_triggered=0, 未走 ms_gw)
> tier 错误: 30min NVCFPexecRemoteDisconnected (k0/k1/k2/k3 各 1, k4 2) + k2 500_nv_error 1×
>   + k2 empty_200 1×, 各 key/time 分散单点 self-heal 未上浮 surface (低频下沉稳态,
>   延续 [[ssleof-error-transient-egress-blip]])
> buffer: 30min ~128 tx 全部 attempt-1 direct flush 成功, 无 exhaust/无 WAIT/无 execute_failed
>   (R1146 后最干净, 主链 shortest-path 稳态)
> 容器 (实查): nv_gw 40006 ok, dsv4p_nv40066 40066 ok, 稳定未重启
> 上轮: R1146 (NOP, 主链零表面错误 100% SR)

## 本轮 (R1147) 改动 + 依据 + 验证

### 改动: 无 (NOP。30min cc2-primary 实查 0 行非-200 (200|124 = 100% SR), 主链全绿。
### 错误分类全空。tier 错误 RD (k0/k1/k2/k3 各 1 + k4 2) + k2 500_nv_error 1× + k2 empty_200 1×
### 分布式单点 self-heal 未上浮, 低频下沉稳态。buffer 全 attempt-1 direct flush 无 exhaust/无 WAIT/无 execute_failed。
### fallback 0% (124 行 0 触发)。cc2 范围无配置回归 → 不改码)

### 依据 (本 session 实查 2026-08-08)

- **30min cc2-primary (实查)**: `cc4101-primary|200|124` = **0 行非-200, 100% SR** — 主链全绿。
- **30min 链路总览 (注入)**: cc4101-primary|dsv4f0731_nv|200|123 + hermes|dsv4f0731_nv|200|33 (实查取数瞬间滚动到 124)。
- **30min 错误分类 (实查)**: **空** — 所有 caller 0 行非-200, surface 层连 hermes 侧错误都无 (较 R1146 更干净)。
- **fallback (实查)**: 30min cc_requests 124 行, fallback_triggered=0 = **0%** — 未触发 ms_gw。
- **tier 错误 (实查)**: NVCFPexecRemoteDisconnected (k0 1/k1 1/k2 1/k3 1/k4 2) + k2 500_nv_error 1×
  + k2 empty_200 1×, 全 fid 52e1ddb6 (dsv4f0731_nv 主链), 分散单点 self-heal 未上浮 surface,
  无同 key 连续复发。
- **buffer 日志 (实查)**: 共 ~128 [NV-BUFFER-START], 全部 attempt=1 → [NV-BUFFER-SUCCESS] direct flush,
  无 exhaust/无 WAIT/无 execute_failed (R1146 后最干净)。
- **容器 (实查)**: nv_gw:40006 /health ok (5 keys, 5 models), dsv4p_nv40066:40066 /health ok — 稳定运行。

### 本轮数据

| 指标 | 值 | 状态 |
|---|---|---|
| cc2 主链 (40006) 30min | **200|124 = 0 行非-200, 100% SR** | ✅ 零表面错误 |
| 错误分类 (surface) | **空** (所有 caller 0 行非-200) | ✅ 全绿 |
| fallback 触发率 | 0% (30min 124 行, 未走 ms_gw) | ✅ |
| per-key tier 错误 | RD (k0/k1/k2/k3 各 1 + k4 2) + k2 500_nv_error 1× + k2 empty_200 1×, 分散 self-heal 未上浮 | ✅ (低频下沉) |
| buffer | ~128 tx 全部 attempt-1 direct flush, 无 exhaust/无 WAIT/无 execute_failed | ✅ (最干净) |
| container | nv_gw 40006 ok, dsv4p_nv40066 40066 ok | ✅ |

## 参数快照 (nv_gw + cc4101, 注入)

- **nv_gw**: UPSTREAM_TIMEOUT=90, TIER_TIMEOUT_BUDGET_S=180, NVU_BUFFER_MAX_RETRIES=5 (stairs 90×5=450s),
  NVU_DISABLE_MS_FALLBACK=0, NVU_FORCE_STREAM_UPGRADE=0, NVU_PEER_FB_SKIP_MODELS=glm5_2_nv,dsv4p_nv,
  KEY_COOLDOWN_S=30, NV_INTEGRATE_KEY_COOLDOWN_S=90, TIER_COOLDOWN_S=180, MIN_OUTBOUND_INTERVAL_S=10,
  NVU_BUFFER_CALLERS=cc4101-primary,openclaw2, NVU_CALLER_KEY_MAP=hermes:2;openclaw:3;opencode:4。
- **cc4101**: PRIMARY_UPSTREAM_MODEL=dsv4f0731_nv, PRIMARY_UPSTREAM_URL=http://nv_gw:40006/v1/messages,
  FALLBACK_UPSTREAM_MODEL=glm5_2_ms, FALLBACK_UPSTREAM_URL=http://ms_gw:40007/v1/chat/completions,
  CC4101_STREAM_TOTAL_DEADLINE_S=470, PRIMARY_HEADER_TIMEOUT=400, CC4101_PRIMARY_FAIL_THRESHOLD=3,
  CC4101_PRIMARY_SKIP_S=30, UPSTREAM_TIMEOUT=130, UPSTREAM_IDLE_TIMEOUT=150。
- **nv_gw 主链 fid**: 当前 cc4101-primary 走 dsv4f0731_nv → fid **52e1ddb6** (RD/500_nv/empty 错误分布即该 fid)。

## 下一步

- 延续 NOP 观察至 R1148。主链 SR 100% + fallback 0% + buffer 全 direct flush 已达静稳最优。
- 注: cc4101 FALLBACK_UPSTREAM_URL 仍指 ms_gw:40007 (历史残留), 但 fallback=0% 从未触发, 铁律 4 不主动改。
- 触发更码信号 (任一): (1) cc2-primary 自身出现非-200; (2) fallback>5%; (3) buffer exhaust/WAIT
  或同 key 连续复发 (不等同单点 self-heal); (4) k2 500_nv_error/empty_200 连续复发。