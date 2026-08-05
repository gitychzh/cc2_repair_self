# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: R782 (NOP 巡检, 2026-08-05 ~08:11 CST)
> 上轮: R781 (NOP, 47th consecutive 100%)

## 本轮 (R782) 改了什么 + 依据 + 验证

### 改动: 不改码 (NOP)

### 依据 (轮前链路分析 ~08:10 CST, 30min 窗口)
- **cc2 (cc4101-primary|glm5_2_nv): 79 req × 200 (SR=100%), 0 错误, 0 fallback** ✅
- **cc4101-primary caller: 79 nv / 79 ok / 0 err — 零穿透坐实**
- avg_dur 29696ms — 稳定
- **tier 噪声 22** (NVCFPexecRemoteDisconnected×17 + pexec_429×1 + empty_200×2 + 529_nv_overloaded×2) — 全被 buffer/KeyManager 消化, cc4101-primary 零穿透
- 噪声分布:
  - RemoteDisc ×17: k0:3+k2:3+k3:4+k4:6 (k1:0，k4 偏多但在容错范围)
  - pexec_429 ×1: k0 (单次 429，KeyManager 退避消化)
  - empty_200 ×2: k1+k3 (NVCF 偶发空响应, buffer retry 1 次消化)
  - 529_nv_overloaded ×2: k1+k2 (NVCF 偶发过载, 不持续)
- per-key pexec_success: k0:15+k1:14+k2:17+k3:17+k4:15 = 78 (全 attempt=1 即 success)
- 无 buffer/wait 日志 (全 attempt=1 即 success, 未触发 retry/backoff)
- 注入噪声 (dsv4f0731_nv 502×9 + all_tiers_exhausted×8 + zombie_empty×1) 全在 dsv4 hermes caller — 零穿透到 cc2
- dsv4p_nv 本身 SR=100% (30/30), per-key 均衡 (k0:7+k1:6+k2:6+k3:6+k4:5), fallback 链路健康

### 验证 (NOP 无需 restart)
- 容器: nv_gw Up 10h, cc4101 Up 6h — 运行中
- 注入链路分析实测 cc4101-primary: 79 nv / 79 ok / 0 err — 链路健康, 零穿透坐实

## 判稳结论
- **cc2 nv_gw 链路连续 48 轮 (R735~R782) SR 100%, fb 0%** — 全面达标 (目标 SR 99%+/fb <10%)
- **本轮 tier 噪声 22** (上轮 20→22, +2) — buffer 容错有效, 全 attempt=1 success, cc4101-primary 零错误
- 流量 79 req/30min (上轮 70→79, +9，正常波动)
- 429 噪声回归 (上轮 0→1) — 单次偶发, KeyManager 退避消化, 无需介入
- NOP 巡检轮 — 链路已稳, 无可改项
- cleanest 计数停在 27 (R774) — R774 后每轮 tier 噪声均>0, not cleanest

### SR 趋势
| 轮 | 30min 窗 SR | tier 噪声 | 备注 |
|---|---|---|---|
| R774 | 100% (95/95) | 0 | 40th, 27th cleanest |
| R775 | 100% (83/83) | 20 | 41st, cleanest 停 27 |
| R776 | 100% (82/82) | 19 | 42nd consecutive 100% |
| R777 | 100% (80/80) | 17 | 43rd consecutive 100% |
| R778 | 100% (57/57) | 16 | 44th consecutive 100% |
| R779 | 100% (67/67) | 18 | 45th consecutive 100% |
| R780 | 100% (71/71) | 20 | 46th consecutive 100% |
| R781 | 100% (70/70) | 20 | 47th consecutive 100% |
| R782 | 100% (79/79) | 22 | **48th consecutive 100%, cleanest 停 27** |

## 下一步
- 持续监控 cc2 SR + fb 触发率 (目标 SR 99%+/fb <10%)
- tier 噪声 22 (17 RemoteDisc + 1 pexec_429 + 2 empty_200 + 2 529) 仍在 buffer 容错范围 — 不影响 cc2 可见 SR
- 关注 k4 RemoteDisc 偏多 (6 次) — 若持续升高可考虑排查 k4 fid3 (b6029a96) 健康
- 注入噪声 (dsv4f0731_nv 502×9 + all_tiers_exhausted×8 + zombie_empty×1) 全在 dsv4 hermes caller, 非本链路问题
- dsv4p_nv fallback 链路健康 (SR=100% 30/30), 应急链路 OK

## 参数快照 (R782, 实测一致无变化)
- nv_gw: NVU_DISABLE_MS_FALLBACK=1, UPSTREAM_TIMEOUT=90, TIER_TIMEOUT_BUDGET_S=180, TIER_COOLDOWN_S=180
- nv_gw: NVU_CALLER_KEY_MAP=hermes:2;openclaw:3;opencode:4
- nv_gw: NVU_BUFFER_CALLERS=cc4101-primary,openclaw2, NVU_PEER_FB_SKIP_MODELS=glm5_2_nv,dsv4p_nv
- nv_gw: MIN_OUTBOUND_INTERVAL_S=10, NVU_FORCE_STREAM_UPGRADE_TIMEOUT=150, KEY_COOLDOWN_S=30, NV_INTEGRATE_KEY_COOLDOWN_S=90
- cc4101: PRIMARY=glm5_2_nv→nv_gw:40006, FALLBACK=ms_gw:40007(glm5_2_ms), STREAM_TOTAL=470, HEADER=400, PRIMARY_FAIL_THRESHOLD=3, PRIMARY_SKIP_S=30
- 链路: cc2→cc4101(4101)→nv_gw(40006, glm5_2_nv)→NVCF | fallback→dsv4p_nv40066(40066) [cc4101 env FALLBACK_UPSTREAM_URL=ms_gw:40007 与 CLAUDE.md 描述 dsv4p 不符, 以注入实测为准未触动]
