# R443 — NOP 巡检轮 (2026-08-03 02:00 CST)

## 摘要
- 0 改动 0 restart. NOP 巡检轮.
- 数据窗口 17:21-17:50 UTC (与 R442 同窗口, 样本结构净变化 15→14 req: 1×200 滚出, 1×429 滚入).
- cc2 (cc4101-primary) 30min 仍 0 req (cc2 session 间歇空闲, 无评估样本).
- dsv4p_nv 全 caller 30min SR=57.1% (8/14), 6×429 all_tiers_exhausted (avg_dur 1510ms), 模式与 R268-R442 一致.
- 历史波动区间: R420=86.4% → R429=69.2% → R430=63.6% → R431=80.0% → R432=89.5% → R433-R437=85.0% → R438=76.5% → R439=78.9% → R440=78.3% → R441=68.4% → R442=53.3% → R443=57.1%.
- nv_tier_attempts 30min 0 行 → 429 在 tier 层前被拒 (空 IP, all_tiers_failed_in_mapped_tier).
- nv_gw Up 11h, cc4101 Up About an hour (本轮未重启).

## 链路数据 (本轮实测 30min 窗口 17:21-17:50 UTC)
- caller×model×status: hermes|dsv4p_nv|200×8, hermes|dsv4p_nv|429×6
- dsv4p_nv SR=57.1% (8/14)
- 错误分类: all_tiers_exhausted|all_tiers_failed_in_mapped_tier ×6 (avg_dur 1510ms)
- cc4101-primary 30min: 0 req
- 时间分布: 17:25(429×1)/17:30(429×1)/17:35(429×1)/17:40(200×1)/17:41(200×6)/17:42(200×1+429×1)/17:45(429×1)/17:50(429×1)
- 前段 17:25-17:35 三次 429 (all_tiers_exhausted), 中段 17:40-17:42 连续 8×200 恢复明确, 末段 17:42-17:50 三次 429
- per-key: key2 8×200 avg 11248ms; 空 key 6×429
- per-egress-IP: 203.10.96.139 8×100%; 空 IP 6×429
- finish_reason: tool_calls×8 (无 zombie, 全部正常结束)
- fallback: f×14 (ms_gw 未触发, dsv4p_nv 自恢复足够)
- nv_tier_attempts: 0 行 (429 未进入 tier 尝试, 空 IP)
- buffer/wait/keymanager 日志: 无 (cc4101-primary 0 req 未触发)

## 判稳
- cc2 0 流量 → 无评估样本, 改前无数据 (铁律1 不满足), 不动码.
- 错误类型仅 all_tiers_exhausted, 无新增, 模式与 R268-R442 一致 (一百六十余轮一致).
- dsv4p_nv SR 在 53.3%-89.5% 区间波动, 本轮 57.1% 较 R442 (53.3%) 升 3.8pp, 处于区间下位但属正常波动.
- 6×429=12/h 高于 5/h 阈值, 但中段连续 8×200 恢复明确, 整体可接受.
- fallback 未触发 (ms_gw 已恢复但 dsv4p_nv 自恢复足够, 无需 fallback).
- 0 restart → 无需 py_compile / curl 复测 (健康检查已做).

## 容器健康 (本轮实测)
- curl /health: status=ok, proxy_role=passthrough, nv_num_keys=5,
  nvcf_pexec_models=[kimi_nv,dsv4p_nv,glm5_2_nv], nv_model_tiers 正常, port=40006.
- docker ps: nv_gw Up 11 hours, cc4101 Up About an hour, nv_gw_stable Up 24 hours, ms_gw Up 3 days, logs_db Up 3 days.
- 0 restart.

## 下一步
- 继续 NOP 巡检, 等 cc2 流量恢复后观察 dsv4p_nv buffer 路径行为.
- 关注新错误类型 (非 all_tiers_exhausted) 或 key/IP 级故障, 再决定是否介入.
- dsv4p_nv 小时级 SR 持续 <60% + cc2 缓冲流量恢复后再评估是否切换 PRIMARY_UPSTREAM_MODEL.
- all_tiers_exhausted 持续 >=5/h 且中段不恢复 再评估 buffer/KeyManager 参数.
- 留意 cc4101 restart 后 PRIMARY_UPSTREAM_MODEL/FALLBACK 配置是否仍为 dsv4p_nv / glm5_2_ms (下次有流量时验证).

## 参数快照 (本轮未改)
- nv_gw: NVU_DISABLE_MS_FALLBACK=0, UPSTREAM_TIMEOUT=90, TIER_TIMEOUT_BUDGET_S=180,
  TIER_COOLDOWN_S=180, KEY_COOLDOWN_S=30, NV_INTEGRATE_KEY_COOLDOWN_S=90,
  MIN_OUTBOUND_INTERVAL_S=10, NVU_FORCE_STREAM_UPGRADE=0,
  NVU_BUFFER_CALLERS=cc4101-primary,openclaw2, NVU_PEER_FB_SKIP_MODELS=glm5_2_nv,dsv4p_nv,
  NVU_CALLER_KEY_MAP=hermes:2;openclaw:3;opencode:4
- cc4101: PRIMARY_UPSTREAM_MODEL=dsv4p_nv, PRIMARY_UPSTREAM_URL=http://nv_gw:40006/v1/messages,
  FALLBACK_UPSTREAM_URL=http://ms_gw:40007/v1/chat/completions, FALLBACK_UPSTREAM_MODEL=glm5_2_ms,
  PRIMARY_HEADER_TIMEOUT=400, CC4101_STREAM_TOTAL_DEADLINE_S=470,
  CC4101_PRIMARY_FAIL_THRESHOLD=3, CC4101_PRIMARY_SKIP_S=30,
  UPSTREAM_TIMEOUT=130, UPSTREAM_IDLE_TIMEOUT=150
- deadline 链: 90s/attempt × 5 = 450s buffer < 470s cc4101 < 500s SDK idle
- settings.json: contextWindow=170000, autoCompactWindow=155000, API_TIMEOUT_MS=600000
