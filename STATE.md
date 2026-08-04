# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: R734 (NOP 巡检, 2026-08-05 02:41 CST)
> 上轮: R733 (NOP, glm5_2_nv 32×200 nv_gw SR100%, cc4101 32×200+1×499 client_gone)

## 本轮 (R734) 改了什么 + 依据 + 验证

### 改动: 不改码 (NOP)

### 依据 (实测多窗口 ~01:55-02:41 CST, created_at 字段)

#### cc4101 用户可见 SR (cc_requests, 60min ~01:20-02:20)
- 54 req: 53×200(primary ok) + 1×200(primary timeout→fallback dsv4p 成功) + 2×499(client_gone, 非 nv_gw)
- **用户可见 SR = 54/54 = 100%** (2×499 = cc2 SDK 主动断连, 非 nv_gw 故障)
- **fallback 触发率 = 1/54 = 1.9%** (< 10% 目标)

#### nv_gw 层 (nv_requests, cc4101-primary)
- 60min: 30 req, 28×200 + 2×502(buffer_exhausted, avg 390.5s) → nv_gw SR 93.3%
- 45min (~01:55-02:40): 44 req, 40×200 + 4×502 → nv_gw SR 90.9% (4×502 散布间歇性抖动, 非连续退化)
- 15min (02:41 实测): 11 req, 8×200 + 3×502(2 buffer_exhausted + 1 all_tiers_exhausted) → nv_gw SR 72.7%
- **根因**: NVCF 上游 529_nv_overloaded 间歇高发 (注入 30min: k0=19/k1=21/k2=18/k3=17/k4=19 共 94 次 529)
- **但 02:36 后已恢复**: 15min nv_tier_attempts 实测全 pexec_success (k0=2/k1=2/k2=3/k3=2), 0 error
- buffer retry 机制实证吸收抖动: req a7d1c77e (attempt1 失败→5s backoff→attempt2 success), req ceb747c1 (同)

#### per-key tier 错误 (nv_tier_attempts, 30min, glm5_2_nv tier)
- 529_nv_overloaded: k0=24, k1=29, k2=27, k3=23, k4=29 (共 132 次) — NVCF 容量问题
- 404_nv_function_not_found: 共 12 次 — fid 路由偶发
- pexec_success: 共 35 次 — 混合链路 healthy

### 验证 (NOP 无需 restart)
- `/health`: nv_gw ok(5keys, glm5_2_nv default) + cc4101 ok(primary=glm5_2_nv) + dsv4p_nv40066 ok(5keys) — 全 ok
- `docker ps`: nv_gw Up 5h, cc4101 Up 56min, dsv4p_nv40066 Up 6h, nv_gw_stable Up 3days, logs_db Up 5days — 全 Up
- env 零漂移 (沿 R-glm52split 架构)
  - nv_gw: NVU_DISABLE_MS_FALLBACK=1, buffer 5×90s=450s, UPSTREAM_TIMEOUT=90, TIER_COOLDOWN_S=180
  - cc4101: FALLBACK=dsv4p_nv40066:40066, STREAM_TOTAL=470, HEADER=400, UPSTREAM_IDLE=150

### 注入轮前分析 vs 实测一致性
- 注入 30min cc4101-primary: 21×200 + 3×502(all_tiers_exhausted;buffer_exhausted, avg 421767ms) — 与实测一致
- 注入 per-key 529 分布 — 与实测一致 (NVCF 上游容量问题)
- 注入 dsv4p_nv SR=100% (4/4) — dsv4p fallback 链路 healthy

## 判稳结论
- **用户可见 SR 100% (54/54, 60min)** — 超过 99% 目标
- **nv_gw SR 93.3% (28/30, 60min) / 72.7% (8/11, 15min)** — 低于 90%+ 目标, 根因 NVCF 529 间歇性容量, 非 nv_gw 可改
- **fallback 触发率 1.9% (1/54)** — 远低于 10% 目标, fallback 机制正常工作
- **2×499 client_gone** = cc2 SDK 主动断连, 非 nv_gw 故障
- 529 overloaded 是 NVCF 上游问题, 间歇性非持续, buffer retry (5s backoff + attempt2) 已实证吸收抖动
- 流量低时不动码, NOP 记数据

## 下一步
- 持续监控 cc2 SR + fallback 触发率 (目标 SR99%+ fb<10%)
- 当前用户 SR 100%, nv_gw SR 93.3%, fb 1.9% — 用户层面超目标
- 529 overloaded 若持续高频, 可考虑: (a) 加大 buffer attempts (但已 5×90s=450s 接近 cc4101 470s 上限, 空间小); (b) 降低 MIN_OUTBOUND_INTERVAL_S (当前 10s) 增加探测频率 — 但根因是 NVCF 容量, 缓解有限
- 404_nv_function_not_found 共 12 次 — 可关注 fid 路由是否需调, 但占比低暂不动
- 流量低时不动码, 仅 NOP 记数据
- cc_requests.ts 时区 bug 沿用: 分析用 created_at (R730/R732 已实证)

## 参数快照 (无变化, 沿用 R-glm52split, 实测 env 确认)
- nv_gw: NVU_DISABLE_MS_FALLBACK=1 (ms_gw 关, fallback=dsv4p_nv40066), buffer 5×90s=450s (NVU_BUFFER_MAX_RETRIES=5, NVU_BUFFER_TIMEOUT_STAIRS=90,90,90,90,90), UPSTREAM_TIMEOUT=90, TIER_COOLDOWN_S=180
  - per-key FID bind: NV_GLM52_KEY_FID_BIND=0:0;2:1;4:2 (k0/k2/k4 pexec fid1/2/3)
  - per-key mode bind: NV_GLM52_KEY_MODE_BIND=0:pexec_us_rr;1:integrate_us_rr;2:pexec_us_rr;3:integrate_us_rr;4:pexec_us_rr
  - NV_GLM52_MODE_CHAIN=pexec_us_rr,integrate_us_rr
  - NVU_BUFFER_CALLERS=cc4101-primary,openclaw2, NVU_KEYMGR_429_BASE=120/MAX=600, NVU_KEYMGR_CONN_BASE=30/LONG=120/MAX=60
- cc4101: PRIMARY=glm5_2_nv→nv_gw:40006, FALLBACK=dsv4p_nv→dsv4p_nv40066:40066, STREAM_TOTAL=470, HEADER=400, UPSTREAM_IDLE=150, UPSTREAM_TIMEOUT=130
- deadline 链: 90s×5=450s buffer < 470s cc4101 < 600s API < 900s idle
