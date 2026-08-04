# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: R778 (NOP 巡检, 2026-08-05 ~07:55 CST)
> 上轮: R777 (NOP, 43rd consecutive 100%, cleanest=27)

## 本轮 (R778) 改了什么 + 依据 + 验证

### 改动: 不改码 (NOP)

### 依据 (轮前链路分析 ~07:51 CST, 30min 窗口)
- **cc2 (cc4101-primary) glm5_2_nv: nv_requests 57×200 (SR=100%), 0 错误, 0 fallback**
- **cc4101-primary caller: 57 total / 57 ok / fb=0 (fb=0%, 目标<10%)** ✅
- **tier 噪声 16 (NVCFPexecRemoteDisconnected×15 + empty_200×1) — 全被 buffer/KeyManager 消化, cc4101-primary 零穿透**
- per-key pexec_success: k0:12+k1:9+k2:11+k3:13+k4:12 = 57 (与 57 req 一致, 全 attempt=1)
- 无 buffer/wait 日志 (全 attempt=1 即 success, 未触发 retry/backoff)
- 注入噪声 (dsv4f0731_nv 502×8 + all_tiers_exhausted×8) 全在 dsv4 hermes caller — 非本链路问题

### 验证 (NOP 无需 restart)
- 容器: nv_gw Up 10h, cc4101 Up 6h — 运行中
- cc4101-primary caller 全 200, fb=0/57 — 链路健康

## 判稳结论
- **cc2 nv_gw 链路连续 44 轮 (R735~R778) SR 100%, fb 0%** — 全面达标 (目标 SR 99%+/fb <10%)
- **本轮 tier 噪声 16** (NVCFPexecRemoteDisconnected×15 + empty_200×1) — buffer 容错有效, 全 attempt=1 即 success, cc4101-primary 零错误
- 流量 57 req/30min (上轮 80→57, 流量偏低但稳定)
- NOP 巡检轮 — 链路已稳, 无可改项
- cleanest 计数停在 27 (R774)

### SR 趋势
| 轮 | 30min 窗 SR | tier 噪声 | 备注 |
|---|---|---|---|
| R774 | 100% (95/95) | 0 | 40th, 27th cleanest |
| R775 | 100% (83/83) | 20 | 41st, cleanest 停 27 |
| R776 | 100% (82/82) | 19 | 42nd consecutive 100% |
| R777 | 100% (80/80) | 17 | 43rd consecutive 100% |
| R778 | 100% (57/57) | 16 | **44th consecutive 100%, cleanest 停 27** |

## 下一步
- 持续监控 cc2 SR + fb 触发率 (目标 SR 99%+/fb <10%)
- tier 噪声仍在 buffer 消化范围内 (15 RemoteDisc, 全 attempt=1 success) — 不影响 cc2 可见 SR
- 注入噪声 (dsv4f0731_nv 502×8 + all_tiers_exhausted×8) 全在 dsv4 hermes caller, 非本链路问题

## 参数快照 (R778, 实测一致无变化)
- nv_gw: NVU_DISABLE_MS_FALLBACK=1, UPSTREAM_TIMEOUT=90, TIER_TIMEOUT_BUDGET_S=180, TIER_COOLDOWN_S=180
- nv_gw: NVU_CALLER_KEY_MAP=hermes:2;openclaw:3;opencode:4
- nv_gw: NVU_BUFFER_CALLERS=cc4101-primary,openclaw2, NVU_PEER_FB_SKIP_MODELS=glm5_2_nv,dsv4p_nv
- cc4101: PRIMARY=glm5_2_nv→nv_gw:40006, FALLBACK=dsv4p_nv40066, STREAM_TOTAL=470, HEADER=400
- 链路: cc2→cc4101(4101)→nv_gw(40006, glm5_2_nv)→NVCF | fallback→dsv4p_nv40066(40066)
