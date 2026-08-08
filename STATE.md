# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: **R1226 (NOP — SR 100%, 0 错误, fallback 0%, 连续第 6 轮全绿洁净)**
> 主链 fid: **281478d0-f307** 稳定, dsv4f0731_nv 单模式 (active 流量)
> 错误分类 (轮前注入 30min + 自查询, 09:20 CST): 请求级 0 错误; 仅 1 次 hermes 线瞬时
> NVCFPexecRemoteDisconnected (request 12c5d63d, 最终 200 self-heal, 非 cc2)
> 根因: 无新根因; cc2 专属 100/100, k3 SSLEOFError 持续不复发 (连续 6+ 轮), buffer 全 attempt=1 success
> 最新窗口: 30min cc2-primary 200|100, fallback 0%, 全量 dsv4f0731_nv SR 100%
> 容器: nv_gw /health ok (5 keys + dsv4f0731_nv fid 281478d0-f307), cc4101 ok

## 本轮 (R1226) 改动 + 依据 + 验证

### 改动: 无 (NOP 巡检轮。SR 100% + 0 请求级错误 + 全 attempt=1 success + fallback 0%, 不改码)

### 依据 (自查询, 2026-08-08 09:20 CST)

- **30min cc2-primary (nv_requests, caller=cc4101-primary)**: `200|100` → SR=**100% (100/100)**,
  无 502/4xx。请求级 0 错误。
- **30min 错误分类 (cc4101-primary status!=200)**: 空 (0 rows) → 无 buffer_exhausted /
  stream_total_deadline / 其他。
- **tier 错误 (nv_tier_attempts)**: `NVCFPexecRemoteDisconnected|1` — 仅 1 次 (request 12c5d63d,
  nv_key_idx=1, hermes caller, fid 281478d0)。**request_id JOIN → hermes 线非 cc2; request 最终
  status=200 self-heal 成功**。KeyManager 2 次瞬时惩罚 (k3/k5 penalty=5s transport_err no conn_count)
  均自愈吸收。瞬时 egress 抖动, 符合 R1077 self-heal 模式, 非 cc2 主链异常。
- **buffer 日志**: 全 `NV-BUFFER-SUCCESS ... after 1 attempt(s)`, elapsed 7-12s, 0 退回/惩罚/阻塞。
- **fallback**: 0% (cc4101-primary 全 200)。
- **k3 SSLEOFError (R1205/R1206)**: 持续不复发 (连续 6+ 轮), self-heal 离散瞬时确认。
- **mihomo 升级监控触发条件 (R1206/R1207 收紧) 判定**: 无真实新失败 (非上轮 request_id) + SR=100%
  ≥ 99% → 条件不满足, 延后。触发条件: **后续轮次真实新失败 + SR<99%**。
- **容器健康**: nv_gw /health ok (5 keys + pexec_models 含 dsv4f0731_nv, fid 281478d0-f307),
  cc4101 ok。参数无漂移 → 非配置回归。
- **容器 up**: nv_gw 29h, cc4101 29h, nv_gw_stable 6d。

### 验证
自查询 30min cc2-primary 100/100 (0 错误), fallback 0%, buffer 全 attempt=1 success。
唯一 RemoteDisconnected 归属 hermes 且最终 200 self-heal。容器 health ok、参数无漂移。→ 无改码条件, NOP。

## 参数快照 (nv_gw + cc4101, 与 R1225 一致)

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
R1225 (NOP — SR 100%, 0 错误, fallback 0%, 连续第 5 轮全绿) → R1226: 维持 SR 100%, fallback 0%。
cc2-primary 100 (较 R1225 的 96 微升), 全绿的正常流量波动。k3 SSLEOFError 持续不复发 (连续 6 轮)。
唯一 hermes 线瞬时 RemoteDisconnected (12c5d63d) 最终 200 self-heal, 非 cc2 主链异常。

## 下一步
维持静稳观察。**mihomo 升级监控触发条件 (R1206/R1207 收紧)**: 若 **后续轮次出现真实新失败
(非上轮 request_id) + SR<99%** → 拉 mihomo 隧道线路质量 (各 egress_ip 失败率、隧道状态、
带宽/超时)、逐关键链路排查并小步优化。持续观察 k3 SSLEOFError 不复发 (已被连续 6+ 轮确认
self-heal 离散瞬时); 若连续复发 → 查 k3 mihomo 7896 线路。hermes 线 RemoteDisconnected 归属
hermes, 非 cc2 范围 (request_id JOIN 判归属)。