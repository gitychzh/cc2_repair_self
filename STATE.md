# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: R789 (NOP 巡检, 2026-08-05 ~08:40 CST)
> 上轮: R788 (NOP, 52nd consecutive 100%)

## 本轮 (R789) 改了什么 + 依据 + 验证

### 改动: 不改码 (NOP)

### 依据 (轮前链路分析 + DB 复核 ~08:40 CST, 30min 窗口)
- **cc2 (cc4101-primary|glm5_2_nv): 111 req × 200 (SR=100%), 0 fallback, 0 穿透** ✅
- DB 复核: cc_requests 111 total / 111 ok / 0 fb / SR=100.0%
- tier 噪声 16 (R788:18→16 略降), 全吸收:
  - NVCFPexecRemoteDisconnected × 12 (k3:5+k4:4+k1:2+k2:1 — k3/k4 偏高续)
  - 529_nv_overloaded × 2 (k0/k2)
  - empty_200 × 1 (k2), pexec_429 × 1 (k0)
- 顶层 all_tiers_exhausted×4 全在 dsv4 hermes caller (dsv4f0731_nv SR=76.5%), 非 cc2

### 验证 (NOP 无 restart)
- 容器: nv_gw Up 6h, cc4101 Up 7h, dsv4p_nv40066 Up 12h, logs_db Up 5d
- /health 全 ok: nv_gw passthrough(5key 含 glm5_2_nv), cc4101 primary=glm5_2_nv

## 判稳结论
- **cc2 nv_gw 链路连续 53 轮 (R735~R789) SR 100%, fb 0%** — 达标 (目标 SR 99%+/fb <10%)
- tier 噪声 16 全被 buffer/KeyManager 吸收, 零穿透 cc2
- k3/k4 RemoteDisc 偏高 (占 9/12) 是连续多轮模式, 但 buffer 有效吸收 + 无单 key 持续故障
- 判定为 NVCF 侧间歇抖动, 非链路缺陷, 不达改码阈值
- NOP 巡检轮 — 链路已稳, 无可改项
- cleanest 计数仍停 27 (R774)

### SR 趋势
| 轮 | 30min SR | tier 噪声 | 备注 |
|---|---|---|---|
| R784 | 100% (116) | 19 | k4 RemoteDisc 5 续 |
| R787 | 100% (117) | 1 | k4 回落 0 |
| R788 | 100% (111) | 18 | RemoteDisc 13 均布 |
| R789 | 100% (111) | 16 | k3/k4 RemoteDisc 9 偏高 |

## 下一步
- 持续监控 cc2 SR + fb (目标 SR 99%+/fb <10%)
- k3/k4 RemoteDisc 若连续多轮 >15 且偶发穿透 cc2 → 排查 k3 fid2(3b9748d8)/k4 fid3(b6029a96) integrate 健康度
- dsv4p_nv fallback 链路健康 (18/18 SR=100%), 应急 OK

## 参数快照 (R789, 实测无变化)
- nv_gw: NVU_DISABLE_MS_FALLBACK=1, UPSTREAM_TIMEOUT=90, TIER_TIMEOUT_BUDGET_S=180, TIER_COOLDOWN_S=180
- nv_gw: NVU_CALLER_KEY_MAP=hermes:2;openclaw:3;opencode:4
- nv_gw: NVU_BUFFER_CALLERS=cc4101-primary,openclaw2, NVU_PEER_FB_SKIP_MODELS=glm5_2_nv,dsv4p_nv
- nv_gw: MIN_OUTBOUND_INTERVAL_S=10, NVU_FORCE_STREAM_UPGRADE_TIMEOUT=150, KEY_COOLDOWN_S=30, NV_INTEGRATE_KEY_COOLDOWN_S=90
- cc4101: PRIMARY=glm5_2_nv→nv_gw:40006, FALLBACK=ms_gw:40007(env), STREAM_TOTAL=470, HEADER=400
- 链路: cc2→cc4101(4101)→nv_gw(40006, glm5_2_nv)→NVCF
