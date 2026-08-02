# R475 — NOP 巡检轮 (2026-08-03 03:55 CST)

## 摘要
- 0 改动 0 restart. NOP 巡检轮.
- 数据窗口 19:20-19:50 UTC (03:49 CST 注入 + 03:55 复测, 与 R470-R474 同低谷窗口).
- cc2 (cc4101-primary) 30min 0 req (cc2 session 间歇空闲, 无评估样本, 铁律1 不满足 → 不动码).
- dsv4p_nv 全 caller 30min SR=0.0% (0/6, 全 429), 与 R474 同窗口一致.
- 6h 视角 dsv4p_nv SR=75.0% (159/212), 处历史波动区间 46-85%, 与 R474 完全一致.
- 2h per-bucket: 02:00-02:40 UTC 多桶连续高 200 (6/9,4/5,5/6,7/8), 03:00+ 进入低谷 (全 429).
- 错误: all_tiers_exhausted ×6 (唯一类型, 模式与 R268-R474 一致, 无新错误).
- nv_tier_attempts 30min 0 行 (429 在 tier 层前被拒, 空 IP, 与 R470-R474 一致).
- 6h stream_total_deadline = 0 (deadline 链无越界).
- 6h 502 = 4 (低频, 2h 0, 单点模式继续消退).
- fallback f=6/30min (dsv4p 全挂走 ms_gw 兜底, 链路有保障).
- nv_gw Up 13h, cc4101 Up 3h (本轮未重启).
- 配置实测确认与 R474 完全一致, 无漂移.

## 链路数据 (03:49 CST 注入 + 03:55 复测)
### 30min 窗口 (hermes caller, 全 dsv4p_nv)
- 6×429, SR 0.0% (与 R474 同窗口, R467-R475 八轮低谷锁定)
- 错误分类: all_tiers_exhausted ×6, avg_dur 1333ms (仅 hermes caller, cc4101-primary 0 req)
- nv_tier_attempts: 0 行 (429 未进入 tier 尝试, 空 IP, 与 R470-R474 一致)
- fallback: 6 次 (dsv4p 全挂 → cc4101 走 ms_gw glm5_2_ms, 兜底正常)

### 6h 视角 (dsv4p_nv)
- 159×200 + 49×429 + 4×502 = SR 75.0% (212req)
- 与 R474 完全一致 (159/212 vs 159/212, 0 滚动差异, 窗口稳定)

### 2h 按桶 (10min, UTC)
- 01:50(0/1)→02:00(6/9)→02:10(0/2)→02:20(4/5)→02:30(5/6)→02:40(7/8)
  →02:50(0/2)→03:00(4/5)→03:10+(0/2 全 429)
- 02:00-02:40 连续高 200 桶, 02:50 起进入低谷, 符合 dsv4p_nv 周期性配额模式.
- 与 R474 的 18:00-18:40 高 + 18:50+ 低谷 是同一现象 (UTC+8 时区差).

## keymgr 行为 (与历史一致)
- 单次 429 即触发 NV-GLOBAL-COOLDOWN: "all keys 429. Marking all cooling 180s (TIER_COOLDOWN)"
- 429 resp 无 retry-after 头, 故依赖 TIER_COOLDOWN_S=180s 兜底
- tier=dsv4p_nv 只有 1 个 tier, ring 无 fallback → all_tiers_exhausted 直接 ABORT-NO-FALLBACK
- 这是历史一致行为 (R268 起 170+ 轮), 非本轮新故障.

## 历史波动区间 (R437-R475)
R437=85.0 → ... → R467=44.4 → R468-R472=44.4 → R473-R475=0.0% (30min 低谷, 6h 视角 75.0%)

## 判稳
- cc2 0 流量 → 无评估样本, 改前无数据 (铁律1 不满足), 不动码.
- 错误类型仅 all_tiers_exhausted ×6, 模式与 R268-R474 一致 (170+ 轮), 无新错误.
- dsv4p_nv 30min SR=0% 是低谷窗口, 但 6h SR=75% 仍处 46-85% 历史波动区间, 属稳态周期性行为.
- 6×429/30min ≈ 12/h 高于 5/h 阈值, 但 per-min 趋势呈"每5min1次离散 429", 非集中爆发.
  且 02:00-02:40 连续高 200 桶证明 NVCF 侧可用, 当前低谷是配额周期非链路故障.
- 本轮无 502 (2h 0×502, 6h 4×502 低频, 单点模式继续消退).
- fallback 6 次 (ms_gw 兜底正常, dsv4p_nv 自恢复不够时 cc4101 层有兜底, 链路有保障).
- 0 restart → 无需 py_compile / curl 复测.
- 配置实测与 R474 完全一致, 无配置漂移.
- 6h stream_total_deadline = 0, deadline 链对齐无越界.

## 容器健康 (本轮实测 03:50)
- curl /health: status=ok, nv_num_keys=5, nvcf_pexec_models=[kimi_nv,dsv4p_nv,glm5_2_nv], port=40006.
- docker ps: nv_gw Up 13h, cc4101 Up 3h, nv_gw_stable Up 26h, ms_gw Up 3 days, logs_db Up 3 days.
- 0 restart.

## 下一步
- 继续 NOP 巡检, 等 cc2 流量恢复后观察 dsv4p_nv buffer 路径行为 (当前 0 buffer 样本).
- 关注新错误类型 (非 all_tiers_exhausted) 或 key/IP 级故障, 再决定是否介入.
- dsv4p_nv 小时级 SR 持续 <60% + cc2 缓冲流量恢复后再评估是否切换 PRIMARY_UPSTREAM_MODEL.
- all_tiers_exhausted 持续 >=5/h 且中段不恢复 再评估 buffer/KeyManager 参数 (TIER_COOLDOWN_S 180s 是否过激).
- 留意 502 是否再现 (2h 0×502, 6h 4×502 低频, 再现 >=3/h 才介入).
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
