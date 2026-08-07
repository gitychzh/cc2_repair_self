# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: **R1084 (NOP 巡检轮/不改码 — cc2 主链 103/103=100% SR 全 clean 零坏, 连续第 3 轮; hermes 2 bad out-of-scope; fallback 0.0%)**
> cc4101-primary (主 nv_gw:40006) 实测 30min = **103/103 = 100% SR, 零 bad** — 连续第 3 轮全 clean
> (R1082 107/108 → R1083 115/115 → R1084 103/103), 无新错误, 无配置漂移
> dsv4f0731_nv 总 149/151=98.7% 的 2 bad (502×2: NVStream_IncompleteRead×1 + zombie_empty_completion×1) **全归 hermes** (out-of-scope);
> per-key 全 5 key 均 pexec_success (19-22/key), 仅 k3 2 次 transient NVCFPexecRemoteDisconnected 已补回, 无冷却堆积;
> buffer req=0c9a505f 一次 k4 attempt-1 all_keys_exhausted → 自愈 attempt-2 全量补回 (退避/重试机制有效);
> fallback 0/104 = 0.0%; 无 BUFFER-EXHAUSTED/WAIT 异常日志;
> 容器 (/health 复核): nv_gw Up 17h, cc4101 Up 17h, 40006/4101 全 200
> 上轮: R1083 (NOP, 主链 115/115=100% 全 clean 零坏)

## 本轮 (R1084) 改动 + 依据 + 验证

### 改动: 无 (NOP。主链 103/103=100% 全 clean 零坏, 连续第 3 轮, 无新错误, 无 fallback, 无配置漂移; hermes 2 bad 均 out-of-scope, 无参数可调)

### 依据 (轮前注入 20:55 CST + DB 复核 20:58 + 容器 /health 复核 2026-08-07)

- **30min cc4101-primary (主 nv_gw:40006) = 103/103 = 100% SR, 零 bad**
  DB 复核 `SELECT status,count(*) ... caller='cc4101-primary'` → 全 200, 0 非 200。连续第 3 轮全 clean。
- **per-caller 归属铁证**: dsv4f0731_nv 总 149/151 (2 bad) 的 502×2, 错误分类 NVStream_IncompleteRead×1 + zombie_empty_completion×1
  经 caller 复核**全归 hermes**, out-of-scope; cc4101-primary 零坏。
- **per-key 健康**: nv_tier_attempts 全 5 key 均高 pexec_success (k0 22/k1 20/k2 22/k3 20/k4 19);
  仅 k3 2 次 NVCFPexecRemoteDisconnected (transient, 部分补回), KeyManager 正常无堆积。
- **buffer 自愈铁证**: req=0c9a505f attempt-1 key=k4 execute_failed (all_keys_exhausted=True) → backoff 5s →
  attempt-2 success_tool_call 全量 12789b flush 补回。同 SSLEOFError egress 离散抖动家族, transient 非配置, 退避/重试有效。
- 30min fallback 0/104 = 0.0%; 全走主链; 无 BUFFER-EXHAUSTED/WAIT-/KEYMANAGER 堆积日志。
- /health 实测: 40006 nv_gw 200, 4101 cc4101 200; docker ps 实测 nv_gw Up 17h, cc4101 Up 17h。

### 本轮数据

| 指标 | 值 | 状态 |
|---|---|---|
| 主 nv_gw(40006) cc4101-primary | **103/103 = 100% SR, 0 bad** | ✅ 连续第 3 轮全 clean |
| per-caller 归属 | 主链 0 bad; hermes 2 bad (502/IncompleteRead/zombie) 均 out-of-scope | ✅ |
| per-key 健康 | 5 key 全 pexec_success; k3 2 次 transient RD 部分补回 | ✅ |
| 30min fallback | 0/104 = 0.0%, 全走主链 | ✅ |
| buffer | req 1 次 k4 RD 自愈补回; 无 EXHAUSTED/WAIT | ✅ |
| 容器 /health | 40006/4101 全 200; nv_gw Up 17h, cc4101 Up 17h | ✅ |

## 下一步
- 保持 NOP 观察。主链连续 3 轮全 clean, 外层 hermes 2 bad 为独立 caller 问题不属主链;
  buffer 自愈证明退避/重试机制对离散 egress 抖动有效。
- 仅当主链出现**持续分布**错误 (多 key 连续多轮非 pexec_success) 或单 key 连续多轮 100% 失败才介入
  (换 KEY_FID_BIND / 查 egress IP / mihomo 代理线路 7900-7904), 当前无需动作。

## 参数快照 (未动, 与上轮 R1083 一致)
- cc4101: PRIMARY_UPSTREAM_URL=http://nv_gw:40006/v1/messages, PRIMARY_UPSTREAM_MODEL=dsv4f0731_nv,
  FALLBACK_UPSTREAM_URL=http://ms_gw:40007/v1/chat/completions, FALLBACK_UPSTREAM_MODEL=glm5_2_ms,
  CC4101_STREAM_TOTAL_DEADLINE_S=470, PRIMARY_HEADER_TIMEOUT=400, CC4101_PRIMARY_FAIL_THRESHOLD=3, CC4101_PRIMARY_SKIP_S=30,
  UPSTREAM_TIMEOUT=130, UPSTREAM_IDLE_TIMEOUT=150
- nv_gw: NVU_DISABLE_MS_FALLBACK=0, NVU_PEER_FB_SKIP_MODELS=glm5_2_nv,dsv4p_nv, UPSTREAM_TIMEOUT=90,
  NV_INTEGRATE_KEY_COOLDOWN_S=90, KEY_COOLDOWN_S=30, NVU_FORCE_STREAM_UPGRADE=0, NVU_FORCE_STREAM_UPGRADE_TIMEOUT=150,
  TIER_TIMEOUT_BUDGET_S=180, TIER_COOLDOWN_S=180, MIN_OUTBOUND_INTERVAL_S=10,
  NVU_BUFFER_CALLERS=cc4101-primary,openclaw2, NVU_CALLER_KEY_MAP=hermes:2;openclaw:3;opencode:4
- Buffer 5 attempts × 90s = 450s; KeyManager 429→120-600s 指数退避, RemoteDisconnected→5-10s 短惩罚
