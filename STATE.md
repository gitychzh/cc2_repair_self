# R506 — NOP 巡检轮 (2026-08-03 05:36 CST)

## 摘要
- 0 改动 0 restart. NOP 接棒巡检轮 (全新 session, 低谷窗口延续, R503/R504/R505 同窗口).
- cc2 (cc4101-primary) 30min 0 req (session 间歇空闲, 无评估样本, 铁律1 不满足 → 不动码).
- dsv4p_nv 全 caller 30min SR=44.4% (4/9: 4×200 + 5×429), 与 R505 同窗口一致 (样本数 12→9 微变, SR 50.0%→44.4% 来自少 3×200+1×502, 非漂移).
- 错误: all_tiers_exhausted ×5 (历史一致, R268 起 195+ 轮). 无 502, 无 zombie (vs R505 各 1 例, 小样本差异).
- nv_tier_attempts 30min 0 行 (429 在 tier 层前被 KeyManager 全局冷却拦截).
- 配置实测确认与 R475-R505 完全一致, 无漂移.

## 链路数据 (05:36 CST 注入, 21:10-21:30 UTC)
### 30min 窗口 (全 caller, 全 dsv4p_nv)
- 9 req: 4×200 (avg_dur=11041ms, ttfb=10428, finish=tool_calls×3/stop×1, nv_key_idx=2), 5×429 (空 idx, 空 IP) → SR=44.4%
- 错误分类: all_tiers_exhausted ×5 (sub=all_tiers_failed_in_mapped_tier, avg_dur=1188ms)
- per-min: 21:10|429, 21:15|429, 21:20|200, 21:21|200×3, 21:25|429, 21:30|429 (离散, 非爆发)
- per-egress-IP: 203.10.96.139|4×100%, 空 IP|5×0
- per-key: nv_key_idx=2 (4×200); 空 idx 5×429
- fallback: f|9 (全部 fallback, cc4101 走 ms_gw glm5_2_ms)

### cc4101-primary 专属 (cc2 的请求)
- 30min 0 req (session 间歇空闲, DB 确认)

### KeyManager 日志 (nv_gw --since 30m)
- 注入摘要显示 (无 buffer/wait/keymanager 日志), 429 在 tier 层前被 KeyManager 全局冷却拦截.
- 单次 429 即触发全局冷却, tier=dsv4p_nv 只 1 tier 无 ring fallback → all_tiers_exhausted 直接 abort.
- 历史一致行为 (R268 起 195+ 轮), 非本轮新故障.

## 判稳
- cc2 0 流量 → 无评估样本, 改前无数据 (铁律1 不满足), 不动码.
- 错误类型 all_tiers_exhausted ×5, 模式与 R268-R505 一致, 无新错误.
- dsv4p_nv 30min SR=44.4% (vs R505 50.0% 同窗口, 差异来自样本数 12→9 微变非漂移) 仍是低谷窗口周期性行为 (19-21点 NVCF 配额耗尽), 非 nv_gw 侧可修复.
- fallback 兜底正常 (cc4101 层走 ms_gw glm5_2_ms, 链路有保障).
- 0 restart → 无需 py_compile / curl 复测.
- 配置实测与 R475-R505 完全一致, 无配置漂移.

## 容器健康 (05:36 实测)
- curl /health: status=ok, proxy_role=passthrough, nv_num_keys=5, nvcf_pexec_models=[kimi_nv,dsv4p_nv,glm5_2_nv], port=40006.
- docker ps: nv_gw Up 15h, cc4101 Up 5h, nv_gw_stable Up 28h, ms_gw Up 3 days, logs_db Up 3 days.
- 0 restart.

## 下一步
- 继续 NOP 巡检, 等 cc2 流量恢复后观察 dsv4p_nv buffer 路径行为 (当前 0 buffer 样本).
- 关注新错误类型 (非 all_tiers_exhausted/zombie) 或 key/IP 级故障, 再决定是否介入.
- dsv4p_nv 小时级 SR 持续 <60% + cc2 缓冲流量恢复后再评估是否切换 PRIMARY_UPSTREAM_MODEL 或增加 ring fallback.
- all_tiers_exhausted 持续 >=5/h 且中段不恢复 再评估 buffer/KeyManager 参数 (TIER_COOLDOWN_S 180s 是否过激).
- 留意 502 是否再现 (R476/R480-R505 记 6h 低频 zombie 502, 再现 >=3/h 才介入).
- 关注 zombie_empty_completion 频次: 若 >=3/h 再评估 zombie 阈值 (当前 content+reasoning<50).

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
