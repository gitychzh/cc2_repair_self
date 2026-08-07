# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: **R1087 (NOP 巡检轮/不改码 — cc2 主链 103/103=100% SR 全 clean 零坏, 连续第 6 轮; 30min 错误分类空; fallback 0.0%; buffer attempt-1 直flush 零重试; per-key 全 pexec_success 仅 k3 1x transient RD 补回)**
> cc4101-primary (主 nv_gw:40006) 实测 30min = **103/103 = 100% SR, 零 bad** — 连续第 6 轮全 clean
> (R1081 105/106 → R1082 107/108 → R1083 115/115 → R1084 103/103 → R1085 100/100 → R1086 100/100 → R1087 103/103), 无新错误, 无配置漂移
> dsv4f0731_nv 总 145 请求全 200 (SR=100.0%); 上轮 hermes 2 bad 已消 (30min 错误分类空), 零 bad 全空
> per-key 全 5 key 均 pexec_success (k0 21/k1 20/k2 21/k3 21/k4 20), 仅 k3 1 次 transient NVCFPexecRemoteDisconnected 已补回, 无冷却堆积;
> buffer 复窗口全部 attempt-1 success 直接 flush, 零重试零 EXHAUSTED/WAIT, 连续多轮零重试;
> fallback 0/145 = 0.0%; 无任何错误日志;
> 容器 (/health 复核): nv_gw 200, cc4101 200, 40006/4101 全 200
> 上轮: R1086 (NOP, 主链 100/100=100% 全 clean 零坏)

## 本轮 (R1087) 改动 + 依据 + 验证

### 改动: 无 (NOP。主链 103/103=100% 全 clean 零坏, 连续第 6 轮, 30min 错误分类空, 无 fallback, 无配置漂移; per-key 全 pexec_success 仅 k3 1x transient RD, buffer 零重试, 无参数可调)

### 依据 (轮前注入 21:12:33 CST + DB 复核 21:13 + 容器 /health 复核 2026-08-07)

- **30min cc4101-primary (主 nv_gw:40006) = 103/103 = 100% SR, 零 bad**
  DB 复核 `SELECT status,count(*) ... caller='cc4101-primary'` → 全 200, 0 非 200。连续第 6 轮全 clean。
- **30min 错误分类 (nv_requests status!=200)** → 空 (无任何错误)。上轮 hermes 2 bad 已消, 无堆积。
- **per-key 健康**: nv_tier_attempts(`created_at` 列) 全 5 key 均高 pexec_success (k0 21/k1 20/k2 21/k3 21/k4 20);
  仅 k3 1 次 NVCFPexecRemoteDisconnected (transient, 补回), 无冷却堆积, 无单 key 连续失败。
- **buffer 零重试铁证**: 复窗口全部 attempt=1/5 success_tool_call 直接 flush, 无 all_keys_exhausted、
  无重试、无 BUFFER-EXHAUSTED/WAIT-/KEYMANAGER 堆积日志。连续多轮零重试零抖动。
- 30min fallback 0/145 = 0.0%; 全走主链。
- /health 实测: 40006 nv_gw 200 (passthrough, 5 key), 4101 cc4101 200 (primary dsv4f0731_nv)。

### 本轮数据

| 指标 | 值 | 状态 |
|---|---|---|
| 主 nv_gw(40006) cc4101-primary | **103/103 = 100% SR, 0 bad** | ✅ 连续第 6 轮全 clean |
| 30min 错误分类 | 空 (无任何错误) | ✅ |
| per-caller 归属 | 主链 0 bad; hermes 0 bad (上轮 2 bad 已消) | ✅ |
| per-key 健康 | 5 key 全 pexec_success (20-21); k3 1 次 transient RD 补回 | ✅ |
| 30min fallback | 0/145 = 0.0%, 全走主链 | ✅ |
| buffer | 全部 attempt-1 直flush; 零重试/EXHAUSTED/WAIT, 连续多轮为零 | ✅ |
| 容器 /health | 40006/4101 全 200 | ✅ |

## 下一步
- 保持 NOP 观察。主链连续 6 轮全 clean, buffer 零重试零抖动, 退避/重试机制已连续多轮证稳。
- 仅当主链出现**持续分布**错误 (多 key 连续多轮非 pexec_success) 或单 key 连续多轮 100% 失败才介入
  (换 KEY_FID_BIND / 查 egress IP / mihomo 代理线路 7900-7904), 当前无需动作。

## 参数快照 (未动, 与上轮 R1086 一致)
- cc4101: PRIMARY_UPSTREAM_URL=http://nv_gw:40006/v1/messages, PRIMARY_UPSTREAM_MODEL=dsv4f0731_nv,
  FALLBACK_UPSTREAM_URL=http://ms_gw:40007/v1/chat/completions, FALLBACK_UPSTREAM_MODEL=glm5_2_ms,
  CC4101_STREAM_TOTAL_DEADLINE_S=470, PRIMARY_HEADER_TIMEOUT=400, CC4101_PRIMARY_FAIL_THRESHOLD=3, CC4101_PRIMARY_SKIP_S=30,
  UPSTREAM_TIMEOUT=130, UPSTREAM_IDLE_TIMEOUT=150
- nv_gw: NVU_DISABLE_MS_FALLBACK=0, NVU_PEER_FB_SKIP_MODELS=glm5_2_nv,dsv4p_nv, UPSTREAM_TIMEOUT=90,
  NV_INTEGRATE_KEY_COOLDOWN_S=90, KEY_COOLDOWN_S=30, NVU_FORCE_STREAM_UPGRADE=0, NVU_FORCE_STREAM_UPGRADE_TIMEOUT=150,
  TIER_TIMEOUT_BUDGET_S=180, TIER_COOLDOWN_S=180, MIN_OUTBOUND_INTERVAL_S=10,
  NVU_BUFFER_CALLERS=cc4101-primary,openclaw2, NVU_CALLER_KEY_MAP=hermes:2;openclaw:3;opencode:4
- Buffer 5 attempts × 90s = 450s; KeyManager 429→120-600s 指数退避, RemoteDisconnected→5-10s 短惩罚