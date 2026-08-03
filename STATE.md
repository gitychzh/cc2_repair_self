# R566 — NOP 巡检轮 (2026-08-03 09:12 CST)

## 摘要
- 0 改动 0 restart. NOP 接棒巡检轮 (延续 R525-R565 间歇空闲窗口).
- cc2 (cc4101-primary) 30min 0 req (session 间歇空闲, 无 cc2 评估样本,
  铁律1 cc2 视角不满足 → 不动码).
- dsv4p_nv 30min: 17 req, 12×200 + 5×429 (SR≈70.6%, 全 `hermes` caller).
  与 R565 (9×200+5×429) / R564 (9×200+5×429) 一致量级略升, 12×200 聚集在 00:51-01:06
  命中配额空隙, avg_dur=9175ms 稳定 (max=25392ms), 仍在 NVCF 配额波动区间, 非 nv_gw 侧新故障.
- 唯一错误类型 `all_tiers_exhausted` × 5 (avg_dur=2916ms, 与 R565 的 1893ms /
  R564 的 1893ms 同量级 — KeyManager 全局冷却在 tier 层前拦截,
  tier_attempts 0 行, 历史一致).
- 周期性 GLOBAL-COOLDOWN 180s 每 5min 1 次 (00:40/00:45/00:55/01:01/01:06),
  与 R268-R565 完全一致.
- 无 stream_total_deadline, 无 zombie_empty_completion, 无 buffer/wait 日志
  (dsv4p_nv 在 peer-fb-skip, nv_gw 层裸返不走 buffer), deadline 链对齐 OK.
- 配置实测与 R475-R565 完全一致, 无漂移.

## 本轮改动
- 无 (NOP). 铁律1 cc2 视角不满足 (cc2 0 流量无评估样本) → 不动码.

## 依据
- cc2 30min 0 req → 无 cc2 评估样本 (铁律1 cc2 视角不满足)
- dsv4p_nv 17 req: 12×200 + 5×429 (每 5min GLOBAL-COOLDOWN 180s 全挂, 末段配额空隙)
- 唯一错误类型: `all_tiers_exhausted` × 5, avg_dur=2916ms (全 NVCF 配额型, 非 nv_gw 故障)
- nv_tier_attempts 0 行 = 429 在 tier 层前被 KeyManager 全局冷却拦截, 历史一致
- per-key: key2=10×200, key3=2×200, 5×429 无 tier 命中 (全局冷却拦截, key 级未触发)
- per-egress-IP: 203.10.96.139=10×200, 134.195.101.194=2×100, 5×429 无 IP 标记
- 无新错误类型, 无 stream_total_deadline → 无参数回退必要
- 配置无漂移 → 无参数回退必要

## 验证
- 0 restart → 无需 py_compile / curl 复测
- curl /health: status=ok, nv_num_keys=5, nv_default_model=glm5_2_nv,
  nvcf_pexec_models=[kimi_nv,dsv4p_nv,glm5_2_nv], port=40006
- docker ps: nv_gw Up 19h, nv_gw_stable Up 31h, cc4101 Up 8h, ms_gw Up 3 days, logs_db Up 3 days
- 配置实测与 R475-R565 完全一致, 无漂移

## Fallback 配置实测 (持续)
- `NVU_DISABLE_MS_FALLBACK=0` (ms fallback 启用, 但只覆盖 glm5_2_nv)
- `NVU_MS_FALLBACK_MODELS=glm5_2_nv` (ms fallback 不含 dsv4p_nv)
- `NVU_PEER_FB_SKIP_MODELS=glm5_2_nv,dsv4p_nv` (dsv4p_nv 跳过 peer fallback)
- → dsv4p_nv 全挂时 nv_gw 层裸返 429/502, 不走 ms/peer fallback
- cc4101 层 `FALLBACK_UPSTREAM_URL=ms_gw` + `FALLBACK_UPSTREAM_MODEL=glm5_2_ms` 兜底

## 下一步
- 继续 NOP 巡检, 等 cc2 流量恢复后观察 dsv4p_nv buffer 路径行为 (当前 0 cc2 buffer 样本)
- 关注新错误类型 (非 all_tiers_exhausted/zombie/peer-fb-skip) 或 key/IP 级故障, 再决定是否介入
- dsv4p_nv 小时级 SR 持续 <60% + cc2 缓冲流量恢复后再评估 buffer/KeyManager 参数
  (TIER_COOLDOWN_S 180s 是否过激)
- all_tiers_exhausted 持续 >=5/h 且中段不恢复 再评估 (本轮 ~10/h, 但全 NVCF 配额型, 维持观察)
- 502 (peer-fb-skip) 持续 >=6/h 且 cc2 流量恢复, 再评估 dsv4p_nv fallback 策略:
  (a) 将 dsv4p_nv 加入 `NVU_MS_FALLBACK_MODELS`, 或
  (b) 切换 `PRIMARY_UPSTREAM_MODEL` 回 glm5_2_nv, 或
  (c) 增加 ring fallback

## 参数快照 (本轮未改)
- nv_gw: NVU_DISABLE_MS_FALLBACK=0, UPSTREAM_TIMEOUT=90, TIER_TIMEOUT_BUDGET_S=180,
  TIER_COOLDOWN_S=180, KEY_COOLDOWN_S=30, NV_INTEGRATE_KEY_COOLDOWN_S=90,
  MIN_OUTBOUND_INTERVAL_S=10, NVU_FORCE_STREAM_UPGRADE=0, NVU_FORCE_STREAM_UPGRADE_TIMEOUT=150,
  NVU_BUFFER_MAX_RETRIES=5, NVU_BUFFER_CALLERS=cc4101-primary,openclaw2,
  NVU_PEER_FB_SKIP_MODELS=glm5_2_nv,dsv4p_nv, NVU_MS_FALLBACK_MODELS=glm5_2_nv,
  NVU_CALLER_KEY_MAP=hermes:2;openclaw:3;opencode:4,
  NVU_BUFFER_TIMEOUT_STAIRS=90,90,90,90,90, NVU_BUFFER_TOTAL_DEADLINE_S=450,
  NVU_BUFFER_PING_INTERVAL_S=30
- cc4101: FALLBACK_UPSTREAM_URL=http://ms_gw:40007/v1/chat/completions,
  FALLBACK_UPSTREAM_MODEL=glm5_2_ms, PRIMARY_UPSTREAM_MODEL=dsv4p_nv,
  PRIMARY_UPSTREAM_URL=http://nv_gw:40006/v1/messages,
  CC4101_STREAM_TOTAL_DEADLINE_S=470, PRIMARY_HEADER_TIMEOUT=400,
  CC4101_PRIMARY_SKIP_S=30, CC4101_PRIMARY_FAIL_THRESHOLD=3,
  UPSTREAM_TIMEOUT=130, UPSTREAM_IDLE_TIMEOUT=150
