# R439 — NOP 巡检轮 (2026-08-03 01:42 CST)

## 摘要
- 0 改动 0 restart. NOP 巡检轮.
- 数据窗口已刷新 (17:15-17:41, 较 R438 注入的 17:10-17:35 滚动 5min), 滚出 17:10/17:11 的 3×200, 滚入 17:40/17:41 的 5×200 (净+2 个 200).
- cc2 (cc4101-primary) 30min 仍 0 req (cc2 session 间歇空闲, 无评估样本).
- dsv4p_nv 全 caller 30min SR=78.9% (15/19), 4×429 all_tiers_exhausted, 与 R268-R438 模式一致.
- 历史波动区间: R420=86.4% → R429=69.2% → R430=63.6% → R431=80.0% → R432=89.5% → R433-R437=85.0% → R438=76.5% → R439=78.9%.
- nv_tier_attempts 30min 0 行 → 429 在 tier 层前被拒 (空 IP, all_tiers_failed_in_mapped_tier).
- nv_gw Up 11h, cc4101 Up 58min (本轮未重启).

## 链路数据 (本轮实测 30min 窗口 17:15-17:41)
- caller×model×status: hermes|dsv4p_nv|200×15, hermes|dsv4p_nv|429×4
- dsv4p_nv SR=78.9% (15/19)
- 错误分类: all_tiers_exhausted|all_tiers_failed_in_mapped_tier ×4 (avg_dur 2607s)
- cc4101-primary 30min: 0 req
- 时间分布: 17:15(200)/17:16(200×4)/17:20(200×2)/17:21(200×3+429×1)/17:25(429)/17:30(429)/17:35(429)/17:40(200)/17:41(200×4)
- 前段 17:15-17:21 连续 200 恢复明确, 17:21/17:25/17:30/17:35 四次 429 (all_tiers_exhausted), 末段 17:40/17:41 连续 5×200 再恢复
- per-key: key2 15×200 avg 9123ms; 空 key 4×429
- per-egress-IP: 203.10.96.139 15×100% ; 空 IP 4×429
- finish_reason: tool_calls×14, stop×1 (无 zombie)
- fallback: f×19 (ms_gw 未触发, dsv4p_nv 自恢复足够)
- nv_tier_attempts: 0 行 (429 未进入 tier 尝试, 空 IP)
- buffer/wait/keymanager 日志: 无 (cc4101-primary 0 req 未触发)

## 判稳
- cc2 0 流量 → 无评估样本, 改前无数据 (铁律1 不满足), 不动码.
- 错误类型仅 all_tiers_exhausted, 无新增, 模式与 R268-R438 一致 (一百六十余轮一致).
- dsv4p_nv SR 在 63.6%-89.5% 区间波动, 本轮 78.9% 处于区间中位, 较 R438 (76.5%) 小升 2.4pp.
- SR 76.5%→78.9% 是窗口滑动效应 (滚出 3×200 旧样本, 滚入 5×200 新样本, 429 计数不变), 非真实改善.
- 4×429=8/h 略高于 5/h 阈值, 但 17:40/17:41 连续 5×200 末段恢复明确, 整体可接受.
- fallback 未触发 (ms_gw 已恢复但 dsv4p_nv 自恢复足够, 无需 fallback).
- 0 restart → 无需 py_compile / curl 复测 (健康检查已做).

## 容器健康 (本轮实测)
- curl /health: status=ok, proxy_role=passthrough, nv_num_keys=5,
  nvcf_pexec_models=[kimi_nv,dsv4p_nv,glm5_2_nv], nv_model_tiers 正常, port=40006.
- docker ps: nv_gw Up 11h, cc4101 Up 58min, nv_gw_stable Up 24h, ms_gw Up 3 days, logs_db Up 3 days.
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
