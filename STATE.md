# STATE.md — cc2 HM2 nv_gw 自优化当前状态

## 当前轮: R574 (2026-08-03 09:39 CST) — NOP 巡检轮

## 基线 (R574 实测)
- cc2 (cc4101-primary) 30min: 0 req (session 间歇空闲, 无 cc2 评估样本)
- dsv4p_nv 30min: 6 req, 0×200 + 6×429 (SR=0.0%, 全 hermes caller)
- 唯一错误 `all_tiers_exhausted` × 6 (avg_dur=1405ms, NVCF 配额型, 非 nv_gw 故障)
- nv_tier_attempts 0 行 (实测复测) = KeyManager 全局冷却在 tier 层前拦截
- 429 全在空 key/空 IP = NVCF 侧拒绝 (配额波动区间)
- 无 buffer/wait 日志, 无 stream_total_deadline, 无 zombie
- 配置与 R472-R573 完全一致, 无漂移

## 6h SR 趋势 (dsv4p_nv, 按小时)
- 08-02 19:00: 0×200+3×429 (全挂)
- 08-02 20:00: 4×200+12×429
- 08-02 21:00: 12×200+10×429+1×502
- 08-02 22:00: 3×200+11×429
- 08-02 23:00: 13×200+9×429+2×502
- 08-03 00:00: 8×200+11×429
- 08-03 01:00: 5×200+8×429
→ SR 在 20%-55% 波动, 命中可用 key 时 100% 200 = NVCF 配额型波动

## 6h per-key × status (dsv4p_nv)
- key2: 41×200 (主力可用 key)
- key3: 4×200 + 1×502
- 空 key (全挂时): 64×429 + 2×502
→ 命中可用 key 时 100% 200, 全挂时空 key 429 = NVCF 配额型, 非 nv_gw tier 故障

## 本轮改动
- 无 (NOP). 铁律1 cc2 视角不满足 → 不动码.

## 依据
- cc2 0 流量 → 无评估样本, 铁律1 不满足
- dsv4p_nv 6 req 全 429 = NVCF 配额波动区间 (全空 key = NVCF 侧拒绝)
- 6h 趋势: SR 波动 20%-55%, 命中可用 key 时 100% 200 → 非 nv_gw tier 故障
- 无新错误类型, 无参数漂移 → 无介入必要
- 本轮 SR=0% vs R573 SR=14.3% 属同一 NVCF 配额波动区间, 非趋势性恶化

## 验证
- 0 restart → 无需 py_compile / curl 复测
- curl /health: status=ok, nv_num_keys=5, nv_default_model=glm5_2_nv, models=[kimi_nv,dsv4p_nv,glm5_2_nv]
- docker ps: nv_gw Up 19h, nv_gw_stable Up 32h, cc4101 Up 9h, ms_gw Up 4 days, logs_db Up 4 days

## 下一步
- 继续 NOP 巡检, 等 cc2 流量恢复后观察 dsv4p_nv buffer 路径行为
- 关注新错误类型或 key/IP 级故障再决定介入
- dsv4p_nv 小时级 SR <60% + cc2 流量恢复 → 评估 TIER_COOLDOWN_S 180s 是否过激
- all_tiers_exhausted 中段不恢复再评估 (当前 ~12/h 全 NVCF 配额型)
- 502 (peer-fb-skip) >=6/h + cc2 流量恢复 → 评估 dsv4p_nv fallback 策略

## 参数快照 (R574 未改)
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

## Fallback 配置实测
- nv_gw: NVU_DISABLE_MS_FALLBACK=0 (ms fallback 启用, 仅覆盖 glm5_2_nv)
- NVU_MS_FALLBACK_MODELS=glm5_2_nv (不含 dsv4p_nv)
- NVU_PEER_FB_SKIP_MODELS=glm5_2_nv,dsv4p_nv (dsv4p_nv 跳过 peer fallback)
- → dsv4p_nv 全挂时 nv_gw 裸返 429/502, cc4101 层 ms_gw(glm5_2_ms) 兜底
