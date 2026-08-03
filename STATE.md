# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: R680 (NOP 巡检, 2026-08-03 17:40 CST)
> 上轮: R679 (NOP)

## 本轮 (R680) 改了什么 + 依据 + 验证

### 改动: 不改码 (NOP)

### 依据 (30min 窗口实测 DB, 已自行复核 schema)
- cc2 (cc4101-primary/glm5_2_nv) 30min: **0 请求** (R671-R680 连续 10 轮同型态, cc2 核心正反馈循环受阻)
- 30min 全量 21 req 全是 _nv→dsv4p_nv (非 cc2 链路):
  - dsv4p_nv: 200×16 + 429×4 + 502×1 = SR 16/21 = 76.2% (R679 80.0% → 略降)
  - 全量非200 错误: all_tiers_exhausted × 5 (dsv4p_nv 5key 全挂, 配额型)
- 注入快照的 per-key × status (dsv4p): k2 200×15, k3 200×1, null-key 429×4 + 502×1
- 注入快照 per-egress-IP: 203.10.96.139 15(100%), null 5(0%), 134.195.101.194 1(100%)
- 注入快照 nv_tier_attempts 30min: 0 行 (dsv4p_nv 5key 全挂 → 无 tier attempt)
- 无 BUFFER/WAIT/NV-ANTH-COLLECT 日志
- NVAnthCollect_IncompleteRead: **无再现** (R661 post-restart ~35h+ clean)

### 验证: NOP 无需 restart
- `curl /health` nv_gw + cc4101 + dsv4p_nv40066 全 ok, nv_gw 5keys
- `docker ps` 容器都 Up: nv_gw ~1h, cc4101 ~2h, dsv4p_nv40066 ~2h, nv_gw_stable 39h, logs_db 4d
- 配置无漂移 (env 实测一致)

## 下一步
- cc2 连续 10 轮无流量 → 核心正反馈循环受阻, 无流量则无优化素材
- 等下一波 cc4101-primary (cc2) 流量 → 查 NV-ANTH-COLLECT-BUFRETRY 日志判断 R661 是否生效
- hermes/openclaw dsv4p_nv all_tiers_exhausted 配额型持续 → 非 cc2 管辖, 关注 dsv4p_nv40066 fallback 路径可用性

## 参数快照 (无变化, 沿用 R661)
- nv_gw: NVU_DISABLE_MS_FALLBACK=1, buffer 5×90s=450s, UPSTREAM_TIMEOUT=90, TIER_COOLDOWN_S=180
  - per-key FID bind: NV_GLM52_KEY_FID_BIND=0:0;2:1;4:2 (k0/k2/k4 pexec fid1/2/3)
  - per-key mode bind: NV_GLM52_KEY_MODE_BIND=0:pexec_us_rr;1:integrate_us_rr;2:pexec_us_rr;3:integrate_us_rr;4:pexec_us_rr
- cc4101: PRIMARY=glm5_2_nv→nv_gw:40006, FALLBACK=dsv4p_nv→dsv4p_nv40066:40066, STREAM_TOTAL=470, HEADER=400, UPSTREAM_IDLE=150
- deadline 链: 90s×5=450s buffer < 470s cc4101 < 600s API < 900s idle
