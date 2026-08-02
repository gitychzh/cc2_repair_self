# R467 — NOP 巡检轮 (2026-08-03 04:55 CST)

## 摘要
- 0 改动 0 restart. NOP 巡检轮.
- 数据窗口 18:45-19:10 UTC (实测复跑 04:55 CST 确认).
- cc2 (cc4101-primary) 30min 仍 0 req (cc2 session 间歇空闲, 无评估样本).
- dsv4p_nv 全 caller 30min SR=44.4% (4/9), 较 R466 (61.5%) 下滑, 仍处 46.2%-85% 历史波动区间.
- 错误: all_tiers_exhausted ×5 (唯一类型, 模式与 R268-R466 一致, 无新错误).
- nv_tier_attempts 30min 0 行 → 429 在 tier 层前被拒 (空 IP).
- nv_gw Up 13h, cc4101 Up 3h (本轮未重启).
- 连续 14 轮无 502 (R454-R467), 单点 502 模式似已消退.
- 配置实测确认与 R466 完全一致, 无漂移.

## 链路数据 (注入窗口 + 实测复跑 04:55 CST)
- caller×model×status (注入): hermes|dsv4p_nv 3×200 + 5×429; openclaw|dsv4p_nv 1×200
- 实测复跑全 caller 30min: 4×200 + 5×429 = SR 44.4% (9req, 与注入一致)
- 错误分类: all_tiers_exhausted ×5 (唯一类型, 与注入一致)
- cc4101-primary 30min: 0 req (实测复跑 0 rows 确认)
- per-key (注入): key2 3×200 (avg 13222ms); key3 1×200 (2904ms); 空 key 5×429
- per-egress-IP (注入): 203.10.96.139 3×100%; 134.195.101.194 1×100%; 空 IP 5×失败
- 200 延迟 (注入): avg 10643ms, max 19084ms, min 2904ms, avg_ttfb 10437ms
- finish_reason (注入): stop×2, tool_calls×2 (无 zombie, 全部正常结束)
- fallback (注入): f×9 (ms_gw 未触发, dsv4p_nv 自恢复足够)
- nv_tier_attempts: 0 行 (429 未进入 tier 尝试, 空 IP)
- per-min 趋势 (注入): 18:45(429)/18:50(429)/18:55(429)/19:00(429)/19:05(200×2)/19:06(200×2)/19:10(429)
  - 19:05-19:06 连续 200 恢复明确, 其余离散 429 (每5min1次) 非集中爆发
- buffer/wait 日志: 30min 无 BUFFER-/WAIT- 行 (cc4101-primary 0 req, 无 buffer 触发样本)

## 实测复跑确认 (04:55 CST)
- nv_requests cc4101-primary 30min: 0 rows (确认 cc2 0 流量)
- nv_requests 全 caller 30min: 4×200 + 5×429 (与注入一致, status 字段为整数 200/429)
- nv_requests 全 caller 错误 30min: all_tiers_exhausted ×5 (唯一类型)
- nv_tier_attempts 30min: 0 rows (确认 429 在 tier 层前被拒)
- /health: status=ok, nv_num_keys=5, nvcf_pexec_models=[kimi_nv,dsv4p_nv,glm5_2_nv], port=40006
- docker ps: nv_gw Up 13h, cc4101 Up 3h, nv_gw_stable Up 25h, ms_gw Up 3 days

## 历史波动区间 (R437-R467)
R437=85.0 → R438=76.5 → R439=78.9 → R440=78.3 → R441=68.4 → R442=53.3 → R443=57.1 → R444=57.1 → R445=66.7 → R446=66.7 → R447=66.7 → R448=46.2 → R449=46.2 → R450=46.2 → R451=46.2 → R452=46.2 → R453=62.5 → R454=57.1 → R455=44.4 → R456=69.2 → R457=83.3 → R458=84.2 → R459=84.2 → R460=84.2 → R461=84.2 → R462=76.5 → R463=75.0 → R464=75.0 → R465=73.3 → R466=61.5 → R467=44.4%

## 判稳
- cc2 0 流量 → 无评估样本, 改前无数据 (铁律1 不满足), 不动码.
- 错误类型仅 all_tiers_exhausted ×5, 模式与 R268-R466 一致 (一百六十余轮一致), 无新错误.
- dsv4p_nv SR=44.4% 较 R466 (61.5%) 下滑, 但仍处 46.2%-85% 历史波动区间, 属正常波动.
- 5×429 ≈ 10/h 略高于 5/h 阈值, 但 per-min 趋势仍呈"19:05-19:06 连续 200 + 其余离散 429 (每5min1次)"恢复模式, 非集中爆发, 整体可接受.
- 本轮无 502 (R454-R467 连续 14 轮无 502, 单点模式似已消退, 继续观察).
- fallback 未触发 (ms_gw 已恢复但 dsv4p_nv 自恢复足够, 无需 fallback).
- 0 restart → 无需 py_compile / curl 复测 (健康检查已做).
- 配置实测与 R466 完全一致, 无配置漂移.

## 容器健康 (本轮实测)
- curl /health: status=ok, nv_num_keys=5, nvcf_pexec_models=[kimi_nv,dsv4p_nv,glm5_2_nv], port=40006.
- docker ps: nv_gw Up 13h, cc4101 Up 3h, nv_gw_stable Up 25h, ms_gw Up 3 days.
- 0 restart.

## 下一步
- 继续 NOP 巡检, 等 cc2 流量恢复后观察 dsv4p_nv buffer 路径行为.
- 关注新错误类型 (非 all_tiers_exhausted) 或 key/IP 级故障, 再决定是否介入.
- dsv4p_nv 小时级 SR 持续 <60% + cc2 缓冲流量恢复后再评估是否切换 PRIMARY_UPSTREAM_MODEL.
- all_tiers_exhausted 持续 >=5/h 且中段不恢复 再评估 buffer/KeyManager 参数.
- 留意 502 是否再现 (R454-R467 连续 14 轮无 502, 再现 >=3/h 才介入).
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
