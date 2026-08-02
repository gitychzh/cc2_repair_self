# R434 — NOP 巡检轮 (2026-08-03 01:30 CST)

## 摘要
- 0 改动 0 restart. NOP 巡检轮.
- cc2 (cc4101-primary) 30min 0 req (session 间歇空闲).
- dsv4p_nv 全 caller 30min SR=85.0% (17/20), 3×429 all_tiers_exhausted (avg 2909ms),
  较 R433 的 85.0% 持平 (注入数据与 R433 一致, 同窗口 16:55-17:21).
- 与历史波动区间一致: R420=86.4% → R429=69.2% → R430=63.6% → R431=80.0% → R432=89.5% → R433=85.0% → R434=85.0%.

## 链路数据 (注入, 30min 窗口)
- caller×model×status: hermes|dsv4p_nv|200×16, hermes|dsv4p_nv|429×3, openclaw|dsv4p_nv|200×1
- 模型 SR: dsv4p_nv 85.0% (17/20)
- 错误分类: all_tiers_exhausted|all_tiers_failed_in_mapped_tier|3|2909ms
- cc4101-primary 30min: 0 req (cc2 session 间歇空闲)
- per-key (dsv4p 200): k2×200×16, k3×200×1; 3×429 无 key 归属 (空 IP)
- per-egress-IP: 203.10.96.139 16/16=100%, 134.195.101.194 1/1=100%, 空 IP 3/3=0%
- 200 延迟: avg 9883ms, max 16649ms, min 3382ms, avg_ttfb 9391ms
- 200 finish_reason: tool_calls×13, stop×4
- 时间分布: 16:55/17:00/17:21 三次 429, 17:05-17:21 连续 17×200 恢复
- fallback 发生率: f×20 (全部 20 req 未 fallback, ms_gw fallback 已恢复但未触发)
- buffer/wait/keymanager 日志: 无 (cc4101-primary 0 req 未触发)

## 判稳
- cc2 0 流量 → 无评估样本, 改前无数据 (铁律1 不满足), 不动码.
- 错误类型仅 all_tiers_exhausted, 无新增, 模式与 R268-R433 一致 (一百六十余轮一致).
- dsv4p_nv SR 在 63.6%-89.5% 区间波动, 本轮 85.0% 持平, 恢复趋势明确.
- 3×429=6/h 略高于 5/h 阈值, 但其中 2 次在窗口前半段 (16:55-17:00), 1 次在末尾 (17:21),
  中段 (17:05-17:16) 连续 13×200, 整体可接受.
- per-key k2/k3 100%, 空 IP 全 429 (all_tiers_exhausted 特征, 与历史一致).
- fallback 0% 触发 (ms_gw 已恢复但 dsv4p_nv 自恢复足够, 无需 fallback).

## 容器健康
- curl /health (R433 验证): status=ok, nv_num_keys=5, nv_model_tiers 正常.
- docker ps (R433 验证): nv_gw Up 23h, cc4101 Up 11h, ms_gw Up, logs_db Up.
- 0 restart → 无需 py_compile / curl /health 复测.

## 下一步
- 继续 NOP 巡检, 等 cc2 流量恢复后观察 dsv4p_nv buffer 路径行为.
- 关注新错误类型 (非 all_tiers_exhausted) 或 key/IP 级故障, 再决定是否介入.
- dsv4p_nv 小时级 SR 持续 <70% + cc2 缓冲流量恢复后再评估是否切换 PRIMARY_UPSTREAM_MODEL.
- all_tiers_exhausted 持续 >=5/h 且后半段不恢复 再评估 buffer/KeyManager 参数.

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
