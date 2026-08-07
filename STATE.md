# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: **R1094 (NOP 巡检轮/不改码 — cc2 主链 115/115=100.0% SR 零错误, 30min 0 bad 无 502; cc_requests 95/95=100% fallback 0.0%; 历史 90min 窗口仅 2 bad=c107bc7e/9baaf179 历轮已知同一 12-13 UTC 尾迹, 自 13:15 UTC 后零新增; per-key 全 pexec_success 仅 k2 1× 一次性 RD; buffer 全 attempt-1 直flush 5-11s 秒回, 唯一 k3 transient execute_failed 5s backoff attempt-2 自愈零级联; 容器全 200)**
> cc4101-primary (主 nv_gw:40006) 实测 30min = **94/94 = 100.0% SR, 0 bad** (hermes 21/21, 合计 115/115=100%)
> — **零 502, 零错误, 无任何新签名**
> cc_requests 真实 SR 95/95 = **100.0%**, fallback 0/95 = 0.0%
> 90min window 仅 2 bad 均为历轮已知: c107bc7e (12:19 UTC) + 9baaf179 (13:15 UTC, R1088~R1093 同 req)
>   → 自 13:15 UTC 9baaf179 后 status!=200 → **0 条新 502** (self-heal 零级联)
> tier 错误: 30min 全 key pexec_success, 唯一 k2 1× NVCFPexecRemoteDisconnected (一次性非分布)
> buffer 复窗口全 attempt-1 直flush 5-11s (535 行 BUFFER 日志), 唯一 rq=8ed96432 k3 execute_failed 5s backoff
>   → attempt-2 success_tool_call 23.9s flush (transient k3, 机制按设计自愈, 零 502) — 【本轮唯一注意点】
> 3h buffer_exhausted: 仍仅 R1093 已知 3 distinct req (ec39dd9b 11:02/c107bc7e 12:19/9baaf179 13:15), **本轮零新增**
> 容器 (/health 复核 2026-08-07 21:53 CST): nv_gw 200, cc4101 200, dsv4p_nv40066 200; nv_gw Up 18h, cc4101 Up 18h
> 上轮: R1093 (NOP, 主链 103/104=99.0% 1 bad 同根因)

## 本轮 (R1094) 改动 + 依据 + 验证

### 改动: 无 (NOP。30min 主链 115/115=100.0% 零错误零 fallback, 90min 窗口仅 2 bad = 历轮已知同一 12-13 UTC 尾迹
### (c107bc7e + 9baaf179), 自 13:15 UTC 后零新增, 无配置漂移, 无新签名。唯一 k3 一次性 execute_failed 已按 buffer
### 5s backoff 自愈, 属健康自愈行为, 无参数可调)

### 依据 (轮前注入 21:51:33 CST + DB/日志实测 2026-08-07 21:53 CST + 容器 /health 实测)

- **30min nv_requests = 115×200, 0 非200**: cc4101-primary 94×200 + hermes 21×200 = **115/115 = 100.0% SR**, 错误分类 `(0 rows)`。
- **cc_requests 真实 SR (含 fallback)**: 95/95 = **100.0%**, fallback 0/95 = **0.0%**。
- **90min 历史 bad 核对**: window 内仅 2× 502 buffer_exhausted — `c107bc7e` (12:19 UTC) + `9baaf179` (13:15 UTC),
  均为 **可追溯历轮已知 request_id** (R1093 已根因 3h 观察组成员)。无任何新签名 502。
- **self-heal 铁证**: `created_at>'2026-08-07 13:15:13 UTC' AND status!=200` → **0 条** (9baaf179 后零新增 502)。
- **tier 错误**: 30min 94× `pexec_success` + 唯一 1× k2 `NVCFPexecRemoteDisconnected` (一次性, 非分布, 历轮已知 transient 模式);
  **零持续 tier 错误**。
- **buffer 日志** (--since 30m, 535 行 BUFFER): 绝大多数 attempt-1 直 flush 5-11s (success_text / success_tool_call) 秒回。
  **唯一 retry 案例 req=8ed96432**: attempt-1 execute_failed (key=k3) → 5s backoff → attempt-2 success_tool_call 23.9s flush 3.2KB。
  → 一次性 k3 transient execute_failed, buffer 机制按设计 backoff 自愈, **未产生 502, 零级联**。这是本轮唯一非 attempt-1 直通案例,
  但结果健康 (自愈成功), 不构成回归。
- **3h buffer_exhausted 类级复现观察**: 3h 窗口仍仅 R1093 已知 3 distinct req — `ec39dd9b` (11:02, 58.9s)、`c107bc7e` (12:19, 62.8s)、
  `9baaf179` (13:15, 40.7s)。**本轮零新增**, 维持 ~1/h 低频类事件观察, 未衰减未加剧。**列为下一轮监测信号, 本轮不改**
  (SR 100%, fallback 0%, buffer 自愈 100%)。
- 容器 /health 实测 2026-08-07 21:53 CST: 40006 nv_gw 200, 4101 cc4101 200, 40066 dsv4p_nv40066 200。

### 本轮数据

| 指标 | 值 | 状态 |
|---|---|---|
| 主 nv_gw(40006) 30min | cc4101-primary 94/94 + hermes 21/21 = **115/115 = 100.0% SR, 0 bad** | ✅ 全绿 |
| 30min 错误分类 | `(0 rows)` — **零错误** | ✅ |
| cc_requests 真实 SR | 95/95 = 100.0%, fallback 0/95 = 0.0% | ✅ |
| 90min 历史 bad | 仅 c107bc7e + 9baaf179 (历轮已知 12-13 UTC 尾迹), 自 13:15 后零新增 | ✅ self-heal |
| per-key / tier 错误 | 5 key 全 pexec_success; 唯一 k2 1× 一次性 RD | ✅ 零持续 tier 错误 |
| buffer | 全 attempt-1 直flush 5-11s; 唯一 rq=8ed96432 k3 retry 5s backoff → attempt-2 自愈 | ✅ healthy (无 502) |
| 3h buffer_exhausted | 仍仅 3 distinct req (ec39dd9b/c107bc7e/9baaf179), 本轮零新增 | ⚠️ 监测, 不改 |
| 容器 /health | 40006/4101/40066 全 200; nv_gw Up 18h, cc4101 Up 18h | ✅ |

## 下一步
- 保持 NOP 观察。本轮 30min 全绿 100%, 唯一注意点是 req=8ed96432 的 k3 一次性 execute_failed — 已按 buffer 5s backoff 自愈,
  属机制设计内健康自愈, 非回归。若未来 k3 连续多次 execute_failed 不再 attempt-2 恢复, 才查 k3 对应 mihomo 代理线 (态 7896)。
- **3h buffer_exhausted ~1/h 类级复现观察保持**: 本轮零新增, 3 distinct req 均为 12-13 UTC 时段 (午前高峰) 已知尾迹。
  若未来轮次新 distinct req 持续以 ~1/h 繁殖且 SR 开始跌破 99%, 再评估: ① 超大 input (~124K+) thinking 流 skip buffer 直通;
  ② 放大 NVU_BUFFER_TIMEOUT_STAIRS 末级预算。本轮不动作。
- 若 egress IP (代理线路) 多轮连续失败不再 attempt-1 直flush, 才查该 mihomo 代理端口。

## 参数快照 (未动, 与上轮 R1093 一致)
- cc4101: PRIMARY_UPSTREAM_URL=http://nv_gw:40006/v1/messages, PRIMARY_UPSTREAM_MODEL=dsv4f0731_nv,
  FALLBACK_UPSTREAM_URL=http://ms_gw:40007/v1/chat/completions, FALLBACK_UPSTREAM_MODEL=glm5_2_ms,
  CC4101_STREAM_TOTAL_DEADLINE_S=470, PRIMARY_HEADER_TIMEOUT=400, CC4101_PRIMARY_FAIL_THRESHOLD=3, CC4101_PRIMARY_SKIP_S=30,
  UPSTREAM_TIMEOUT=130, UPSTREAM_IDLE_TIMEOUT=150
- nv_gw: NVU_DISABLE_MS_FALLBACK=0, NVU_PEER_FB_SKIP_MODELS=glm5_2_nv,dsv4p_nv, UPSTREAM_TIMEOUT=90,
  NV_INTEGRATE_KEY_COOLDOWN_S=90, KEY_COOLDOWN_S=30, NVU_FORCE_STREAM_UPGRADE=0, NVU_FORCE_STREAM_UPGRADE_TIMEOUT=150,
  TIER_TIMEOUT_BUDGET_S=180, TIER_COOLDOWN_S=180, MIN_OUTBOUND_INTERVAL_S=10,
  NVU_BUFFER_CALLERS=cc4101-primary,openclaw2, NVU_CALLER_KEY_MAP=hermes:2;openclaw:3;opencode:4
- Buffer 5 attempts × 90s = 450s (NVU_BUFFER_MAX_RETRIES=5, NVU_BUFFER_TIMEOUT_STAIRS=90,90,90,90,90);
  KeyManager 429→120-600s 指数退避, RemoteDisconnected→5-10s 短惩罚