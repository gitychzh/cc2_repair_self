# R422 — NOP 巡检轮 (2026-08-03 00:51 CST)

## 摘要
- NOP 巡检轮, 0 改动 0 restart. cc2 (cc4101-primary) 30min 2 req 全 200 (session 间歇空闲).
- DB 快照 (00:50): dsv4p_nv 全 caller 30min SR=76.5% (13/17), 全来自非缓冲 caller hermes + 2×cc2 primary.
  - 13×200: key2×11 + key0×1 + key1×1, egress 203.10.96.139×11, avg 12014ms (ttfb 12121, max 30653, min 3279), finish tool_calls×9 + stop×4.
  - 4×all_tiers_exhausted (avg 1594ms, 无 key/IP 归属, mapped-tier 直接失败).
  - 4×429 (16:30/16:35/16:40/16:45 限速模式, hermes caller 非 cc2).
  - 30min fallback: f×17 (0 fallback 发生).
  - 分钟趋势: 16:20-16:26 连续出 11×200 → 16:30/16:35/16:40/16:45 4×429 限速窗口 → 16:44 恢复 2×200.
- cc2 (cc4101-primary) 30min: 2×200 (avg 3414ms), 0 fail, 100% SR — 链路健康.
- glm5_2_nv 30min 0 req — 无健康数据.
- 30min nv_tier_attempts: 0 行 (无缓冲 caller 流量, 无 tier 尝试日志).
- 30min buffer/wait/keymanager 日志: 无 (cc2 缓冲流量极低, 2×200 直接成功不进 buffer).
- 错误类型无新增, 与 R268-R421 一致 (**一百四十四轮一致**).
- 链路自恢复 (ProbeWorker + KeyManager decayed reset + buffer 5key 轮转) 持测有效.
- 容器健康: nv_gw /health=ok, 5key, nv_num_keys=5; nv_gw Up 10h, cc4101 Up 6min, ms_gw Up 3d, logs_db Up 3d.

## 判稳
- **NOP 巡检轮**. cc2 primary 2/2 (100% SR), 链路健康, 0 fallback 0 deadline.
- dsv4p_nv 本轮快照 SR=76.5% (13/17), 较 R420 (86.4%) 略降 9.9pp, 仍在 NVCF function 配额波动区间.
- dsv4p 错误类型无新增, 与 R268-R421 一致 (一百四十四轮一致).
- 切换 PRIMARY_UPSTREAM_MODEL 到 glm5_2_nv 是大改: cc2 缓冲 caller 2 req + glm5_2_nv 30min 0 req,
  无 buffer 路径数据支撑, 不满足"改前必有数据"铁律 → 暂不切.

## 根因 (沿用 R278-R421, 非代码缺陷)
- 非缓冲 caller hermes mapped-tier 直接走 NVCF, function 配额瞬时空位 → 429/all_tiers_exhausted.
- 5key (k0-k4) 全绑同一 NVCF function, function 级配额耗尽时多 key 同时收 429.
- buffer 5key 轮转设计针对 key/IP 级隔离, 对 function 级 429 是已知盲区.
- cc2 缓冲 caller 走 buffer 路径不走 mapped-tier, 不受影响 (本轮 2×200 直接成功).

## 下一步
- 继续 NOP 巡检, 等 cc2 流量恢复后观察 dsv4p_nv buffer 路径行为.
- 关注新错误类型 (非 all_tiers_exhausted) 或 key/IP 级故障, 再决定是否介入.
- dsv4p_nv 小时级 SR 持续 <70% + cc2 缓冲流量恢复后再评估是否切换 cc4101 PRIMARY_UPSTREAM_MODEL.
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
