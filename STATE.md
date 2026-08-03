# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: R677 (NOP 巡检, 2026-08-03 17:15 CST)
> 上轮: R676 (NOP)

## 本轮 (R677) 改了什么 + 依据 + 验证

### 改动: 不改码 (NOP)

### 依据 (30min 窗口实测, 轮前链路分析注入)
- cc2 (cc4101-primary/glm5_2_nv) 30min: **0 请求** (cc2 自身无流量, R672-R677 连续 6 轮同型态)
- cc4101 fallback 发生率: fb=39 (全部 hermes/openclaw→dsv4p_nv 路径, 非 cc2 链路)
- 30min nv_gw 总: 200×34 + 429×1 + 502×4 = dsv4p_nv SR 87.2% (39 req)
  - 全部 39 请求是 hermes + openclaw caller, 全走 dsv4p_nv (非 cc2 链路 glm5_2_nv)
  - 4 个 502 全是 all_tiers_exhausted (dsv4p_nv 5key 全 429), avg_dur 40810ms
    - hermes/dsv4p_nv: 200×30 + 429×1 + 502×3 (SR 90.9%)
    - openclaw/dsv4p_nv: 200×4 + 502×1 (SR 80%)
  - per-key: k2 200×30 (9574ms avg), k3 200×4 (8302ms avg), 502×4 (null key = 全挂后无 tier attempt)
  - 1 个 429 (null key, 7269ms) — dsv4p_nv 单 key 配额拒绝
  - per-egress-IP: 203.10.96.139 200×30 (100%), 134.195.101.194 200×4 (100%), null IP 5 (0% = 全挂后无 egress)
  - dsv4p 200 finish_reason: tool_calls×31 + stop×3 (无 zombie)
- nv_tier_attempts 30min: **0 行** (dsv4p_nv 5key 全 429 → 无 tier attempt 记录)
- 无 BUFFER/WAIT/NV-ANTH-COLLECT/NV-BREAKER 日志
- NVAnthCollect_IncompleteRead: **无再现** (R661 post-restart @08:02 UTC ~33h+ clean, 与 R676 一致)
- /health ok 5keys, 配置无漂移, 容器都 Up (nv_gw ~1h, cc4101 ~2h, dsv4p_nv40066 ~2h)

### 验证: NOP 无需 restart
- `curl /health` nv_gw + cc4101 + dsv4p_nv40066 ok
- `docker ps` 容器都 Up (nv_gw ~1h, cc4101 ~2h, dsv4p_nv40066 ~2h, logs_db 4 days)
- 无新错误, 无 NV-ANTH-COLLECT/IncompleteRead 再现

## 下一步
- 等下一波 cc4101-primary (cc2) 流量 → 查 NV-ANTH-COLLECT-BUFRETRY 日志判断 R661 是否生效
- 若 IncompleteRead 再现仍落 502 → 深查 handlers.py 触发条件
- hermes/openclaw dsv4p_nv all_tiers_exhausted 配额型持续 → 关注 dsv4p_nv40066 fallback 路径可用性

## 参数快照 (无变化, 沿用 R661)
- nv_gw: NVU_DISABLE_MS_FALLBACK=1, buffer 5×90s=450s, UPSTREAM_TIMEOUT=90, TIER_COOLDOWN_S=180
  - per-key FID bind: NV_GLM52_KEY_FID_BIND=0:0;2:1;4:2 (k0/k2/k4 pexec fid1/2/3)
  - per-key mode bind: NV_GLM52_KEY_MODE_BIND=0:pexec_us_rr;1:integrate_us_rr;2:pexec_us_rr;3:integrate_us_rr;4:pexec_us_rr
- cc4101: PRIMARY=glm5_2_nv→nv_gw:40006, FALLBACK=dsv4p_nv→dsv4p_nv40066:40066, STREAM_TOTAL=470, HEADER=400, UPSTREAM_IDLE=150
- deadline 链: 90s×5=450s buffer < 470s cc4101 < 600s API < 900s idle
