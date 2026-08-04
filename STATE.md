# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: R777 (NOP 巡检, 2026-08-05 ~07:40 CST)
> 上轮: R776 (NOP, 42nd consecutive 100%, cleanest=27)

## 本轮 (R777) 改了什么 + 依据 + 验证

### 改动: 不改码 (NOP)

### 依据 (created_at 实测校验, ~07:38 CST)
- **cc2 (cc4101-primary) glm5_2_nv: nv_requests 80×200 (SR=100%), 0 错误**
- **cc_requests created_at 校验: 80 total / 80 ok / 0 fb (fb=0%, 目标<10%)** ✅
- **tier 噪声 17 (NVCFPexecRemoteDisconnected×16 + empty_200×1) — 全被 buffer/KeyManager 消化, cc4101-primary 零穿透**
- buffer 日志: 全部 attempt=1/5 即 success, 无 retry/backoff 触发, verdict=success_text/success_tool_call
- 注入噪声 (dsv4f0731_nv 502×7 + all_tiers_exhausted×7) 全在 dsv4 hermes caller — 非本链路问题

### 验证 (NOP 无需 restart)
- `/health`: nv_gw ok (nv_num_keys=5, pexec_models 含 glm5_2_nv), cc4101 ok (primary=glm5_2_nv), dsv4p_nv40066 ok — 全 ok
- `docker ps`: nv_gw Up 5h, cc4101 Up 6h, dsv4p_nv40066 Up 11h, nv_gw_stable Up 3d, logs_db Up 5d — 全 Up

## 判稳结论
- **cc2 nv_gw 链路连续 43 轮 (R735~R777) SR 100%, fb 0%** — 全面达标 (目标 SR 99%+/fb <10%)
- **本轮 tier 噪声 17** (NVCFPexecRemoteDisconnected×16 + empty_200×1) — buffer 容错有效, 全 attempt=1 即 success, cc4101-primary 零错误
- 流量 80 req/30min (上轮 82→80, 稳定区间)
- NOP 巡检轮 — 链路已稳, 无可改项
- cleanest 计数停在 27 (R774)

### SR 趋势
| 轮 | 30min 窗 SR | tier 噪声 | 备注 |
|---|---|---|---|
| R774 | 100% (95/95) | 0 | 40th, 27th cleanest |
| R775 | 100% (83/83) | 20 | 41st, cleanest 停 27 |
| R776 | 100% (82/82) | 19 | 42nd consecutive 100% |
| R777 | 100% (80/80) | 17 | **43rd consecutive 100%, cleanest 停 27** |

## 下一步
- 持续监控 cc2 SR + fb 触发率 (目标 SR 99%+/fb <10%)
- tier 噪声仍在 buffer 消化范围内 — 不影响 cc2 可见 SR
- 注入噪声 (dsv4f0731_nv 502×7 + all_tiers_exhausted×7) 全在 dsv4 hermes caller, 非本链路问题

## 参数快照 (R777, 实测一致无变化)
- nv_gw: NVU_DISABLE_MS_FALLBACK=1, UPSTREAM_TIMEOUT=90, TIER_TIMEOUT_BUDGET_S=180, TIER_COOLDOWN_S=180
- nv_gw: NVU_CALLER_KEY_MAP=hermes:2;openclaw:3;opencode:4
- nv_gw: NVU_BUFFER_CALLERS=cc4101-primary,openclaw2, NVU_PEER_FB_SKIP_MODELS=glm5_2_nv,dsv4p_nv
- cc4101: PRIMARY=glm5_2_nv→nv_gw:40006, FALLBACK=dsv4p_nv40066, STREAM_TOTAL=470, HEADER=400
- 链路: cc2→cc4101(4101)→nv_gw(40006, glm5_2_nv)→NVCF | fallback→dsv4p_nv40066(40066)
