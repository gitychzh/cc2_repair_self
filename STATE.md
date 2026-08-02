# R483 — NOP 巡检轮 (2026-08-03 04:30 CST)

## 摘要
- 0 改动 0 restart. NOP 巡检轮.
- 数据窗口 19:50-20:15 UTC (04:19 CST 注入), 与 R475-R482 同低谷窗口高度一致 (连续 9 轮锁定 0-15%).
- cc2 (cc4101-primary) 30min 0 req (psql 复测确认 0 rows, cc2 session 间歇空闲, 无评估样本, 铁律1 不满足 → 不动码).
- dsv4p_nv 全 caller 30min SR=14.3% (1/7, 1×200 + 6×429), 与 R482 完全持平, 仍处低谷窗口.
- 错误: all_tiers_exhausted ×6 (sub=all_tiers_failed_in_mapped_tier), 与 R268-R482 (173+ 轮) 一致, 无新错误.
- nv_tier_attempts 30min 0 行 (429 在 tier 层前被 KeyManager 全局冷却拦截, 空 IP, 与 R470-R482 一致).
- fallback 7 次 (dsv4p 全挂走 ms_gw 兜底, 链路有保障).
- 6h dsv4p_nv 全 caller SR=69.5% (130/187, R481=71.9% 略降, 仍处 46-85% 历史波动区间).
- stream_total_deadline 6h 0 次 (deadline 链对齐稳).
- per-min 趋势: 每 5min 1 次离散 429 (03:50/03:55/04:00/04:05/04:11/04:15), 20:10-11 唯一一次 200 (dur=7760ms, tool_calls finish), 非集中爆发.
- nv_gw Up 14h, cc4101 Up 4h, nv_gw_stable Up 26h, ms_gw Up 3 days (本轮未重启).
- 配置实测确认与 R475-R482 完全一致, 无漂移.

## 链路数据 (04:19 CST 注入)
### 30min 窗口 (hermes caller, 全 dsv4p_nv)
- 7 req: 1×200 (20:10, dur=7760ms, ttfb=7320, finish=tool_calls), 6×429 → SR=14.3%
- 错误分类: all_tiers_exhausted ×6 (sub=all_tiers_failed_in_mapped_tier)
- nv_tier_attempts: 0 行 (429 未进入 tier 尝试, 空 IP, 与 R470-R482 一致)
- fallback: 7 次 (dsv4p 全挂 → cc4101 走 ms_gw glm5_2_ms, 兜底正常)
- per-min: 03:50|429, 03:55|429, 04:00|429, 04:05|429, 04:10|200, 04:11|429, 04:15|429 (离散, 非爆发)

### cc4101-primary 专属 (cc2 的请求)
- 30min 0 req (psql 04:30 复测 0 rows 确认, cc2 session 间歇空闲)

### 6h dsv4p_nv 全 caller SR (04:30 复测基线)
- 200=130, 429=53, 502=4, 共 187 → SR=69.5% (R481=71.9% 略降, 仍处 46-85% 历史波动区间)
- 502 6h 4 次 (与 R476/R480/R481/R482 一致, 低频)

### nv_gw COOLDOWN 日志 (注入摘要, 30min 无 buffer/wait/keymanager 日志)
- (无 buffer/wait/keymanager 日志) — 429 在 buffer 层前被 KeyManager 全局冷却拦截, 与历史一致
- 行为: 单次 429 → NV-GLOBAL-COOLDOWN all keys 429 180s (TIER_COOLDOWN)
- tier=dsv4p_nv 只 1 tier 无 ring fallback → all_tiers_exhausted 直接 ABORT-NO-FALLBACK

## keymgr 行为 (与历史一致)
- 单次 429 即触发 NV-GLOBAL-COOLDOWN: "all keys 429. Marking all cooling 180s (TIER_COOLDOWN)"
- 429 resp 无 retry-after 头, 故依赖 TIER_COOLDOWN_S=180s 兜底
- tier=dsv4p_nv 只有 1 个 tier, ring 无 fallback → all_tiers_exhausted 直接 ABORT-NO-FALLBACK
- 这是历史一致行为 (R268 起 173+ 轮), 非本轮新故障.

## 历史波动区间 (R437-R483)
R437=85.0 → ... → R467=44.4 → R468-R472=44.4 → R473-R481=0.0% → R482=14.3% → R483=14.3% (30min 低谷, 6h 视角 69.5%)

## 判稳
- cc2 0 流量 → 无评估样本, 改前无数据 (铁律1 不满足), 不动码.
- 错误类型仅 all_tiers_exhausted ×6 (sub=all_tiers_failed_in_mapped_tier), 模式与 R268-R482 一致 (173+ 轮), 无新错误.
- dsv4p_nv 30min SR=14.3% (与 R482 持平) 仍是低谷窗口, 6h SR=69.5% 仍处 46-85% 历史波动区间, 属稳态周期性行为.
- fallback 7 次 (ms_gw 兜底正常, dsv4p_nv 自恢复不够时 cc4101 层有兜底, 链路有保障).
- stream_total_deadline 6h 0 次 (deadline 链对齐稳, 铁律4 满足).
- 0 restart → 无需 py_compile / curl 复测.
- 配置实测与 R475-R482 完全一致, 无配置漂移.

## 容器健康 (本轮实测 04:30)
- curl /health: status=ok, nv_num_keys=5, nvcf_pexec_models=[kimi_nv,dsv4p_nv,glm5_2_nv], port=40006.
- docker ps: nv_gw Up 14h, cc4101 Up 4h, nv_gw_stable Up 26h, ms_gw Up 3 days, logs_db Up 3 days.
- 0 restart.

## 下一步
- 继续 NOP 巡检, 等 cc2 流量恢复后观察 dsv4p_nv buffer 路径行为 (当前 0 buffer 样本).
- 关注新错误类型 (非 all_tiers_exhausted) 或 key/IP 级故障, 再决定是否介入.
- dsv4p_nv 小时级 SR 持续 <60% + cc2 缓冲流量恢复后再评估是否切换 PRIMARY_UPSTREAM_MODEL.
- all_tiers_exhausted 持续 >=5/h 且中段不恢复 再评估 buffer/KeyManager 参数 (TIER_COOLDOWN_S 180s 是否过激).
- 留意 502 是否再现 (R476/R480/R481/R482 记 6h 4×502 低频, 再现 >=3/h 才介入).
- 留意 cc4101 restart 后 PRIMARY_UPSTREAM_MODEL/FALLBACK 配置是否仍为 dsv4p_nv / glm5_2_ms.
- 候选观察: dsv4p_nv 单 tier 无 ring fallback, 若 6h SR 持续 <70% 可评估增加 glm5_2_nv 为 dsv4p 失败时的 ring fallback (但当前 ms_gw 已恢复作 cc4101 层 fallback, 链路有兜底, 不急).

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
