# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: **R1221 (NOP — SR 100%, 0 错误, fallback 0%, 防御链按设计工作)**
> 主链 fid: **281478d0-f307** 稳定, dsv4f0731_nv 单模式 (active 流量)
> 错误分类 (活查 30min, 08:3x CST): 空 (无 buffer_exhausted / stream_total_deadline / 其他)
> 根因: 无新根因; 唯一事件=单 k3 SSLEOFError 瞬时 self-heal (00a20c6d attempt2 补刀成功), 成功非回归
> 最新窗口: 30min cc2-primary 200|81, cc_requests 全 200 fallback 0%, dsv4f0731_nv 全量 151/151 SR 100%
> 容器: nv_gw /health ok (5 keys + dsv4f0731_nv fid 281478d0-f307), cc4101 ok, ms_gw ok

## 本轮 (R1221) 改动 + 依据 + 验证

### 改动: 无 (NOP 巡检轮。SR 100% + 无请求级错误, mihomo 升级监控条件不触发, 不改码不查 mihomo)

### 依据 (轮前注入链路分析 + 活查确认, 2026-08-08 CST)

- **30min cc2-primary (nv_requests)**: `200|81`, **无 502/4xx** → SR=**100% (81/81)**
  (活查确认)。请求级 0 错误。
- **30min 错误分类 (活查)**: 空 (0 rows) → 无 buffer_exhausted / stream_total_deadline / 其他。
- **dsv4f0731_nv 全量 (含 hermes 70)**: 151/151 SR=**100%** (注入快照 151 counts, 活查 81+70 核实)。
- **fallback**: 0% (活查 0/81 → 0 fallback_triggered)。
- **per-key tier** (nv_tier_attempts 活查): 整窗全 pexec_success
  (k0 17/k1 16/k2 13/k3 18/k4 17), 全部 bind fid 281478d0-f307, 无任何 attempt 级错误。
- **buffer 日志 (活查)**: 绝大多数请求 attempt=1 即 success (如 108d9635 1 attempt,
  eb86623e/c2d3084d 1 attempt success_tool_call)。唯一异常:
  - **req=00a20c6d**: attempt1 遇 **k3 SSLEOFError** (instant transport_err, penalty=10s no conn_count,
    all_keys_exhausted=True) → Buffer 5s backoff → attempt2 补刀 success_tool_call → flushed 1613b,
    最终 200 自愈, 无用户可见失败。属 **R1077/k3-transient 已知 self-heal 带内** (离散瞬时, 非连续复发)。
  - 无 WAIT- 阻塞, 无 buffer_exhausted, 无 multi-attempt 连续失败, 无 KEYMGR 指数惩罚累计。
- **mihomo 升级监控条件 (R1206/R1207 收紧) 判定**: 无真实新失败 (请求级 0 错, 00a20c6d 最终 200)
  + SR=100% ≥ 99% → 条件不满足, mihomo 隧道检查继续延后。触发条件: **后续轮次出现真实新失败
  (非上轮 request_id) + SR<99%**。
- **容器健康**: nv_gw /health ok (5 keys + pexec_models 含 dsv4f0731_nv, fid 281478d0-f307),
  cc4101 ok, ms_gw ok, nv_gw_stable Up 6d。参数与 R1220 一致 → 非配置回归。
- **容器 up**: nv_gw 29h, cc4101 29h — 各容器持续稳定无重启。

### 验证
活查 30min cc2-primary 81/81 (0 错误), 全量 151/151 SR 100%、fallback 0%;
容器 health ok、参数无漂移。per-key 全 pexec_success。00a20c6d 单 k3 SSLEOFError
attempt2 补刀最终 200 自愈, 成功非回归。
→ 无改码条件, NOP。

## 参数快照 (nv_gw + cc4101, 与 R1220 一致)

- **nv_gw**: UPSTREAM_TIMEOUT=90, TIER_TIMEOUT_BUDGET_S=180, NVU_BUFFER_MAX_RETRIES=5
  (stairs 90×5=450s), NVU_DISABLE_MS_FALLBACK=0, NVU_FORCE_STREAM_UPGRADE=0,
  KEY_COOLDOWN_S=30, INTEGRATE_KEY_COOLDOWN_S=90, TIER_COOLDOWN_S=180, MIN_OUTBOUND_INTERVAL_S=10,
  NVU_BUFFER_CALLERS=cc4101-primary,openclaw2, NV_INTEGRATE_KEY_COOLDOWN_S=90,
  NVU_FORCE_STREAM_UPGRADE_TIMEOUT=150, NVU_CALLER_KEY_MAP=hermes:2;openclaw:3;opencode:4,
  NVU_PEER_FB_SKIP_MODELS=glm5_2_nv,dsv4p_nv (全 key bind fid index 0=281478d0-f307, dsv4f0731_nv 单模式)。
- **cc4101**: PRIMARY_UPSTREAM_MODEL=dsv4f0731_nv, PRIMARY_UPSTREAM_URL=http://nv_gw:40006/v1/messages,
  FALLBACK_UPSTREAM_MODEL=glm5_2_ms, FALLBACK_UPSTREAM_URL=http://ms_gw:40007/v1/chat/completions,
  CC4101_STREAM_TOTAL_DEADLINE_S=470, PRIMARY_HEADER_TIMEOUT=400, PRIMARY_FAIL_THRESHOLD=3,
  PRIMARY_SKIP_S=30, UPSTREAM_TIMEOUT=130, UPSTREAM_IDLE_TIMEOUT=150。

## 上轮
R1220 (NOP — SR 100%, 0 错误, fallback 0%) → R1221: 维持 SR 100%, fallback 0%,
全量 dsv4f0731_nv 151/151。R1206 SSLEOFError/Remote-end-closed 瞬时 egress 抖动统计影响持续闭合;
本轮单 k3 SSLEOFError (00a20c6d) 由 Buffer attempt2 自愈, 成功非回归。

## 下一步
维持静稳观察。**mihomo 升级监控触发条件 (R1206/R1207 收紧)**: 若 **后续轮次出现真实新失败
(非上轮 request_id) + SR<99%** → 拉 mihomo 隧道线路质量 (各 egress_ip 失败率、隧道状态、
带宽/超时)、逐关键链路排查并小步优化。重点留意 k3 SSLEOFError 是离散瞬时 (本轮单例自愈)
还是连续复发; 若连续复发 (非绝对失败 SR<99%) → 查 k3 mihomo 7896 线路。