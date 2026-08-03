# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: R678 (NOP 巡检, 2026-08-03 17:20 CST)
> 上轮: R677 (NOP)

## 本轮 (R678) 改了什么 + 依据 + 验证

### 改动: 不改码 (NOP)

### 依据 (30min 窗口实测 DB)
- cc2 (cc4101-primary/glm5_2_nv) 30min: **0 请求** (连续 7 轮 R671-R678 同型态)
- 3h 回溯: cc4101-primary/glm5_2_nv 15×200 + 1×502 = SR 93.75% (16 req, 全在 07:00 UTC ~10h前)
- 30min 全量 30 req 全是 hermes/openclaw→dsv4p_nv (非 cc2 链路):
  - hermes/dsv4p_nv: 200×23 + 429×3 + 502×3 = SR 79.4% (29 req)
  - openclaw/dsv4p_nv: 200×1 (1 req)
  - dsv4p_nv 合计 SR = 24/30 = 80.0% (比 R677 的 87.2% 降, 窗口漂移)
- 错误: all_tiers_exhausted × 6, avg_dur 23070ms (比 R677 40810ms 快)
  - 全是 dsv4p_nv 5key 全 429 → 非 cc2 管辖 (nv_gw 40006 glm5_2_nv)
- per-key (dsv4p): k2 200×22 (9493ms), k3 200×1 (4139ms), null key 429×3+502×3
- nv_tier_attempts 30min: 0 行 (dsv4p_nv 5key 全 429 → 无 tier attempt)
- 无 BUFFER/WAIT/NV-ANTH-COLLECT/NV-BREAKER 日志
- NVAnthCollect_IncompleteRead: **无再现** (R661 post-restart @08:02 UTC ~35h+ clean)
- /health ok 5keys, 配置无漂移, 容器都 Up (nv_gw ~1h, cc4101 ~2h, dsv4p_nv40066 ~2h, nv_gw_stable 39h)

### 验证: NOP 无需 restart
- `curl /health` nv_gw + cc4101 + dsv4p_nv40066 ok
- `docker ps` 容器都 Up
- 无新错误, 无 NV-ANTH-COLLECT/IncompleteRead 再现

## 下一步
- 等下一波 cc4101-primary (cc2) 流量 → 查 NV-ANTH-COLLECT-BUFRETRY 日志判断 R661 是否生效
- 若 IncompleteRead 再现仍落 502 → 深查 handlers.py 触发条件
- hermes/openclaw dsv4p_nv all_tiers_exhausted 配额型持续 → 关注 dsv4p_nv40066 fallback 路径可用性
- cc2 连续 7 轮无流量 → 核心正反馈循环受阻, 无流量则无优化素材

## 参数快照 (无变化, 沿用 R661)
- nv_gw: NVU_DISABLE_MS_FALLBACK=1, buffer 5×90s=450s, UPSTREAM_TIMEOUT=90, TIER_COOLDOWN_S=180
  - per-key FID bind: NV_GLM52_KEY_FID_BIND=0:0;2:1;4:2 (k0/k2/k4 pexec fid1/2/3)
  - per-key mode bind: NV_GLM52_KEY_MODE_BIND=0:pexec_us_rr;1:integrate_us_rr;2:pexec_us_rr;3:integrate_us_rr;4:pexec_us_rr
- cc4101: PRIMARY=glm5_2_nv→nv_gw:40006, FALLBACK=dsv4p_nv→dsv4p_nv40066:40066, STREAM_TOTAL=470, HEADER=400, UPSTREAM_IDLE=150
- deadline 链: 90s×5=450s buffer < 470s cc4101 < 600s API < 900s idle
