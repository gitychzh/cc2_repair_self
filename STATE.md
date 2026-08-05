# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: R795 (NOP 巡检 + R794 后置验证, 2026-08-05 ~09:00 CST)
> 上轮: R794 (DB function_id + upstream 透传 + mihomo 排除 HK, 跨 HM1/HM2, commit db0fbc9)

## 本轮 (R795) 改了什么 + 依据 + 验证

### 改动: 不改码 (NOP) — R794 后置验证轮

### 依据 (轮前链路分析 08:50 CST + 自查 DB, 30min 窗口, R794 restart 后)
- **cc2 (cc4101-primary|glm5_2_nv): 91 req × 200 (SR=100%), 0 fb, 0 穿透** ✅
- 连续 58 轮 (R735~R795) SR 100%, fb 0%
- cc4101 总览 (含其他 caller): 945 req, ok=934, fb=9, SR=98.8%
  - 499×11 on glm5_2_nv primary fb=0 → client_gone_mid_stream (客户端主动断连, 非 NVCF 失败)
  - fb 9 = glm5_2_ms(7) + dsv4f_nv(2) 走 fallback 路径, **非 cc2 请求**
- tier 噪声 **19** (与 R793 持平): NVCFPexecRemoteDisconnected×17 均布 k0-k4 + empty_200×2
- 顶层 all_tiers_exhausted×4 全在 dsv4 hermes caller, 零穿透到 cc2
- buffer 日志实测: 全 attempt=1/-SUCCESS, elapsed 3-18s, 无 retry/WAIT/KEYMGR/BREAKER
- nv_gw StartedAt=2026-08-04T18:52 UTC (= 2026-08-05 02:52 CST) = R794 restart 后

### R794 端到端三维落库验证 (实测 30min, npm/网关链路无影响)
- nv_requests (cc2 91 全 200): 全走 fid `b1b22d03-` (K1 pexec fid1), 4 美国 IP 实测 134.195.101.{180,193,195}+1 空, 5 mihomo 端口 7894/7896/7897/7899/7901 全工作
- nv_tier_attempts: 主 fid b1b22d03 (84 attempts k0-k4) + 备 fid 52e1ddb6 (20 attempts k0-k4 均布) → buffer 选 fid 工作
- function_id + egress_ip + egress_route 三维全落库 ✅ — R794 改动端到端成功

### 验证 (NOP 无 restart)
- 容器: nv_gw Up 6h (= R794 restart 后续), cc4101 Up 7h, dsv4p_nv40066 Up 12h, logs_db Up 5d, ms_gw Up 7h
- /health: nv_gw ok nv_num_keys=5; cc4101 ok primary=glm5_2_nv

## 判稳结论
- **cc2 nv_gw 链路连续 58 轮 (R735~R795) SR 100%, fb 0%** — 达标 (目标 SR 99%+/fb <10%)
- R794 改动 (DB+upstream透传+mihomo) 验证未破坏链路, function_id/egress_ip/egress_route 三维落库
- tier 噪声 19 零穿透, RemoteDisc 17 均布 k0-k4 非单 key 故障, buffer 全吸收
- RemoteDisc 偏高已连续 4 轮 (R791:12+R792:12+R793:16+R795:17) — NVCF-sided 周期性 jitter, 非链路缺陷
- 判定: 链路健康无可改项, NOP 巡检轮
- cleanest 计数仍停 27 (R774)

### SR 趋势
| 轮 | 30min SR | tier 噪声 | 备注 |
|---|---|---|---|
| R791 | 100% (113) | 12 | k3 RemoteDisc 5 偏高续 |
| R792 | 100% (101) | 14 | RemoteDisc 12 均布 k0-k4 |
| R793 | 100% (91)  | 19 | RemoteDisc 16 均布 k0-k4 偏高 |
| R795 | 100% (91)  | 19 | R794 改动后置验证, RemoteDisc 17 持平偏高 |

(R794 是改码轮, 不在此趋势表统计, 其 R794 改动生效窗口即 R795 的数据)

## 下一步
- 持续监控 cc2 SR + fb (目标 SR 99%+/fb <10%)
- R794 后置下轮可拉 function_id × egress_ip × key 立体限速诊断
- RemoteDisc 偏高模式 (连续 4 轮 12~17) 若连续多轮且偶发穿透 cc2 → 排查 NVCF pexec 端点
- dsv4p_nv fallback 链路健康, 应急 OK
- nv_gw 容器 StartedAt 2026-08-05 02:52 CST (= R794 restart), 下轮以新 uptime 为基线
- 注意并行 R-dsv4f-fallback / R1024 dsv4f0731_nv 线工作 (另一 session) 在 nv_gw 上注册 dsv4f_nv 做 DEFAULT_NV_MODEL 兜底 — 不属我职责, 但下轮需确认 cc2 glm5_2_nv tier 顺序没被改回 (env: PRIMARY_UPSTREAM_MODEL=glm5_2_nv), 不要主动切换

## 参数快照 (R795, 实测无变化)
- nv_gw: NVU_DISABLE_MS_FALLBACK=1, UPSTREAM_TIMEOUT=90, TIER_TIMEOUT_BUDGET_S=180, TIER_COOLDOWN_S=180
- nv_gw: NVU_CALLER_KEY_MAP=hermes:2;openclaw:3;opencode:4
- nv_gw: NVU_BUFFER_CALLERS=cc4101-primary,openclaw2, NVU_PEER_FB_SKIP_MODELS=glm5_2_nv,dsv4p_nv
- nv_gw: MIN_OUTBOUND_INTERVAL_S=10, NVU_FORCE_STREAM_UPGRADE_TIMEOUT=150, KEY_COOLDOWN_S=30, NV_INTEGRATE_KEY_COOLDOWN_S=90
- nv_gw: DB 列加 = function_id TEXT + egress_ip/egress_route TEXT + 复合索引 (R794, 两机)
- nv_gw: StartedAt 2026-08-05 02:52 CST (= R794 restart 后)
- cc4101: PRIMARY=glm5_2_nv→nv_gw:40006, FALLBACK=ms_gw:40007(env), STREAM_TOTAL=470, HEADER=400
- 链路: cc2→cc4101(4101)→nv_gw(40006, glm5_2_nv)→NVCF
