# R481 — NOP 巡检轮 (2026-08-03 04:25 CST)

## 摘要
- 0 改动 0 restart. NOP 巡检轮.
- 数据窗口 19:35-20:05 UTC (04:12 CST 注入 + 04:25 复测), 与 R475-R480 同低谷窗口高度一致 (连续 7 轮锁定 0%).
- cc2 (cc4101-primary) 30min 0 req (cc2 session 间歇空闲, 无评估样本, 铁律1 不满足 → 不动码).
- dsv4p_nv 全 caller 30min SR=0.0% (0/6, 全 429), 与 R475-R480 同窗口一致.
- 6h dsv4p_nv 全 caller SR=71.9% (200=143/429=52/502=4, 共 199), 与 R480 73.3% 略降, 仍处 46-85% 历史波动区间.
- 错误: all_tiers_exhausted ×6 (sub=all_tiers_failed_in_mapped_tier), 与 R475-R480 一致.
- nv_tier_attempts 30min 0 行 (429 在 tier 层前被拒, 空 IP, 与 R470-R480 一致).
- 12h per-hour 趋势: 08-18 UTC 全程稳态 (SR ~80%), 19:00 UTC 转折低谷 (200=4/429=11), 20:00 UTC 200=1/429=3 (低谷持续).
- fallback f=6/30min (dsv4p 全挂走 ms_gw 兜底, 链路有保障).
- nv_gw Up 14h, cc4101 Up 3h, nv_gw_stable Up 26h, ms_gw Up 3 days (本轮未重启).
- 配置实测确认与 R475-R480 完全一致, 无漂移.

## 链路数据 (04:12 CST 注入 + 04:25 复测)
### 30min 窗口 (hermes caller, 全 dsv4p_nv)
- 6×429, SR 0.0% (与 R475-R480 同窗口, R467-R481 十四轮低谷锁定)
- 错误分类: all_tiers_exhausted ×6 (sub=all_tiers_failed_in_mapped_tier)
- nv_tier_attempts: 0 行 (429 未进入 tier 尝试, 空 IP, 与 R470-R480 一致)
- fallback: 6 次 (dsv4p 全挂 → cc4101 走 ms_gw glm5_2_ms, 兜底正常)
- per-min 趋势: 每 5min 1 次离散 429 (19:35/40/45/50/55 + 20:00), 非集中爆发

### 6h dsv4p_nv 全 caller SR (复测)
- 200=143, 429=52, 502=4, 共 199 → SR=71.9% (R480 73.3%, 略降 1.4pp, 一致区间)
- 502 6h 4 次 (与 R476/R480 一致, 低频)

### 12h per-hour 趋势 (dsv4p_nv)
- 08:00 UTC: 200=14, 429=5 (SR 73.7%)
- 09:00-18:00 UTC: 稳态, 200 22-44/h, 429 6-9/h (SR ~80%)
- 19:00 UTC: 200=4, 429=11 (SR 26.7%, 低谷转折点)
- 20:00 UTC: 200=1, 429=3 (低谷持续)
- 结论: 08-18 UTC 稳态可用, 19:00+ 进入配额低谷窗口, 与 R475-R480 一致.

### nv_gw COOLDOWN 日志 (04:25 复测, 与注入一致)
```
[03:45-04:11] 每 5min: [NV-COOLDOWN] tier=dsv4p_nv k3 marked cooling after 429
              → [NV-GLOBAL-COOLDOWN] all keys 429. Marking all cooling 180s (TIER_COOLDOWN)
```
- 触发 key: k3 (单次 429 即触发全 tier cooling 180s)
- tier=dsv4p_nv 只 1 tier 无 ring fallback → all_tiers_exhausted 直接 ABORT-NO-FALLBACK
- 这是历史一致行为 (R268 起 172+ 轮), 非本轮新故障.

## keymgr 行为 (与历史一致)
- 单次 429 即触发 NV-GLOBAL-COOLDOWN: "all keys 429. Marking all cooling 180s (TIER_COOLDOWN)"
- 429 resp 无 retry-after 头, 故依赖 TIER_COOLDOWN_S=180s 兜底
- tier=dsv4p_nv 只有 1 个 tier, ring 无 fallback → all_tiers_exhausted 直接 ABORT-NO-FALLBACK
- 这是历史一致行为 (R268 起 172+ 轮), 非本轮新故障.

## 历史波动区间 (R437-R481)
R437=85.0 → ... → R467=44.4 → R468-R472=44.4 → R473-R481=0.0% (30min 低谷, 6h 视角 71.9-75%)

## 判稳
- cc2 0 流量 → 无评估样本, 改前无数据 (铁律1 不满足), 不动码.
- 错误类型仅 all_tiers_exhausted ×6 (sub=all_tiers_failed_in_mapped_tier), 模式与 R268-R480 一致 (172+ 轮), 无新错误.
- dsv4p_nv 30min SR=0% 是低谷窗口, 6h SR=71.9% 仍处 46-85% 历史波动区间, 属稳态周期性行为.
- 12h per-hour 趋势证实: 08-18 UTC 全程稳态 (SR ~80%), 19:00+ 才转低谷, 确认是配额周期非链路故障.
- fallback 6 次 (ms_gw 兜底正常, dsv4p_nv 自恢复不够时 cc4101 层有兜底, 链路有保障).
- 0 restart → 无需 py_compile / curl 复测.
- 配置实测与 R475-R480 完全一致, 无配置漂移.
- 注入数据 nv_gw "26 hours ago" 实为 nv_gw_stable Up 26h, nv_gw 本身 Up 14h (R480 14h, 0 增长, 无漂移).

## 容器健康 (本轮实测 04:25)
- curl /health: status=ok, nv_num_keys=5, nvcf_pexec_models=[kimi_nv,dsv4p_nv,glm5_2_nv], port=40006.
- docker ps: nv_gw Up 14h, cc4101 Up 3h, nv_gw_stable Up 26h, ms_gw Up 3 days, logs_db Up 3 days.
- 0 restart.

## 下一步
- 继续 NOP 巡检, 等 cc2 流量恢复后观察 dsv4p_nv buffer 路径行为 (当前 0 buffer 样本).
- 关注新错误类型 (非 all_tiers_exhausted) 或 key/IP 级故障, 再决定是否介入.
- dsv4p_nv 小时级 SR 持续 <60% + cc2 缓冲流量恢复后再评估是否切换 PRIMARY_UPSTREAM_MODEL.
- all_tiers_exhausted 持续 >=5/h 且中段不恢复 再评估 buffer/KeyManager 参数 (TIER_COOLDOWN_S 180s 是否过激).
- 留意 502 是否再现 (R476/R480/R481 记 6h 4×502 低频, 再现 >=3/h 才介入).
- 留意 cc4101 restart 后 PRIMARY_UPSTREAM_MODEL/FALLBACK 配置是否仍为 dsv4p_nv / glm5_2_ms.
- 候选观察: dsv4p_nv 单 tier 无 ring fallback, 若 6h SR 持续 <70% 可评估增加 glm5_2_nv 为 dsv4p 失败时的 ring fallback (但当前 ms_gw 已恢复作 cc4101 层 fallback, 链路有兜底, 不急).

## 参数快照 (本轮未改)
- nv_gw: NVU_DISABLE_MS_FALLBACK=0, UPSTREAM_TIMEOUT=90, TIER_TIMEOUT_BUDGET_S=180,
  TIER_COOLDOWN_S=180, KEY_COOLDOWN_S=30, NV_INTEGRATE_KEY_COOLDOWN_S=90,
  MIN_OUTBOUND_INTERVAL_S=10, NVU_FORCE_STREAM_UPGRADE=0,
  NVU_BUFFER_CALLERS=cc4101-primary,openclaw2, NVU_PEER_FB_SKIP_MODELS=glm5_2_nv,dsv4p_nv,
  NVU_CALLER_KEY_MAP=hermes:2;openclaw:3;opencode:4,
  NVU_BUFFER_MAX_RETRIES=5, NVU_BUFFER_TIMEOUT_STAIRS=90,90,90,90,90,
  NVU_BUFFER_TOTAL_DEADLINE_S=450, NVU_BUFFER_PING_INTERVAL_S=30, NVU_STREAM_FULL_BUFFER=0
- cc4101: PRIMARY_UPSTREAM_MODEL=dsv4p_nv, PRIMARY_UPSTREAM_URL=http://nv_gw:40006/v1/messages,
  FALLBACK_UPSTREAM_URL=http://ms_gw:40007/v1/chat/completions, FALLBACK_UPSTREAM_MODEL=glm5_2_ms,
  PRIMARY_HEADER_TIMEOUT=400, CC4101_STREAM_TOTAL_DEADLINE_S=470,
  CC4101_PRIMARY_FAIL_THRESHOLD=3, CC4101_PRIMARY_SKIP_S=30,
  UPSTREAM_TIMEOUT=130, UPSTREAM_IDLE_TIMEOUT=150
- deadline 链: 90s/attempt × 5 = 450s buffer < 470s cc4101 < 500s SDK idle
- settings.json: contextWindow=170000, autoCompactWindow=155000, API_TIMEOUT_MS=600000
