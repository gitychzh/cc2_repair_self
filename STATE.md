# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: **R1090 (NOP 巡检轮/不改码 — cc2 主链 93/94=98.9% SR, 1 bad=502 buffer_exhausted 历轮已知容器尾迹 (R1088 同 req=9baaf179), self-heal 复窗口全 200; per-key 全 pexec_success 零 tier 错误; fallback 0.0%)**
> cc4101-primary (主 nv_gw:40006) 实测 30min = **93/94 = 98.9% SR, 1 bad**
> — 单 bad (13:15:13 UTC req=9baaf179) 为 R1088 (21:15 CST) 已根因的 124K-token thinking 流多 US egress IP 瞬时
>   SSLEOFError transient blip 尾迹, **与 R1088/R1089 同一 request_id**, 非新错误; AKE fail-fast 截断走 ms_gw
> hermes 44×200 (SR=100.0%); 30min 错误分类仅此 1 项 (known bad)
> per-key 全 5 key 均 pexec_success (k0 16/k1 17/k2 18/k3 21/k4 20), **本轮零 tier 错误** (较 R1089 k3 2x transient RD 更干净);
> buffer 复窗口全部 attempt-1 success_tool_call 直 flush 秒回 (4-16s) 零 fail-fast 级联; 无冷却堆积; 无 WaitQueue;
> fallback 0/95 = 0.0%;
> 容器 (/health 复核): nv_gw 200 (passthrough, 5 key), cc4101 200, dsv4p_nv40066 200
> 上轮: R1089 (NOP, 主链 95/96=99.0% 1 transient bad 同根因)

## 本轮 (R1090) 改动 + 依据 + 验证

### 改动: 无 (NOP。93/94=98.9% 仅 1 bad 为 R1088 同根因 (req=9baaf179) 多 IP 瞬时 SSLEOF egress blip 尾迹, 历轮已知容器
### 尾迹号, 同一 request_id, 复窗口全 200, 无配置漂移, 无持续分布, 无参数可调)

### 依据 (轮前注入 21:29:33 CST + DB/日志复核 21:30-21:32 CST + 容器 /health 复核 2026-08-07)

- **30min cc4101-primary (主 nv_gw:40006) = 93/94 = 98.9% SR, 1 bad (502 buffer_exhausted 40665ms)**
- **唯一 bad 定位铁证**: `SELECT request_id,error_type,duration_ms,created_at WHERE status!=200 AND caller='cc4101-primary'
  AND created_at>now()-interval '60 min'` → **req=9baaf179, 502 buffer_exhausted, 40665ms, 13:15:13 UTC**。
  该 request_id 与 R1088/R1089 已根因的 req 完全一致 (124K thinking 流多 US egress IP 瞬时 SSLEOFError blip 尾迹),
  同一已知 historical bad, 无任何新签名 502。
- **self-heal 铁证**: 9baaf179 后无任何 status=502 新增; nv_gw buffer 日志 (--since 30m) 复窗口
  `ae00e936/1a5810cf/c9314851/26c49091/3f5c5ca5...` 全部 attempt=1 success_tool_call 直 flush 秒回 (4-16s),
  零 3-attempt fail-fast 级联, 零冷却堆积, 零 WaitQueue。
- **per-key 健康**: nv_tier_attempts(`created_at`) 30min 全 5 key 均高 pexec_success (k0 16/k1 17/k2 18/k3 21/k4 20),
  **零 tier 错误** (无 RD, 无 429, 无冷却堆积), 较 R1089 更干净。
- **30min fallback 0/95 = 0.0%** (bad 本身已计为 NV 非成功; 复窗口全走主链)。
- /health 实测: 40006 nv_gw 200 (passthrough, 5 key), 40066 dsv4p_nv40066 200。

### 本轮数据

| 指标 | 值 | 状态 |
|---|---|---|
| 主 nv_gw(40006) cc4101-primary | **93/94 = 98.9% SR, 1 bad** (R1088 同 req, 已根因) | ⚠️→self-heal 复窗口全200 |
| 30min 错误分类 | 仅 1× buffer_exhausted (历轮已知容器尾迹) | ✅ 非新错误 |
| per-caller 归属 | 主链 1 bad=known; hermes 44×200 0 bad | ✅ |
| per-key 健康 | 5 key 全 pexec_success (16-21/k); **零 tier 错误** | ✅ |
| 30min fallback | 0/95 = 0.0%, 复窗口全走主链 | ✅ |
| buffer | 复窗口全部 attempt-1 直flush success_tool_call 秒回(4-16s) | ✅ self-heal 正常 |
| 容器 /health | 40006/4101/40066 全 200 | ✅ |

## 下一步
- 保持 NOP 观察。本轮 1 transient 502 为 R1088/R1089 完全同一 req=9baaf179 (124K thinking 流瞬时 SSLEOF egress blip
  尾迹), AKE fail-fast + 复窗口 attempt-1 秒回证明 self-heal 机制健壮, 非配置漂移。
- 关注点: 若同一 egress IP (7894/7896/7897/7899/7901) 在未来 1-2h 多轮连续出现 SSLEOFError+缓冲重试
  (不再让 attempt-1 直flush), 才查该代理线路/mihomo 端口, 当前无需动作。
- 持续 clean ≥ 数轮后再评估是否需对 124K+ thinking 大流裁减 (buffer_exhausted 概率随 input 大小上升属模型/流特性, 非链路 bug)。

## 参数快照 (未动, 与上轮 R1089 一致)
- cc4101: PRIMARY_UPSTREAM_URL=http://nv_gw:40006/v1/messages, PRIMARY_UPSTREAM_MODEL=dsv4f0731_nv,
  FALLBACK_UPSTREAM_URL=http://ms_gw:40007/v1/chat/completions, FALLBACK_UPSTREAM_MODEL=glm5_2_ms,
  CC4101_STREAM_TOTAL_DEADLINE_S=470, PRIMARY_HEADER_TIMEOUT=400, CC4101_PRIMARY_FAIL_THRESHOLD=3, CC4101_PRIMARY_SKIP_S=30,
  UPSTREAM_TIMEOUT=130, UPSTREAM_IDLE_TIMEOUT=150
- nv_gw: NVU_DISABLE_MS_FALLBACK=0, NVU_PEER_FB_SKIP_MODELS=glm5_2_nv,dsv4p_nv, UPSTREAM_TIMEOUT=90,
  NV_INTEGRATE_KEY_COOLDOWN_S=90, KEY_COOLDOWN_S=30, NVU_FORCE_STREAM_UPGRADE=0, NVU_FORCE_STREAM_UPGRADE_TIMEOUT=150,
  TIER_TIMEOUT_BUDGET_S=180, TIER_COOLDOWN_S=180, MIN_OUTBOUND_INTERVAL_S=10,
  NVU_BUFFER_CALLERS=cc4101-primary,openclaw2, NVU_CALLER_KEY_MAP=hermes:2;openclaw:3;opencode:4
- Buffer 5 attempts × 90s = 450s; KeyManager 429→120-600s 指数退避, RemoteDisconnected→5-10s 短惩罚