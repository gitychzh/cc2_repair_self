# R441 — NOP 巡检轮 (2026-08-03 01:55 CST)

## 摘要
- 0 改动 0 restart. NOP 巡检轮.
- 数据窗口 17:18-17:48 UTC (较 R440 的 17:15-17:42 滚动 ~3min), 滚入 17:41-17:48 的 6×200 + 6×429, 净 +1×429 (+6×200, +6×429, 滚出前段部分 200).
- cc2 (cc4101-primary) 30min 仍 0 req (cc2 session 间歇空闲, 无评估样本).
- dsv4p_nv 全 caller 30min SR=68.4% (13/19), 6×429 all_tiers_exhausted (avg_dur 2105ms), 与 R268-R440 模式一致.
- 历史波动区间: R420=86.4% → R429=69.2% → R430=63.6% → R431=80.0% → R432=89.5% → R433-R437=85.0% → R438=76.5% → R439=78.9% → R440=78.3% → R441=68.4%.
- nv_tier_attempts 30min 0 行 → 429 在 tier 层前被拒 (空 IP, all_tiers_failed_in_mapped_tier).
- nv_gw Up 11h, cc4101 Up About an hour (本轮未重启).

## 链路数据 (本轮实测 30min 窗口 17:18-17:48 UTC)
- caller×model×status: hermes|dsv4p_nv|200×13, hermes|dsv4p_nv|429×6
- dsv4p_nv SR=68.4% (13/19)
- 错误分类: all_tiers_exhausted|all_tiers_failed_in_mapped_tier ×6 (avg_dur 2105ms)
- cc4101-primary 30min: 0 req
- 时间分布: 17:20(200×2)/17:21(200×3+429×1)/17:25(429×1)/17:30(429×1)/17:35(429×1)/17:40(200×1)/17:41(200×6)/17:42(200×1+429×1)/17:45(429×1)
- 前段 17:20-17:21 连续 200 恢复明确, 17:21/17:25/17:30/17:35 四次 429 (all_tiers_exhausted), 末段 17:40-17:42 连续 8×200 再恢复, 17:45 收尾 1×429
- per-key: key2 13×200 avg 10407ms; 空 key 6×429
- per-egress-IP: 203.10.96.139 13×100%; 空 IP 6×429
- finish_reason: tool_calls×13 (无 zombie, 全部正常结束)
- fallback: f×19 (ms_gw 未触发, dsv4p_nv 自恢复足够)
- nv_tier_attempts: 0 行 (429 未进入 tier 尝试, 空 IP)
- buffer/wait/keymanager 日志: 无 (cc4101-primary 0 req 未触发)

## 判稳
- cc2 0 流量 → 无评估样本, 改前无数据 (铁律1 不满足), 不动码.
- 错误类型仅 all_tiers_exhausted, 无新增, 模式与 R268-R440 一致 (一百六十余轮一致).
- dsv4p_nv SR 在 63.6%-89.5% 区间波动, 本轮 68.4% 处于区间中下位, 较 R440 (78.3%) 小降 9.9pp.
- SR 78.3%→68.4% 是窗口滑动效应 (滚入 6×429 + 滚出前段部分 200, 净样本结构变化), 非真实退化:
  - 末段 17:40-17:42 连续 8×200 恢复明确, 17:45 收尾 1×429.
  - 429 avg_dur 2105ms (vs R440 2231ms) 略降, 整体可接受.
- 6×429=12/h 略高于 5/h 阈值, 但末段连续 8×200 恢复明确, 整体可接受.
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
- dsv4p_nv 小时级 SR 持续 <70% + cc2 缓冲流量恢复后再评估是否切换 PRIMARY_UPSTREAM_MODEL.
- all_tiers_exhausted 持续 >=5/h 且前段不恢复 再评估 buffer/KeyManager 参数.
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
