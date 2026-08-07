# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: **R1078 (NOP 巡检轮/不改码 — cc2 主链 110/111=99.1%, 1 bad transient; fallback 0; 该 1 bad 同签名 SSLEOFError egress 离散抖动, 已自愈 20:20:30 后全恢复 110×200 clean)**
> cc4101-primary (主 nv_gw:40006) 实测 30min = **110/111 = 99.1% SR, 1 bad (buffer_exhausted 502, avg_dur 62796ms)**;
> 该 1 bad = 与 R1077 完全相同签名的 transient **SSLEOFError `UNEXPECTED_EOF_WHILE_READING`** (`c107bc7e` 20:19 残迹) 多 key egress 抖动,
> AKE fail-fast 正确触发 (省 180s WaitQueue, state CLOSED), ms_gw fallback 未接管 (time-locked 同窗口) → 报 502 给 CC;
> **20:20:30 后 nv_gw 0 SSLEOFError / 0 buffer / 0 wait, 后续全 attempt=1 success** — 已自愈, 非配置漂移, 无参数可调 (故障在上游 TLS egress);
> fallback 0 次 / 0.0%; per-key 0/2/3/4 pexec_success, key1 19+1 RemoteDisconnected (常态单键) 后恢复;
> 容器 (/health 复核): nv_gw Up 17h, cc4101 Up 17h, 40006/4101 全 200
> 上轮: R1077 (NOP, 主链 102/103=99.0%, 1 transient SSLEOFError)

## 本轮 (R1078) 改动 + 依据 + 验证

### 改动: 无 (NOP。连续 2 轮 R1077+R1078 各 1 bad 均同签名 transient SSLEOFError egress 离散抖动, 已自愈 20:20:30 后全 clean; 故障在上游 TLS egress, 超出 nv_gw 参数调整范围, 无配置漂移)

### 依据 (注入轮前链路分析 20:28 CST + nv_gw 30min 日志根因复核 + 容器 /health 复核 2026-08-07)

- **30min cc4101-primary (主 nv_gw:40006) = 110/111 = 99.1% SR, 1 bad** (buffer_exhausted 502, avg_dur 62796ms)。
- dsv4f0731_nv 整体 SR=99.3% (150/151); 错误分类 buffer_exhausted×1 + zombie_empty_completion×1 (参考); hermes 40×200+1×502 out-of-scope。
- **根因复核 (nv_gw 30min 日志)**: `2d088060`@20:15 + `c107bc7e`@20:19 2 个同签名 transient buffer_exhausted,
  均 SSLEOFError `UNEXPECTED_EOF_WHILE_READING` 依次命中 k3/k5→k1→k2; 3 次 consecutive all_keys_exhausted 触发
  **AKE fail-fast** (`c107bc7e`@20:19:55, skip WaitQueue 省 180s, state CLOSED) → ms_gw fallback time-locked 未接管 → 报错给 CC。
- **AKE fail-fast + buffer 超时链工作完全符合设计**: 60s 内 fail-fast 释放, 未浪费 450s buffer 预算。
- **20:20:30 后 nv_gw 再 0 条 SSLEOFError / 0 buffer / 0 wait 活动**, 后续全部 attempt=1 success —— 已自愈, 与 R1077 模式一致。
- 30min fallback 0 次 (0.0%); per-key 0/2/3/4 pexec_success, key1 19 success + 1 NVCFPexecRemoteDisconnected (常态单键抖动)。
- /health 实测: 40006 nv_gw 200, 4101 cc4101 200; 容器 nv_gw Up 17h, cc4101 Up 17h.

### 本轮数据

| 指标 | 值 | 状态 |
|---|---|---|
| 主 nv_gw(40006) cc4101-primary | **110/111 = 99.1% SR, 1 bad** (buffer_exhausted) | ⚠️ root-caused transient |
| 30min fallback | 0 次 (0.0%), 全走主链 | ✅ |
| dsv4f0731_nv 整体 | 150/151 = 99.3% (zombie 作参考) | ✅ |
| 错误分类 | buffer_exhausted×1 (root-cause=SSLEOFError egress 抖动) | ✅ 已自愈 |
| per-key | 0/2/3/4 pexec_success; key1 19+1 RemoteDisconnected 后恢复 | ✅ |
| buffer 日志 | 20:20:30 后 0 SSLEOF / 0 buffer / 0 wait, 全 attempt=1 success | ✅ |
| 容器 /health | 40006/4101 全 200; nv_gw Up 17h, cc4101 Up 17h | ✅ |

## 下一步
- 保持 NOP 观察。本轮 1 bad 为同签名 transient SSLEOFError egress 离散抖动 (故障在上游 TLS 连接中断), 已自愈, 非配置漂移, 无参数可调。
- 仅当 SSLEOFError 复现且呈**持续分布** (非单次离散抖动) 才查 egress IP / mihomo 代理线路健康 (7900-7904), 属 dsv4f0731_nv 链路 / 宿主链路问题, 超出 nv_gw 调整范围。
- 单 key 连续多轮 100% 失败才考虑 KEY_FID_BIND 换 fid; 当前 key1 单次抖动后恢复, 无需动作。

## 参数快照 (未动, 与上轮 R1077 一致)
- cc4101: PRIMARY_UPSTREAM_URL=http://nv_gw:40006/v1/messages, PRIMARY_UPSTREAM_MODEL=dsv4f0731_nv,
  FALLBACK_UPSTREAM_URL=http://ms_gw:40007/v1/chat/completions, FALLBACK_UPSTREAM_MODEL=glm5_2_ms,
  CC4101_STREAM_TOTAL_DEADLINE_S=470, PRIMARY_HEADER_TIMEOUT=400, CC4101_PRIMARY_FAIL_THRESHOLD=3, CC4101_PRIMARY_SKIP_S=30,
  UPSTREAM_TIMEOUT=130, UPSTREAM_IDLE_TIMEOUT=150
- nv_gw: NVU_DISABLE_MS_FALLBACK=0, NVU_PEER_FB_SKIP_MODELS=glm5_2_nv,dsv4p_nv, UPSTREAM_TIMEOUT=90,
  NV_INTEGRATE_KEY_COOLDOWN_S=90, KEY_COOLDOWN_S=30, NVU_FORCE_STREAM_UPGRADE=0, NVU_FORCE_STREAM_UPGRADE_TIMEOUT=150,
  TIER_TIMEOUT_BUDGET_S=180, TIER_COOLDOWN_S=180, MIN_OUTBOUND_INTERVAL_S=10,
  NVU_BUFFER_CALLERS=cc4101-primary,openclaw2, NVU_CALLER_KEY_MAP=hermes:2;openclaw:3;opencode:4
- Buffer 5 attempts × 90s = 450s; KeyManager 429→120-600s 指数退避, RemoteDisconnected→5-10s 短惩罚