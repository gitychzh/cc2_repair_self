# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: **R1082 (NOP 巡检轮/不改码 — cc2 主链 107/108=99.1%, 1 bad transient; fallback 0; 该 1 bad 同签名 SSLEOFError egress 离散抖动, 自愈 20:19:55 后最近 28min 104/104=100% clean)**
> cc4101-primary (主 nv_gw:40006) 实测 30min = **107/108 = 99.1% SR, 1 bad (buffer_exhausted 502, 完成态 20:19:55, 与 R1081 同瞬时)**
> 该 1 bad = 与 R1077~R1081 完全相同签名的 transient **SSLEOFError `UNEXPECTED_EOF_WHILE_READING`** 多 key egress 离散抖动,
> AKE fail-fast 正确触发 (省 WaitQueue), ms_gw fallback time-locked 未接管 → 报 502 给 CC;
> **20:19:55 后全 clean**: 最近 28min 主链 **104/104 = 100%**, 零坏 — 已自愈, 非配置漂移, 无参数可调 (故障在上游 TLS egress);
> per-caller 归属铁证: NVStream_IncompleteRead+zombie 2 bad 全归 hermes (out-of-scope), 主链仅 1 bad;
> fallback 0 次 / 0.0%; buffer 实时流 20:49 全 attempt=1 success_tool_call 6-9s, 无耗尽/等待;
> 容器 (/health 复核): nv_gw Up 17h, cc4101 Up 17h, 40006/4101 全 200
> 上轮: R1081 (NOP, 主链 105/106=99.1%, 1 transient SSLEOFError)

## 本轮 (R1082) 改动 + 依据 + 验证

### 改动: 无 (NOP。连续 6 轮 R1077~R1082 各 1 bad 均同签名 transient SSLEOFError egress 离散抖动, 自愈 20:19:55 后最近 28min 104/104=100%; 故障在上游 TLS egress, 超出 nv_gw 参数调整范围, 无配置漂移)

### 依据 (注入轮前链路分析 20:48 CST + 本轮 DB 复核 20:50 + buffer 实时流 + 容器 /health 复核 2026-08-07)

- **30min cc4101-primary (主 nv_gw:40006) = 107/108 = 99.1% SR, 1 bad** (buffer_exhausted 502, 完成态 12:19:55 UTC / 20:19:55 CST, 与 R1081 同瞬时)。
- **per-caller 归属铁证**: 错误分类表 NVStream_IncompleteRead×1 (12:40 UTC) + zombie_empty_completion×1 (12:39 UTC)
  经 `GROUP BY caller` 复核 **全归 hermes**, out-of-scope; cc4101-primary 仅有 buffer_exhausted×1。
- **DB 错误时间线复核**: 唯一主链 502 buffer_exhausted 完成态 **20:19:55 CST**, 此后全 200, 零坏。
- **自愈复核**: 最近 28min 主链 **104/104 = 100%** (含本轮实时 20:49 buffer 流), 已完全恢复, 与 R1077~R1081 模式一致。
- **buffer 实时流**: 20:49 CST 日志全部 attempt=1 verdict=success_tool_call, elapsed 6-9s, 无 BUFFER-EXHAUSTED/WAIT-/KEYMANAGER 事件。
- 30min fallback 0/111 = 0.0%; 全走主链。
- /health 实测: 40006 nv_gw 200, 4101 cc4101 200; docker ps 实测 nv_gw Up 17h, cc4101 Up 17h。

### 本轮数据

| 指标 | 值 | 状态 |
|---|---|---|
| 主 nv_gw(40006) cc4101-primary | **107/108 = 99.1% SR, 1 bad** (buffer_exhausted) | ⚠️ root-caused transient |
| per-caller 归属 | 主链 1 bad; hermes 2 bad (IncompleteRead/zombie) 均 out-of-scope | ✅ |
| 错误时间线 | 唯一主链 502 完成态 20:19:55; 此后全 200 | ✅ |
| 最近 28min | 104/104 = 100% | ✅ 已自愈 |
| 30min fallback | 0 次 (0.0%), 全走主链 | ✅ |
| buffer 实时流 | attempt=1 success, 6-9s, 无耗尽/等待 | ✅ |
| 容器 /health | 40006/4101 全 200; nv_gw Up 17h, cc4101 Up 17h | ✅ |

## 下一步
- 保持 NOP 观察。连续 6 轮 (R1077-R1082) 同签名单 bad, 均为同一瞬时的 egress 离散抖动周期 (故障在上游 TLS 连接中断), 已自愈, 非配置漂移, 无参数可调。
- 仅当 SSLEOFError 复现且呈**持续分布** (非单次离散抖动) 才查 egress IP / mihomo 代理线路健康 (7900-7904), 属 dsv4f0731_nv 链路 / 宿主链路问题, 超出 nv_gw 调整范围。
- 单 key 连续多轮 100% 失败才考虑 KEY_FID_BIND 换 fid; 当前 key1 单次抖动后恢复, 无需动作。

## 参数快照 (未动, 与上轮 R1081 一致)
- cc4101: PRIMARY_UPSTREAM_URL=http://nv_gw:40006/v1/messages, PRIMARY_UPSTREAM_MODEL=dsv4f0731_nv,
  FALLBACK_UPSTREAM_URL=http://ms_gw:40007/v1/chat/completions, FALLBACK_UPSTREAM_MODEL=glm5_2_ms,
  CC4101_STREAM_TOTAL_DEADLINE_S=470, PRIMARY_HEADER_TIMEOUT=400, CC4101_PRIMARY_FAIL_THRESHOLD=3, CC4101_PRIMARY_SKIP_S=30,
  UPSTREAM_TIMEOUT=130, UPSTREAM_IDLE_TIMEOUT=150
- nv_gw: NVU_DISABLE_MS_FALLBACK=0, NVU_PEER_FB_SKIP_MODELS=glm5_2_nv,dsv4p_nv, UPSTREAM_TIMEOUT=90,
  NV_INTEGRATE_KEY_COOLDOWN_S=90, KEY_COOLDOWN_S=30, NVU_FORCE_STREAM_UPGRADE=0, NVU_FORCE_STREAM_UPGRADE_TIMEOUT=150,
  TIER_TIMEOUT_BUDGET_S=180, TIER_COOLDOWN_S=180, MIN_OUTBOUND_INTERVAL_S=10,
  NVU_BUFFER_CALLERS=cc4101-primary,openclaw2, NVU_CALLER_KEY_MAP=hermes:2;openclaw:3;opencode:4
- Buffer 5 attempts × 90s = 450s; KeyManager 429→120-600s 指数退避, RemoteDisconnected→5-10s 短惩罚