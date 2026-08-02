# R430 — NOP 巡检轮 (2026-08-03 01:20 CST)

## 本轮改了什么
- 0 改动 0 restart. NOP 巡检轮.

## 依据
- cc2 (cc4101-primary) 30min 无请求 (session 间歇空闲), 0 错误 0 fallback.
- dsv4p_nv 全 caller 30min SR=63.6% (7/11), 4×429 all_tiers_exhausted (avg 1910ms),
  在历史波动区间内 (R420=86.4% → R429=69.2% → R430=63.6%).
- per-key (dsv4p 200): k2×6, k3×1 = 7×200; 4×429 无 key 归属 (空 IP).
- per-egress-IP: 203.10.96.139 6/6=100%, 134.195.101.194 1/1=100%, 空 IP 4req 全 429.
- 200 延迟 avg 10439ms, avg_ttfb 9740ms (正常波动).
- 30min buffer/wait/keymanager 日志: 无 (buffer caller 本轮 0 req 触发).
- 错误类型无新增, 与 R268-R429 一致 (一百五十余轮一致).
- glm5_2_nv 30min 0 req → 切 PRIMARY_UPSTREAM_MODEL 不满足"改前必有数据"铁律, 暂不切.

## 验证
- 容器健康: nv_gw (23h), cc4101 (11h), ms_gw, logs_db Up.
- 0 restart → 无需 py_compile / curl /health 复测.

## 下一步
- 继续 NOP 巡检, 等 cc2 流量恢复后观察 dsv4p_nv buffer 路径行为.
- 关注新错误类型 (非 all_tiers_exhausted) 或 key/IP 级故障, 再决定是否介入.
- dsv4p_nv 小时级 SR 持续 <70% + cc2 缓冲流量恢复后再评估是否切换 PRIMARY_UPSTREAM_MODEL.
- all_tiers_exhausted 持续 >=5/h 再评估 buffer/KeyManager 参数.

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
