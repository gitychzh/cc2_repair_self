# R525 — NOP 巡检轮 (2026-08-03 06:39 CST)

## 摘要
- 0 改动 0 restart. NOP 接棒巡检轮 (延续 R524 间歇空闲窗口).
- cc2 (cc4101-primary) 30min 0 req (session 间歇空闲, 无评估样本, 铁律1 不满足 → 不动码).
- dsv4p_nv 2h SR=40.5% (15/37: 15×200 + 21×429 + 1×502 zombie), 与 R510-R524 同窗口周期一致.
- 错误: all_tiers_exhausted ×21 (2h), zombie_empty_completion ×1 (2h, 低频).
- stream_total_deadline: 0 (6h, deadline 链对齐 OK).
- nv_tier_attempts 30min 0 行 (429 在 tier 层前被 KeyManager 全局冷却拦截).
- 配置实测确认与 R475-R524 完全一致, 无漂移.

## 本轮改动
- 无 (NOP). 铁律1 不满足 (cc2 0 流量无评估样本) → 不动码.

## 依据
- cc2 30min 0 req → 无评估样本, 改前无数据 (铁律1)
- 错误模式与 R268-R524 一致 (all_tiers_exhausted 周期性, 单次 429 触发全局冷却)
- dsv4p_nv 2h SR=40.5% = R510-R524 同窗口低谷, 非新故障
- zombie 502 仅 1 次/2h < 介入阈值 3/h → 不介入
- deadline 链 0 stream_total_deadline (6h) → 对齐 OK

## 验证
- 0 restart → 无需 py_compile / curl 复测
- curl /health: status=ok, nv_num_keys=5, nv_default_model=glm5_2_nv, port=40006
- docker ps: nv_gw Up 16h, cc4101 Up 6h, ms_gw Up 3 days, logs_db Up 3 days
- 配置实测与 R475-R524 完全一致, 无漂移

## 链路数据 (06:39 CST 实测)
### 2h 窗口 (全 caller, dsv4p_nv)
- 37 req: 15×200 + 21×429 + 1×502 (zombie_empty_completion)
- SR=40.5% (15/37)
- 30min 子窗口: 8 req 3×200 + 5×429 → SR=37.5% (与 R524 同窗口一致)

### cc4101-primary 专属 (cc2 的请求)
- 30min 0 req, 2h 0 req (session 间歇空闲)

### KeyManager 行为
- 30min 5×429 → 全局冷却 180s (TIER_COOLDOWN_S=180)
- nv_tier_attempts 0 行 = 429 在 tier 层前被 KeyManager 拦截 (历史一致行为)
- fallback: cc4101 层走 ms_gw glm5_2_ms, 链路有保障

## 下一步
- 继续 NOP 巡检, 等 cc2 流量恢复后观察 dsv4p_nv buffer 路径行为 (当前 0 buffer 样本)
- 关注新错误类型 (非 all_tiers_exhausted/zombie) 或 key/IP 级故障, 再决定是否介入
- dsv4p_nv 小时级 SR 持续 <60% + cc2 缓冲流量恢复后再评估切换 PRIMARY_UPSTREAM_MODEL 或增加 ring fallback
- all_tiers_exhausted 持续 >=5/h 且中段不恢复 再评估 buffer/KeyManager 参数 (TIER_COOLDOWN_S 180s 是否过激)
- zombie 502 再现 >=3/h 才介入 (当前 1 次/2h)
- zombie_empty_completion 频次 >=3/h 再评估 zombie 阈值 (当前 content+reasoning<50)

## 参数快照 (本轮未改)
- nv_gw: NVU_DISABLE_MS_FALLBACK=0, UPSTREAM_TIMEOUT=90, TIER_TIMEOUT_BUDGET_S=180,
  TIER_COOLDOWN_S=180, KEY_COOLDOWN_S=30, NV_INTEGRATE_KEY_COOLDOWN_S=90,
  MIN_OUTBOUND_INTERVAL_S=10, NVU_FORCE_STREAM_UPGRADE=0,
  NVU_BUFFER_CALLERS=cc4101-primary,openclaw2, NVU_PEER_FB_SKIP_MODELS=glm5_2_nv,dsv4p_nv,
  NVU_CALLER_KEY_MAP=hermes:2;openclaw:3;opencode:4,
  NVU_BUFFER_MAX_RETRIES=5, NVU_BUFFER_TIMEOUT_STAIRS=90,90,90,90,90,
  NVU_BUFFER_TOTAL_DEADLINE_S=450, NVU_BUFFER_PING_INTERVAL_S=30, NVU_STREAM_FULL_BUFFER=0,
  NVU_KEYMGR_429_BASE_COOLDOWN=120, NVU_KEYMGR_429_MAX_COOLDOWN=600,
  NVU_KEYMGR_CONN_BASE_COOLDOWN=30, NVU_KEYMGR_CONN_FAIL_THRESHOLD=3,
  NVU_KEYMGR_CONN_LONG_COOLDOWN=120, NVU_KEYMGR_CONN_MAX_COOLDOWN=60
- cc4101: PRIMARY_UPSTREAM_MODEL=dsv4p_nv, PRIMARY_UPSTREAM_URL=http://nv_gw:40006/v1/messages,
  FALLBACK_UPSTREAM_URL=http://ms_gw:40007/v1/chat/completions, FALLBACK_UPSTREAM_MODEL=glm5_2_ms,
  PRIMARY_HEADER_TIMEOUT=400, CC4101_STREAM_TOTAL_DEADLINE_S=470,
  CC4101_PRIMARY_FAIL_THRESHOLD=3, CC4101_PRIMARY_SKIP_S=30,
  UPSTREAM_TIMEOUT=130, UPSTREAM_IDLE_TIMEOUT=150
- deadline 链: 90s/attempt × 5 = 450s buffer < 470s cc4101 < 500s SDK idle
- settings.json: contextWindow=170000, autoCompactWindow=155000, API_TIMEOUT_MS=600000
