# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: **R1076 (NOP 巡检轮/不改码 — cc2 主链 109/109=100% SR, 0 bad; fallback 0; 主链错误分类为空; 连续多轮达完全健康基线)**
> cc4101-primary (主 nv_gw:40006) 实测 30min = **109/109 = 100% SR, 0 bad**;
> dsv4f0731_nv 整体 SR=99.4% (171/172) — 1×zombie_empty_completion 属 hermes 越界宿主 40666, 非主链;
> 30min cc_requests (110 条) = fallback 0 次 / 0.0%, 全走主链;
> 错误分类: 主链为空 (无 zombie, 无 502, 无 timeout);
> per-key: 全 5 key pexec_success, key1 一次 NVCFPexecRemoteDisconnected 但随行 19 次 success (常态单键抖动);
> buffer 日志: 全 attempt=1 即 success (3-9s, input 66-68K tokens, tool_calls 正常), 无 fail/WAIT/KEYMGR;
> 容器 (/health 复核): nv_gw Up 21h, cc4101 Up 16h, /health 40006/40066/4101 全 200
> 上轮: R1075 (NOP, 主链 107/107=100%)

## 本轮 (R1076) 改动 + 依据 + 验证

### 改动: 无 (NOP。cc2 主链 109/109=100% 0 bad, 主链错误分类为空, 无参数可调; 唯一 1×zombie 为 hermes 越界宿主 40666, 非 cc2 范围)

### 依据 (注入轮前链路分析 20:17 CST + 独立 DB 复核 + 容器 /health 复核 2026-08-07)

- **30min cc4101-primary (主 nv_gw:40006) = 109/109 = 100% SR, 0 bad** (独立 psql 复核: nv_requests caller=cc4101-primary = 200|109, 0 error)。
- dsv4f0731_nv 整体 SR=99.4% (171/172) — 1 个 502 zombie_empty_completion (avg_dur 5428ms) 属 hermes 越界宿主 (非主链)。
- **主链错误分类为空** — 无 zombie, 无 502, 无 timeout。
- 30min cc_requests (110 条) = sr 100.0%, fallback 0 次 / 0.0%, 全走主链。
- per-key: 0/1/2/3/4 全 pexec_success (24/19+1/22/20/21), key1 一次 NVCFPexecRemoteDisconnected 后 19 次 success (常态单键抖动)。
- buffer 日志: 全 attempt=1 即 success_tool_call (3-9s, input 66-68K tokens), 无 fail/WAIT/KEYMGR。
- /health 实测: 40006/40066/4101 全 200; 容器 nv_gw Up 21h, cc4101 Up 16h.

### 本轮数据

| 指标 | 值 | 状态 |
|---|---|---|
| 主 nv_gw(40006) cc4101-primary | **109/109 = 100% SR, 0 bad** | ✅ |
| dsv4f0731_nv 整体 | 171/172 = 99.4% (1×zombie 作参考) | ✅ |
| 30min cc_requests | 110 条, fallback 0 次 (0.0%), 全走主链 | ✅ |
| psql 复核 | nv_requests caller=cc4101-primary = 200\|109 (0 error) | ✅ |
| per-key | 全 5 key pexec_success; key1 一次 RemoteDisconnected 后恢复 | ✅ |
| buffer 日志 | 全 attempt=1 success (3-9s), 无 fail/WAIT/KEYMGR | ✅ |
| 容器 | nv_gw Up 21h, cc4101 Up 16h; /health 40006/40066/4101 全 200 | ✅ |

## 下一步
- 保持 NOP 观察。主链连续多轮 0 bad 已抵达"完全健康基线"。
- 仅当 cc2 主链自身出现 bad 或 fallback > 约 10% 才行动; 本轮 1×zombie 为 hermes 越界宿主 (非主链), 不计入 cc2 范围。
- 单 key 连续多轮 100% 失败才考虑 KEY_FID_BIND 换 fid; 当前主链 fid 全 pexec_success, 无此需。

## 参数快照 (2026-08-07, 与上轮 R1075 一致, 未动)
- cc4101: PRIMARY_UPSTREAM_URL=http://nv_gw:40006/v1/messages, PRIMARY_UPSTREAM_MODEL=dsv4f0731_nv,
  FALLBACK_UPSTREAM_URL=http://ms_gw:40007/v1/chat/completions, FALLBACK_UPSTREAM_MODEL=glm5_2_ms,
  CC4101_STREAM_TOTAL_DEADLINE_S=470, PRIMARY_HEADER_TIMEOUT=400, CC4101_PRIMARY_FAIL_THRESHOLD=3, CC4101_PRIMARY_SKIP_S=30,
  UPSTREAM_TIMEOUT=130, UPSTREAM_IDLE_TIMEOUT=150
- nv_gw: NVU_DISABLE_MS_FALLBACK=0, NVU_PEER_FB_SKIP_MODELS=glm5_2_nv,dsv4p_nv, UPSTREAM_TIMEOUT=90,
  NV_INTEGRATE_KEY_COOLDOWN_S=90, KEY_COOLDOWN_S=30, NVU_FORCE_STREAM_UPGRADE=0, NVU_FORCE_STREAM_UPGRADE_TIMEOUT=150,
  TIER_TIMEOUT_BUDGET_S=180, TIER_COOLDOWN_S=180, MIN_OUTBOUND_INTERVAL_S=10,
  NVU_BUFFER_CALLERS=cc4101-primary,openclaw2, NVU_CALLER_KEY_MAP=hermes:2;openclaw:3;opencode:4
- Buffer 5 attempts × 90s = 450s; KeyManager 429→120-600s 指数退避, RemoteDisconnected→5-10s 短惩罚