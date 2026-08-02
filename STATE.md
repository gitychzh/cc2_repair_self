# R534 — NOP 巡检轮 (2026-08-03 07:21 CST)

## 摘要
- 0 改动 0 restart. NOP 接棒巡检轮 (延续 R525-R533 间歇空闲窗口).
- cc2 (cc4101-primary) 30min 0 req (session 间歇空闲, 无 cc2 评估样本, 铁律1 cc2 视角不满足 → 不动码).
- dsv4p_nv 30min: 15 req SR=60.0% (9×200 + 4×429 + 2×502), 全 `hermes` caller (1× openclaw 200).
  SR 较 R533 的 64.3% 略降 4pct, 仍在 NVCF 侧配额波动区间 (40-65% band, R530-R533).
- 唯一错误类型 `all_tiers_exhausted` × 6 (avg 18.8s), 无新错误类型.
- 2× 502 = peer-fb-skip 已知路径 (07:02 + 07:17 UTC), R530 同源, 非新错误.
  (R533 下一步阈值 >=3/h 评估, 本轮 4/h 跨阈值, 但 502 是 dsv4p_nv 在 peer-fb-skip list 的设计行为,
   且 cc2 0 流量无法评估 buffer 路径 → 维持 NOP, 仅标记观察.)
- NV-GLOBAL-COOLDOWN tier=dsv4p_nv 周期性 429 仍在 (22:55/23:05/23:10/23:20 UTC),
  与 R268-R533 完全一致, NVCF 侧配额波动.
- 无 stream_total_deadline, 无 zombie_empty_completion, 无 buffer/wait 日志 (dsv4p_nv 在 peer-fb-skip,
  nv_gw 层裸返不走 buffer), deadline 链对齐 OK.
- 配置实测与 R475-R533 完全一致, 无漂移.

## 本轮改动
- 无 (NOP). 铁律1 cc2 视角不满足 (cc2 0 流量无评估样本) → 不动码.
- dsv4p_nv 错误模式与 R268-R533 完全一致 (周期性 all_tiers_exhausted + NVCF 侧 429 配额波动 +
  peer-fb-skip 502), 非 nv_gw 代码问题.

## 依据
- cc2 30min 0 req → 无 cc2 评估样本 (铁律1 cc2 视角不满足)
- dsv4p_nv 15 req: 9×200 (k2=8 + k3=1, 23:01/23:04/23:16 UTC 恢复窗口, 8.3s avg dur) +
  4×429 (每 5min 1 次 GLOBAL-COOLDOWN 180s) + 2×502 (peer-fb-skip, 07:02 + 07:17)
- 唯一错误类型: `all_tiers_exhausted` × 6, avg_dur=18.8s (全 NVCF 配额型, 非 nv_gw 故障)
- per-key (dsv4p): k2=8×200 (9022ms avg), k3=1×200 (2408ms), 其余 key 全 429 (无成功)
- per-egress-IP: 203.10.96.139=8×100% SR, 134.195.101.194=1×100% SR, 其余 IP 0 success (6×429/502)
- 200 finish_reason: tool_calls × 8, stop × 1 (无 zombie)
- fallback_occurred=f × 15 (nv_gw 层 dsv4p_nv 不 fallback, cc4101 层兜底)
- 全局冷却模式: 每 5min 1 次 NV-GLOBAL-COOLDOWN tier=dsv4p_nv all keys 429,
  与 R268-R533 完全一致, 是 NVCF 侧配额波动, 非 nv_gw 故障
- nv_tier_attempts 0 行 = 429 在 tier 层前被 KeyManager 全局冷却拦截, 历史一致行为
- 502 peer-fb-skip × 2 (4/h 跨 R533 阈值 3/h, 但属设计行为 + cc2 0 流量无法评估 → 维持 NOP)
- 无新错误类型 (仅 all_tiers_exhausted), 无 stream_total_deadline, deadline 链对齐 OK
- 配置无漂移 → 无参数回退必要

## 验证
- 0 restart → 无需 py_compile / curl 复测
- curl /health: status=ok, nv_num_keys=5, nv_default_model=glm5_2_nv,
  nvcf_pexec_models=[kimi_nv,dsv4p_nv,glm5_2_nv], port=40006
- docker ps: nv_gw Up 17h, nv_gw_stable Up 29h, cc4101 Up 7h, ms_gw Up 3 days, logs_db Up 3 days
- 配置实测与 R475-R533 完全一致, 无漂移

## Fallback 配置实测 (持续)
- `NVU_DISABLE_MS_FALLBACK=0` (ms fallback 启用, 但只覆盖 glm5_2_nv)
- `NVU_MS_FALLBACK_MODELS=glm5_2_nv` (ms fallback 不含 dsv4p_nv)
- `NVU_PEER_FB_SKIP_MODELS=glm5_2_nv,dsv4p_nv` (dsv4p_nv 跳过 peer fallback)
- → dsv4p_nv 全挂时 nv_gw 层裸返 429/502, 不走 ms/peer fallback
- cc4101 层 `FALLBACK_UPSTREAM_URL=ms_gw` + `FALLBACK_UPSTREAM_MODEL=glm5_2_ms` 兜底 cc2/hermes 请求

## 下一步
- 继续 NOP 巡检, 等 cc2 流量恢复后观察 dsv4p_nv buffer 路径行为 (当前 0 cc2 buffer 样本)
- 关注新错误类型 (非 all_tiers_exhausted/zombie/peer-fb-skip) 或 key/IP 级故障, 再决定是否介入
- 502 (peer-fb-skip) 跨 R533 阈值 4/h, 但属设计行为 + cc2 0 流量 → 仅标记观察, 不改码;
  若持续 >=6/h 且 cc2 流量恢复, 再评估 dsv4p_nv fallback 策略:
  (a) 将 dsv4p_nv 加入 `NVU_MS_FALLBACK_MODELS` 让 nv_gw 层也兜底, 或
  (b) 切换 `PRIMARY_UPSTREAM_MODEL` 回 glm5_2_nv, 或
  (c) 增加 ring fallback
- k3 53s RemoteDisconnected 传输挂死若频次上升再评估 (本轮 0 次, R530-R532 偶发 1 次)
- dsv4p_nv 小时级 SR 持续 <60% + cc2 缓冲流量恢复后再评估 buffer/KeyManager 参数
  (TIER_COOLDOWN_S 180s 是否过激)
- all_tiers_exhausted 持续 >=5/h 且中段不恢复 再评估 (本轮 12/h, 但全 NVCF 配额型, 维持观察)

## 参数快照 (本轮未改)
- nv_gw: NVU_DISABLE_MS_FALLBACK=0, UPSTREAM_TIMEOUT=90, TIER_TIMEOUT_BUDGET_S=180,
  TIER_COOLDOWN_S=180, KEY_COOLDOWN_S=30, NV_INTEGRATE_KEY_COOLDOWN_S=90,
  MIN_OUTBOUND_INTERVAL_S=10, NVU_FORCE_STREAM_UPGRADE=0,
  NVU_BUFFER_MAX_RETRIES=5, NVU_BUFFER_CALLERS=cc4101-primary,openclaw2,
  NVU_PEER_FB_SKIP_MODELS=glm5_2_nv,dsv4p_nv, NVU_MS_FALLBACK_MODELS=glm5_2_nv,
  NVU_CALLER_KEY_MAP=hermes:2;openclaw:3;opencode:4
- cc4101: FALLBACK_UPSTREAM_URL=http://ms_gw:40007/v1/chat/completions,
  FALLBACK_UPSTREAM_MODEL=glm5_2_ms, PRIMARY_UPSTREAM_MODEL=dsv4p_nv,
  PRIMARY_UPSTREAM_URL=http://nv_gw:40006/v1/messages,
  CC4101_STREAM_TOTAL_DEADLINE_S=470, PRIMARY_HEADER_TIMEOUT=400,
  CC4101_PRIMARY_SKIP_S=30, CC4101_PRIMARY_FAIL_THRESHOLD=3,
  UPSTREAM_TIMEOUT=130, UPSTREAM_IDLE_TIMEOUT=150
