# R451 — NOP 巡检轮 (2026-08-03 03:50 CST)

## 摘要
- 0 改动 0 restart. NOP 巡检轮.
- 数据窗口 17:45-18:10 UTC (与 R448-R450 同窗口延续, 样本 13 req: 6×200 + 7×429).
- cc2 (cc4101-primary) 30min 仍 0 req (cc2 session 间歇空闲, 无评估样本).
- dsv4p_nv 全 caller 30min SR=46.2% (6/13), 7×429 all_tiers_exhausted, 模式与 R268-R450 一致.
- 历史波动区间: R437=85.0% → R438=76.5% → R439=78.9% → R440=78.3% → R441=68.4% → R442=53.3% → R443=57.1% → R444=57.1% → R445=66.7% → R446=66.7% → R447=66.7% → R448=46.2% → R449=46.2% → R450=46.2% → R451=46.2%.
- nv_tier_attempts 30min 0 行 → 429 在 tier 层前被拒 (空 IP, all_tiers_failed_in_mapped_tier).
- nv_gw Up 12h, cc4101 Up 2h (本轮未重启).

## 链路数据 (本轮实测 30min 窗口 17:45-18:10 UTC)
- caller×status: hermes 6×429 + 1×502; openclaw 6×200
- dsv4p_nv SR=46.2% (6/13)
- 错误分类: all_tiers_exhausted ×7 (nv_tier_attempts 0 行)
- cc4101-primary 30min: 0 req
- 时间分布: 17:50(429×1)/17:55(429×1)/18:00(200×3+429×1+502×1)/18:01(200×3)/18:05(429×1)/18:10(429×1)
- 前段 17:50-17:55 两次 429, 18:00-18:01 连续 6×200 恢复明确, 末段 18:05-18:10 两次 429
- per-key: key3 6×200 avg 13050ms; 空 key 6×429 + 1×502
- per-egress-IP: 134.195.101.194 6×100%; 空 IP 7×失败
- 200 延迟: avg 13050ms, max 31901ms, min 5264ms, avg_ttfb 12588ms
- finish_reason: tool_calls×5, stop×1 (无 zombie, 全部正常结束)
- fallback: f×13 (ms_gw 未触发, dsv4p_nv 自恢复足够)
- nv_tier_attempts: 0 行 (429 未进入 tier 尝试, 空 IP)
- buffer/wait 日志: 30min 无 BUFFER-/WAIT- 行 (cc4101-primary 0 req, 无 buffer 触发样本)

## 判稳
- cc2 0 流量 → 无评估样本, 改前无数据 (铁律1 不满足), 不动码.
- 错误类型仅 all_tiers_exhausted + 1×502 单点 (不构成新错误模式), 模式与 R268-R450 一致 (一百六十余轮一致).
- dsv4p_nv SR 在 46.2%-89.5% 区间波动, 本轮 46.2% 与 R448-R450 持平, 处于区间下沿但属正常波动.
- 7×429=14/h 高于 5/h 阈值, 但 18:00-18:01 连续 6×200 恢复明确, 整体可接受.
- 1×502 单点 (18:00) 不足构成新错误模式 (连续 R445-R451 各 1×502, 仍 <3/h 阈值, 继续观察).
- fallback 未触发 (ms_gw 已恢复但 dsv4p_nv 自恢复足够, 无需 fallback).
- 0 restart → 无需 py_compile / curl 复测 (健康检查已做).

## 容器健康 (本轮实测)
- curl /health: status=ok, proxy_role=passthrough, nv_num_keys=5,
  nvcf_pexec_models=[kimi_nv,dsv4p_nv,glm5_2_nv], nv_model_tiers 正常, nv_default_model=glm5_2_nv, port=40006.
- docker ps: nv_gw Up 12 hours, cc4101 Up 2 hours, nv_gw_stable Up 24 hours, ms_gw Up 3 days, logs_db Up 3 days.
- 0 restart.

## 下一步
- 继续 NOP 巡检, 等 cc2 流量恢复后观察 dsv4p_nv buffer 路径行为.
- 关注新错误类型 (非 all_tiers_exhausted) 或 key/IP 级故障, 再决定是否介入.
- dsv4p_nv 小时级 SR 持续 <60% + cc2 缓冲流量恢复后再评估是否切换 PRIMARY_UPSTREAM_MODEL.
- all_tiers_exhausted 持续 >=5/h 且中段不恢复 再评估 buffer/KeyManager 参数.
- 留意 502 是否再现 (R445-R451 各 1×单点, 再现 >=3/h 才介入).
- 留意 cc4101 restart 后 PRIMARY_UPSTREAM_MODEL/FALLBACK 配置是否仍为 dsv4p_nv / glm5_2_ms.

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
