# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: R682 (NOP 巡检, 2026-08-03 18:00 CST)
> 上轮: R681 (NOP)

## 本轮 (R682) 改了什么 + 依据 + 验证

### 改动: 不改码 (NOP)

### 依据 (30min 窗口注入快照)
- cc2 (cc4101-primary/glm5_2_nv) 30min: **0 请求** (R671-R682 连续 12 轮同型态, cc2 核心正反馈循环受阻)
- 30min 全量 16 req 全是 hermes/openclaw → dsv4p_nv (非 cc2 链路):
  - dsv4p_nv: 200×10 + 429×5 + 502×1 = SR 10/16 = 62.5% (R681 62.5% → 持平)
  - 全量非200: all_tiers_exhausted ×6 (dsv4p_nv 5key 全挂, 配额型)
- per-key × status (dsv4p): k2 200×9, k3 200×1, null-key 429×5 + 502×1
- per-egress-IP: 203.10.96.139 9(100%), null 6(0%), 134.195.101.194 1(100%)
- nv_tier_attempts 30min: 0 行 (dsv4p_nv 5key 全挂 → 无 tier attempt)
- 30min 按分钟趋势: 09:05 200×6, 09:06 502×1, 09:10 200×2+429×1, 09:15 429×1, 09:20 429×1, 09:25 200×2+429×1, 09:30 429×1
- 无 BUFFER/WAIT/NV-ANTH-COLLECT 日志
- NVAnthCollect_IncompleteRead: **无再现** (R661 post-restart ~40h+ clean)

### 验证: NOP 无需 restart
- `curl /health` nv_gw + cc4101 + dsv4p_nv40066 全 ok, nv_gw 5keys
- `docker ps` 容器都 Up: nv_gw ~2h, cc4101 ~2h, dsv4p_nv40066 ~2h, nv_gw_stable 40h, logs_db 4d, ms_gw 4d
- 配置无漂移 (env 实测一致)

## 下一步
- cc2 连续 12 轮无流量 → 核心正反馈循环受阻, 无流量则无优化素材
- 等下一波 cc4101-primary (cc2) 流量 → 查 NV-ANTH-COLLECT-BUFRETRY 日志判断 R661 是否生效
- hermes/openclaw dsv4p_nv all_tiers_exhausted 配额型持续 → 非 cc2 管辖, 关注 dsv4p_nv40066 fallback 路径可用性

## 参数快照 (无变化, 沿用 R661)
- nv_gw: NVU_DISABLE_MS_FALLBACK=1, buffer 5×90s=450s, UPSTREAM_TIMEOUT=90, TIER_COOLDOWN_S=180
  - per-key FID bind: NV_GLM52_KEY_FID_BIND=0:0;2:1;4:2 (k0/k2/k4 pexec fid1/2/3)
  - per-key mode bind: NV_GLM52_KEY_MODE_BIND=0:pexec_us_rr;1:integrate_us_rr;2:pexec_us_rr;3:integrate_us_rr;4:pexec_us_rr
- cc4101: PRIMARY=glm5_2_nv→nv_gw:40006, FALLBACK=dsv4p_nv→dsv4p_nv40066:40066, STREAM_TOTAL=470, HEADER=400, UPSTREAM_IDLE=150
- deadline 链: 90s×5=450s buffer < 470s cc4101 < 600s API < 900s idle
