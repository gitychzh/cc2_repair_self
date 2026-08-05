# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: R791 (NOP 巡检, 2026-08-05 ~08:45 CST)
> 上轮: R790 (NOP, 54th consecutive 100%)

## 本轮 (R791) 改了什么 + 依据 + 验证

### 改动: 不改码 (NOP)

### 依据 (轮前链路分析 08:39 + DB 复核 ~08:45 CST, 30min 窗口)
- **cc2 (cc4101-primary|glm5_2_nv): 113 req × 200 (SR=100%), 0 fb, 0 穿透** ✅
- DB 复核 (nv_requests caller=cc4101-primary): 113 total / 113 ok / SR=100%
- cc_requests: 113/113 SR=100%, **0 fb**
- 连续 55 轮 (R735~R791) SR 100%, fb 0%
- tier 噪声 **12** (R790:1→12 回升, NVCF-sided 周期性 jitter):
  - NVCFPexecRemoteDisconnected×11: k3:5(偏高续 R789:5)+k1:3+k2:2+k4:2
  - empty_200×3 (k0:1+k2:2), 529_nv_overloaded×1 (k0:1)
- 顶层 all_tiers_exhausted×3 全在 dsv4 hermes caller (dsv4f0731_nv 注入 502 噪声), 零穿透到 cc2
- buffer 全 attempt=1 success, elapse 3-17s, 无 retry/WAIT/KEYMGR/BREAKER 触发

### 验证 (NOP 无 restart)
- 容器: nv_gw Up 6h, cc4101 Up 7h, dsv4p_nv40066 Up 12h, logs_db Up 5d
- /health 全 ok: nv_gw passthrough(5key 含 glm5_2_nv), cc4101 primary=glm5_2_nv, dsv4p_nv40066 passthrough

## 判稳结论
- **cc2 nv_gw 链路连续 55 轮 (R735~R791) SR 100%, fb 0%** — 达标 (目标 SR 99%+/fb <10%)
- tier 噪声 12 零穿透, k3 RemoteDisc 5 偏高但均布非单key + buffer 全吸收
- k3 RemoteDisc 模式 R789:5+R790:0+R791:5 — NVCF-sided 周期性 jitter, 非链路缺陷
- 判定: 链路健康无可改项, NOP 巡检轮
- cleanest 计数仍停 27 (R774)

### SR 趋势
| 轮 | 30min SR | tier 噪声 | 备注 |
|---|---|---|---|
| R788 | 100% (111) | 18 | RemoteDisc 13 均布 |
| R789 | 100% (111) | 16 | k3/k4 RemoteDisc 9 偏高 |
| R790 | 100% (111) | 1 | k3/k4 RemoteDisc 0 自愈 |
| R791 | 100% (113) | 12 | k3 RemoteDisc 5 偏高续 |

## 下一步
- 持续监控 cc2 SR + fb (目标 SR 99%+/fb <10%)
- k3 RemoteDisc 偏高模式 (R789:5+R790:0+R791:5) 若再起连续多轮且偶发穿透 cc2 → 排查 k3 fid2(3b9748d8)
- dsv4p_nv fallback 链路健康, 应急 OK

## 参数快照 (R791, 实测无变化)
- nv_gw: NVU_DISABLE_MS_FALLBACK=1, UPSTREAM_TIMEOUT=90, TIER_TIMEOUT_BUDGET_S=180, TIER_COOLDOWN_S=180
- nv_gw: NVU_CALLER_KEY_MAP=hermes:2;openclaw:3;opencode:4
- nv_gw: NVU_BUFFER_CALLERS=cc4101-primary,openclaw2, NVU_PEER_FB_SKIP_MODELS=glm5_2_nv,dsv4p_nv
- nv_gw: MIN_OUTBOUND_INTERVAL_S=10, NVU_FORCE_STREAM_UPGRADE_TIMEOUT=150, KEY_COOLDOWN_S=30, NV_INTEGRATE_KEY_COOLDOWN_S=90
- cc4101: PRIMARY=glm5_2_nv→nv_gw:40006, FALLBACK=ms_gw:40007(env), STREAM_TOTAL=470, HEADER=400
- 链路: cc2→cc4101(4101)→nv_gw(40006, glm5_2_nv)→NVCF
