# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: R776 (NOP 巡检, 2026-08-05 ~07:40 CST)
> 上轮: R775 (NOP, 41st consecutive 100%, cleanest=27)

## 本轮 (R776) 改了什么 + 依据 + 验证

### 改动: 不改码 (NOP)

### 依据 (created_at 实测校验, ~07:34 CST)
- **cc2 (cc4101-primary) glm5_2_nv: nv_requests 82×200 (SR=100%), 0 错误**
- **cc_requests: 82 total / 82 ok / 0 fallback (fb=0%, 目标<10%)** — created_at 校验
- **tier 噪声 19 (NVCFPexecRemoteDisconnected×17 + empty_200×2) — 全被 buffer/KeyManager 消化, cc4101-primary 零穿透**
- 注入噪声 (dsv4f0731_nv 502×8 + all_tiers_exhausted×8) 全在 dsv4 hermes caller — 非本链路问题

### 验证 (NOP 无需 restart)
- `/health`: nv_gw ok (nv_num_keys=5), cc4101 ok (primary=glm5_2_nv), dsv4p_nv40066 ok — 全 ok
- `docker ps`: nv_gw Up 5h, cc4101 Up 6h, dsv4p_nv40066 Up 11h, logs_db Up 5d — 全 Up

## 判稳结论
- **cc2 nv_gw 链路连续 42 轮 (R735~R776) SR 100%, fb 0%** — 全面达标 (目标 SR 99%+/fb <10%)
- **本轮 tier 噪声 19** (NVCFPexecRemoteDisconnected×17 + empty_200×2) — buffer 容错有效, cc4101-primary 零错误
- 流量 82 req/30min (上轮 83→82, 稳定区间)
- NOP 巡检轮 — 链路已稳, 无可改项
- cleanest 计数停在 27 (R774)

### SR 趋势
| 轮 | 30min 窗 SR | tier 噪声 | 备注 |
|---|---|---|---|
| R773 | 100% (104/104) | 24 | 39th, cleanest 停在 26 |
| R774 | 100% (95/95) | 0 | 40th, 27th cleanest |
| R775 | 100% (83/83) | 20 | 41st, cleanest 停在 27 |
| R776 | 100% (82/82) | 19 | **42nd consecutive 100%, cleanest 停在 27** |

## 下一步
- 持续监控 cc2 SR + fb 触发率 (目标 SR 99%+/fb <10%)
- tier 噪声仍在 buffer 消化范围内 — 不影响 cc2 可见 SR
- 注入噪声 (dsv4f0731_nv 502×8 + all_tiers_exhausted×8) 全在 dsv4 hermes caller, 非本链路问题

## 参数快照 (R776, 实测)
- nv_gw: NVU_DISABLE_MS_FALLBACK=1, UPSTREAM_TIMEOUT=90, TIER_TIMEOUT_BUDGET_S=180, TIER_COOLDOWN_S=180
- nv_gw: NVU_CALLER_KEY_MAP=hermes:2;openclaw:3;opencode:4
- nv_gw: NVU_BUFFER_CALLERS=cc4101-primary,openclaw2, NVU_PEER_FB_SKIP_MODELS=glm5_2_nv,dsv4p_nv
- cc4101: PRIMARY=glm5_2_nv→nv_gw:40006, FALLBACK=dsv4p_nv40066, STREAM_TOTAL=470, HEADER=400
- 链路: cc2→cc4101(4101)→nv_gw(40006, glm5_2_nv)→NVCF | fallback→dsv4p_nv40066(40066)
