# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: R792 (NOP 巡检, 2026-08-05 ~09:00 CST)
> 上轮: R791 (NOP, 55th consecutive 100%)

## 本轮 (R792) 改了什么 + 依据 + 验证

### 改动: 不改码 (NOP)

### 依据 (轮前链路分析 08:43 CST, 30min 窗口)
- **cc2 (cc4101-primary|glm5_2_nv): 101 req × 200 (SR=100%), 0 fb, 0 穿透** ✅
- 连续 56 轮 (R735~R792) SR 100%, fb 0%
- tier 噪声 **14** (R791:12→14 微升):
  - NVCFPexecRemoteDisconnected×12: k3:4+k1:3+k2:2+k4:2+k0:1 (均布非单key)
  - empty_200×3 (k0:1+k2:2), 529_nv_overloaded×1 (k0:1)
- 顶层 all_tiers_exhausted×2 全在 dsv4 hermes caller (dsv4f0731_nv 注入 502 噪声), 零穿透到 cc2
- buffer/wait/keymanager 日志: 无 (全 attempt=1 success, 无 retry/WAIT/KEYMGR/BREAKER)

### 验证 (NOP 无 restart)
- 容器: nv_gw Up 11h, cc4101 Up 7h, dsv4p_nv40066 Up 12h, logs_db Up 5d
- /health 全 ok (上轮已确认, 本轮 NOP 沿用)

## 判稳结论
- **cc2 nv_gw 链路连续 56 轮 (R735~R792) SR 100%, fb 0%** — 达标 (目标 SR 99%+/fb <10%)
- tier 噪声 14 零穿透, RemoteDisc 12 均布 k0-k4 非单 key 故障, buffer 全吸收
- k3 RemoteDisc 4 (R789:5+R790:0+R791:5+R792:4) — NVCF-sided 周期性 jitter, 非链路缺陷
- 判定: 链路健康无可改项, NOP 巡检轮
- cleanest 计数仍停 27 (R774)

### SR 趋势
| 轮 | 30min SR | tier 噪声 | 备注 |
|---|---|---|---|
| R789 | 100% (111) | 16 | k3/k4 RemoteDisc 9 偏高 |
| R790 | 100% (111) | 1 | k3/k4 RemoteDisc 0 自愈 |
| R791 | 100% (113) | 12 | k3 RemoteDisc 5 偏高续 |
| R792 | 100% (101) | 14 | RemoteDisc 12 均布 k0-k4 |

## 下一步
- 持续监控 cc2 SR + fb (目标 SR 99%+/fb <10%)
- k3 RemoteDisc 偏高模式 (R789:5+R790:0+R791:5+R792:4) 若连续多轮且偶发穿透 cc2 → 排查 k3 fid2(3b9748d8)
- dsv4p_nv fallback 链路健康, 应急 OK

## 参数快照 (R792, 实测无变化)
- nv_gw: NVU_DISABLE_MS_FALLBACK=1, UPSTREAM_TIMEOUT=90, TIER_TIMEOUT_BUDGET_S=180, TIER_COOLDOWN_S=180
- nv_gw: NVU_CALLER_KEY_MAP=hermes:2;openclaw:3;opencode:4
- nv_gw: NVU_BUFFER_CALLERS=cc4101-primary,openclaw2, NVU_PEER_FB_SKIP_MODELS=glm5_2_nv,dsv4p_nv
- nv_gw: MIN_OUTBOUND_INTERVAL_S=10, NVU_FORCE_STREAM_UPGRADE_TIMEOUT=150, KEY_COOLDOWN_S=30, NV_INTEGRATE_KEY_COOLDOWN_S=90
- cc4101: PRIMARY=glm5_2_nv→nv_gw:40006, FALLBACK=ms_gw:40007(env), STREAM_TOTAL=470, HEADER=400
- 链路: cc2→cc4101(4101)→nv_gw(40006, glm5_2_nv)→NVCF
