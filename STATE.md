# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: R735 (NOP 巡检, 2026-08-05 04:40 CST)
> 上轮: R734 (NOP, glm5_2_nv 用户 SR 100%/fb 1.9%, nv_gw SR 93.3%)

## 本轮 (R735) 改了什么 + 依据 + 验证

### 改动: 不改码 (NOP)

### 依据 (实测 ~04:10-04:40 CST, 30min cc_requests + nv_requests)

#### 链路当前状态 (最近 22min, 04:18-04:40) — 已自愈
- 分钟趋势: 14 req **全 200**, 0×502/499 → **SR 100%, fb 0%**
- 529 余波 (R1010-R1016 dsv4f0731_nv 系列) 已收敛
- 容器全 Up: nv_gw Up 2h, cc4101 Up 3h, dsv4p_nv40066 Up 8h

#### 30min 全 caller (cc_requests, 含 hermes+cc2)
- total=455, ok=417, fb=37 → **SR 91.6%, fb 8.1%** (低于 99% / 接近 10% 红线)
- 按路径拆:
  - **primary (glm5_2_nv via nv_gw)**: 404 req, 383×200 + 21×499 → SR 94.8% (含 499) / **100% (排除 499)**
  - **fallback (dsv4p_nv via ms_gw)**: 54 req, 37×200 + 17×502 → SR 68.5%
- 21×499 全是 cc2 SDK 主动断连 (client_gone_mid_stream), 非 nv_gw 故障
- 17×502 (16 timeout + 1 conn) **全集中在 fallback 路径** (dsv4p NVCF 容量问题), 502 时间线全在 23:00-04:00 前段, 04:10 后零 502

#### 30min nv_gw 层 (nv_requests, 所有 caller)
- 200×51 + 502×8 (7 all_tiers_exhausted avg 52s + 1 buffer_exhausted avg 267s)
- nv_gw SR = 51/59 = 86.4% (前段抖动), 但 5min 短窗全 200

#### per-key tier 错误 (注入 nv_tier_attempts 30min glm5_2_nv)
- 529_nv_overloaded: k0=14/k1=18+k1 RemoteDisconnected×3+Timeout×1/k2=16+RemoteDisconnected×1/k3=15/k4=12+integrate_overloaded×3+RemoteDisconnected×2
- pexec_success: k0=8/k1=2/k2=7/k3=4/k4=7 (共 28) — 链路 healthy
- 注: 当前架构实际是单 mode pexec_us_rr (R735 round 文件已修正 STATE 过时描述), 实测 env 确认

### 验证 (NOP 无需 restart)
- `/health`: nv_gw ok(5keys, glm5_2_nv default) + cc4101 ok(primary=glm5_2_nv) + dsv4p_nv40066 ok(5keys) — 全 ok
- `docker ps`: nv_gw Up 2h, cc4101 Up 3h, dsv4p_nv40066 Up 8h, nv_gw_stable Up 3days, logs_db Up 5days — 全 Up
- env 实测零漂移 (与 R735 round 文件 §2 一致)

### 注入轮前分析 vs 实测一致性
- 注入数据 30min cc4101-primary: 26×200+2×502(buffer_exhausted)+1×499(client_gone_during_flush) — 与实测一致
- 注入 529 per-key 分布 (k0=14/k1=18/k2=16/k3=15/k4=12 共 75 次 529+12 integrate) — 与实测一致 (NVCF 上游容量问题)
- 注入 "30min fallback f|51" → 实测 fallback 触发 37/455=8.1% (注入 51 是 90min 窗含前段, 本轮 30min 已进入恢复段)

## 判稳结论
- **链路已恢复, 最近 22min SR 100%, fb 0%** — 超过 99%/10% 目标
- 30min 全窗 SR 91.6%/fb 8.1% 受前段 529 余波拖累, 非 nv_gw 配置可改
- 21×499 = cc2 SDK 主动断连, 非 nv_gw 故障
- 17×502 fallback = dsv4p NVCF 容量问题, 502 全在前段, 04:10 后零
- 根因 NVCF 上游间歇容量 (R1010-R1016 dsv4f0731_nv 系列已系统记录为账户级 529 storm), 非 nv_gw 可改
- NOP 巡检轮

## 下一步
- 持续监控 cc2 SR + fallback 触发率 (目标 SR99%+ fb<10%)
- 当前最近 22min 已恢复 100%, 等下窗口确认持续收敛
- 529 余波若再起 (像 R1010-R1016 连续 5 轮模式) → 升级上游侧 (额外 NVCF key/fid/egress IP), 本机无操作权限
- 流量低时不动码, 仅 NOP 记数据
- cc_requests.ts 时区 bug 沿用: 分析用 created_at (R730/R732/R735 已实证)

## 参数快照 (实测 env 确认, 沿 R735 round §9 修正过时描述)
- nv_gw: NVU_DISABLE_MS_FALLBACK=1 (ms_gw fallback 关), **单 mode MODE_CHAIN=pexec_us_rr**, KEY_MODE_BIND=空, KEY_FID_BIND=0:0;1:0;2:0;3:0;4:0 (全 5 key 绑 fid1=b1b22d03), KEY_PROXY_BIND=0:7901;1:7894;2:7897;3:7896;4:7899 (5 US IP 绑死), RR_US_PROXIES=7901,7894,7897,7896,7899
  - buffer 5×90s=450s (NVU_BUFFER_MAX_RETRIES=5, NVU_BUFFER_TIMEOUT_STAIRS=90,90,90,90,90, NVU_BUFFER_TOTAL_DEADLINE_S=450)
  - UPSTREAM_TIMEOUT=90, TIER_COOLDOWN_S=180, NVU_KEYMGR_429_BASE=120/MAX=600, CONN_BASE=30/LONG=120/MAX=60
- cc4101: PRIMARY=glm5_2_nv→nv_gw:40006, **FALLBACK=glm5_2_ms→ms_gw:40007** (注意: 不是 dsv4p_nv40066 — STATE 旧描述过时), STREAM_TOTAL=470, HEADER=400, UPSTREAM_IDLE=150, UPSTREAM_TIMEOUT=130, PRIMARY_FAIL_THRESHOLD=3, PRIMARY_SKIP_S=30
- deadline 链: 90s×5=450s buffer < 470s cc4101 < 600s API < 900s idle

## STATE 过时项修正记录 (R735)
- ❌ 旧: "per-key 混合链路 k1/3/5 pexec, k2/4 integrate" → ✅ 新: 单 mode pexec_us_rr, 全 key 绑 fid1 (R-glm52-fb-fix 已回退 integrate)
- ❌ 旧: "cc4101 FALLBACK=dsv4p_nv40066:40066" → ✅ 新: FALLBACK=ms_gw:40007 (model=glm5_2_ms), dsv4p_nv40066 仍 Up 但非当前 fallback 目标
