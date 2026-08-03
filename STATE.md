# R669 — NOP 巡检轮 — cc2 链路无流量, cc4101 真实 SR100%, R661 修复窗口 ~9h 无 IncompleteRead 再现

> 时间: 2026-08-03 17:15 CST (09:15 UTC)
> 上轮: R668 (NOP, R661 修复窗口 7h 无再现)
> 容器: nv_gw Up 41min (restart@08:02 UTC), cc4101 Up ~1h, dsv4p_nv40066 Up ~1h

## 判稳结论: NOP (不改码)

R661 (handlers.py:1853 NV-ANTH-COLLECT-BUFRETRY) restart @08:02 UTC 后 ~9h 窗口:
- cc2 (cc4101-primary/glm5_2_nv) 30min: 0 请求 (cc2 自身无流量)
- cc4101 真实 SR 30min=100% (16/16, fb=1) — 1 次 dsv4p_nv fallback 成功覆盖
- 30min 非 200: all_tiers_exhausted×5 → hermes|dsv4p_nv 5key 全 429 (NVCF 侧配额型, 非 cc2 链路)
- nv_tier_attempts 30min: 0 行 (无 tier 级错误)
- 无 BUFFER/WAIT/NV-ANTH-COLLECT 日志
- NVAnthCollect_IncompleteRead 仍无再现 (最后一次 @07:50:34 UTC, 早于 R661 restart @08:02) → R661 修复窗口 ~9h 干净
- /health ok 5keys, 配置无漂移, 容器都 Up → NOP

## 基线 (R669 实测)
- cc2 (cc4101-primary/glm5_2_nv) nv_gw 30min: 0 req (无流量)
- cc4101 真实 SR 30min=100% (16/16, fb=1) — 1 次 dsv4p_nv fallback 成功
- 30min 非 200: all_tiers_exhausted×5 (hermes|dsv4p_nv 429, NVCF 配额型)
- nv_tier_attempts 30min: 0 行
- 6h stream_total_deadline: 0 (deadline 链健康)
- NVAnthCollect_IncompleteRead 最后: 07:50:34 UTC (R661 restart @08:02 前, 已 9h 无再现)
- /health ok 5keys, 配置无漂移, 无启动错误, 容器都 Up

## 下一步
- 等下一波 cc4101-primary 流量 → 查 NV-ANTH-COLLECT-BUFRETRY 日志判断 R661 是否生效
- 若 IncompleteRead 再现仍落 502 → 深查 handlers.py:1853 触发条件是否命中
- hermes/dsv4p all_tiers_exhausted 配额型持续 → 关注 dsv4p_nv40066 fallback 路径可用性 (本轮 1 次 fb 成功说明 fallback 健康)

## 参数快照 (无变化, 沿用 R661)
- nv_gw: NVU_DISABLE_MS_FALLBACK=1, buffer 5×90s=450s, UPSTREAM_TIMEOUT=90, TIER_COOLDOWN_S=180
  - per-key FID bind: NV_GLM52_KEY_FID_BIND=0:0;2:1;4:2 (k0/k2/k4 pexec fid1/2/3)
  - per-key mode bind: NV_GLM52_KEY_MODE_BIND=0:pexec_us_rr;1:integrate_us_rr;2:pexec_us_rr;3:integrate_us_rr;4:pexec_us_rr
- cc4101: PRIMARY=glm5_2_nv→nv_gw:40006, FALLBACK=dsv4p_nv→dsv4p_nv40066:40066, STREAM_TOTAL=470, HEADER=400, UPSTREAM_IDLE=150
- deadline 链: 90s×5=450s buffer < 470s cc4101 < 600s API < 900s idle
