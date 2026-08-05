# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: R787 (NOP 巡检, 2026-08-05 ~08:25 CST)
> 上轮: R784 (NOP, 50th consecutive 100%)  [R785/R786 被 hm2 k3-key-typo-fix 线占用]

## 本轮 (R787) 改了什么 + 依据 + 验证

### 改动: 不改码 (NOP)

### 依据 (轮前链路分析 ~08:24 CST + 实测复核, 30min 窗口)
- **cc2 (cc4101-primary|glm5_2_nv): 117 req × 200 (SR=100%), 0 错误, 0 fallback** ✅
- **本轮 tier 噪声 1** (仅 k0 pexec_429×1) — 大幅回落 (R784:19→1)
- 全 attempt=1 即 success, 无 buffer/wait
- per-key pexec_success: k0:24+k1:25+k2:22+k3:24+k4:22 = 117 (全干净 success)
- k4 RemoteDisc 连续 3 轮偏高 (R782:6+R783:6+R784:5) **本轮回落为 0** — k4 (fid3 b6029a96) 健康
- 注入噪声 (RemoteDisc×13 全 caller tier 表) 全在 dsv4 hermes caller, 零穿透 cc2
- cc_requests 聚合 (881/866 SR=98.3%) 的 15 错误全是 client_gone×14 + timeout×1, 客户端断开非 NVCF 故障, 非 cc2 链路问题

### 验证 (NOP 无需 restart)
- 容器: nv_gw Up 6h, cc4101 Up 7h, dsv4p_nv40066 Up 12h, nv_gw_stable Up 3d, logs_db Up 5d
- /health 全 ok: nv_gw passthrough(5key, pexec 含 glm5_2_nv), cc4101 primary=glm5_2_nv
- buffer 日志健康: 全 attempt=1 verdict=success_*, elapsed 4s~19s, 无 WAIT/EVENT

## 判稳结论
- **cc2 nv_gw 链路连续 51 轮 (R735~R787) SR 100%, fb 0%** — 全面达标 (目标 SR 99%+/fb <10%)
- 本轮 tier 噪声 1 (上轮 R784:19 → 1, 大幅下降) — 极干净, 接近 cleanest
- 流量 117 req/30min (上轮 R784:116, +1 持平)
- k4 RemoteDisc 自愈 — 上轮关注点解除
- NOP 巡检轮 — 链路已稳, 无可改项
- cleanest 计数仍停在 27 (R774)

### SR 趋势
| 轮 | 30min 窗 SR | tier 噪声 | 备注 |
|---|---|---|---|
| R774 | 100% (95/95) | 0 | 40th, 27th cleanest |
| R775 | 100% (83/83) | 20 | 41st, cleanest 停 27 |
| R776 | 100% (82/82) | 19 | 42nd |
| R777 | 100% (80/80) | 17 | 43rd |
| R778 | 100% (57/57) | 16 | 44th |
| R779 | 100% (67/67) | 18 | 45th |
| R780 | 100% (71/71) | 20 | 46th |
| R781 | 100% (70/70) | 20 | 47th |
| R782 | 100% (79/79) | 22 | 48th, k4 RemoteDisc 6 偏高 |
| R783 | 100% (107/107) | 20 | 49th, k4 RemoteDisc 6 续 |
| R784 | 100% (116/116) | 19 | 50th, k4 RemoteDisc 5 续 |
| R787 | 100% (117/117) | 1 | **51st, k4 RemoteDisc 回落为 0** |

## 下一步
- 持续监控 cc2 SR + fb 触发率 (目标 SR 99%+/fb <10%)
- 关注 k0 pexec_429 是否升级 (本轮单次偶发, 不构成趋势)
- k4 RemoteDisc 已自愈, 不再特别关注
- 注入噪声 (dsv4 hermes caller) 全在 dsv4 链路, 非 cc2 问题
- dsv4p_nv fallback 链路健康 (SR=100% 20/20), 应急链路 OK

## 参数快照 (R787, 实测无变化)
- nv_gw: NVU_DISABLE_MS_FALLBACK=1, UPSTREAM_TIMEOUT=90, TIER_TIMEOUT_BUDGET_S=180, TIER_COOLDOWN_S=180
- nv_gw: NVU_CALLER_KEY_MAP=hermes:2;openclaw:3;opencode:4
- nv_gw: NVU_BUFFER_CALLERS=cc4101-primary,openclaw2, NVU_PEER_FB_SKIP_MODELS=glm5_2_nv,dsv4p_nv
- nv_gw: MIN_OUTBOUND_INTERVAL_S=10, NVU_FORCE_STREAM_UPGRADE_TIMEOUT=150, KEY_COOLDOWN_S=30, NV_INTEGRATE_KEY_COOLDOWN_S=90
- cc4101: PRIMARY=glm5_2_nv→nv_gw:40006, FALLBACK=ms_gw:40007(env), STREAM_TOTAL=470, HEADER=400, PRIMARY_FAIL_THRESHOLD=3, PRIMARY_SKIP_S=30
- 链路: cc2→cc4101(4101)→nv_gw(40006, glm5_2_nv)→NVCF | 注: cc4101 env FALLBACK_UPSTREAM_URL=ms_gw:40007 与 CLAUDE.md 中描述的 dsv4p 链路不一致, 但本轮 0 fb 触发不动它
