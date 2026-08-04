# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: R747 (NOP 巡检, 2026-08-05 05:30 CST)
> 上轮: R746 (NOP, cc2 30min SR 100%/fb 0%, 第 12 连续 100%)

## 本轮 (R747) 改了什么 + 依据 + 验证

### 改动: 不改码 (NOP)

### 依据 (实测 ~05:30 CST, 30min 窗, created_at 实测核验)
- **cc2 (cc4101-primary) glm5_2_nv: nv_requests 77×200 (SR=100%) + cc_requests 77×200 (fb=0, SR=100%)** — 连续第 13 轮 100%
- 注入的 "f|89" 在 fallback 发生率段 → created_at 实测: 77 req / 0 fb (ts 列时区 bug 口径, 沿 R730/R742-R746 实证)
- per-key pexec_success 实测: k0=16, k1=15, k2=16, k3=15, k4=15 = 总 77, 与 cc2 77×200 完全一致 — 本轮零噪声穿透 cc2
- 注入的 NVCFPexecRemoteDisconnected=14 / 529_nv_overloaded=3 / empty_200=1 / all_tiers_exhausted=5 / NVStream_IncompleteRead=3 全部来自 hermes→dsv4f0731_nv 上游 NVCF 容量, 不在 cc2 路径

### 验证 (NOP 无需 restart)
- `/health`: nv_gw ok (5 keys, glm5_2_nv default) + cc4101 ok (primary=glm5_2_nv) — 全 ok
- `docker ps`: nv_gw Up 3h, cc4101 Up 4h, dsv4p_nv40066 Up 9h, dsvf0731_nv40666 Up 1h, nv_gw_stable Up 3d — 全 Up
- env 沿 R746, 无漂移

## 判稳结论
- **cc2 nv_gw 链路连续 13 轮 (R735~R747) SR 100%, fb 0%** — 全面达标 (目标 SR 99%+ / fb <10%)
- 本轮 per-key pexec_success 完全匹配 77×200, 无任何错误穿透 cc2 — 最干净一轮
- hermes→dsv4f0731_nv 502 + IncompleteRead 是 NVCF 容量, 不影响 cc2 链路
- NOP 巡检轮 — 链路已稳, 无可改项

### SR 趋势
| 轮 | 30min 窗 SR | 备注 |
|---|---|---|
| R735 | 100% (最近 22min) | 30min 91.6% 被 529 余波拖低 |
| R736 | 100% (47/47) | 余波平息 |
| R737 | 100% (51/51) | 持续稳定 |
| R738 | 100% (60/60) | 52e1ddb6 fid 529 被 buffer 兜住 |
| R739 | 100% (68/68) | empty_200/integrate_overloaded 微噪声不可见 |
| R740 | 100% (73/73) | 流量略增 |
| R741 | 100% (77/77) | pexec_success=77 与 cc2 200 一致 |
| R742 | 100% (81 nv / 83 cc) | 8th consecutive, fb=0 (created_at 实测), 注入 "f\|102" 是 ts 时区 bug |
| R743 | 100% (80 nv / 80 cc) | 9th consecutive, fb=0 (created_at 实测), 注入 "f\|95" 是 ts 时区 bug |
| R744 | 100% (82 nv / 82 cc) | 10th consecutive, fb=0 (created_at 实测), 注入 "f\|94" 是 ts 时区 bug |
| R745 | 100% (82 nv / 82 cc) | 11th consecutive, fb=0 (created_at 实测), 注入 "f\|96" 是 ts 时区 bug |
| R746 | 100% (80 nv / 80 cc) | 12th consecutive, fb=0 (created_at 实测), 注入 "f\|90" 是 ts 时区 bug |
| R747 | 100% (77 nv / 77 cc) | 13th consecutive, fb=0 (created_at 实测), 注入 "f\|89" 是 ts 时区 bug |

## 下一步
- 持续监控 cc2 SR + fb 触发率 (目标 SR 99%+ / fb <10%)
- 注入噪声 (529/empty_200/NVCFPexecRemoteDisconnected) 持续观察, 若泄漏到 cc2 (buffer 失效) 再查
- 流量低时不动码, 仅 NOP 记数据
- cc_requests.ts 时区 bug 沿用: 分析用 created_at (R730 起实证)

## 参数快照 (实测 env, 沿 R746, 无变化)
- nv_gw: NVU_DISABLE_MS_FALLBACK=1, 单 mode MODE_CHAIN=pexec_us_rr, KEY_MODE_BIND=空,
  KEY_FID_BIND=全 5 key 绑 fid1=b1b22d03,
  KEY_PROXY_BIND=0:7901;1:7894;2:7897;3:7896;4:7899, RR_US_PROXIES=7901,7894,7897,7896,7899
  - buffer 5×90s=450s (NVU_BUFFER_MAX_RETRIES=5, NVU_BUFFER_CALLERS=cc4101-primary,openclaw2)
  - UPSTREAM_TIMEOUT=90, TIER_COOLDOWN_S=180, KEY_COOLDOWN_S=30, NVU_KEYMGR_429_BASE=120/MAX=600
- cc4101: PRIMARY=glm5_2_nv→nv_gw:40006, FALLBACK=glm5_2_ms→ms_gw:40007,
  STREAM_TOTAL=470, HEADER=400, UPSTREAM_IDLE=150, UPSTREAM_TIMEOUT=130,
  PRIMARY_FAIL_THRESHOLD=3, PRIMARY_SKIP_S=30
- deadline 链: 90s×5=450s buffer < 470s cc4101 < 600s API < 900s idle

## STATE 过时项修正记录 (R735 起, 沿用)
- ❌ 旧 (CLAUDE.md 顶): "per-key 混合链路 k1/3/5 pexec, k2/4 integrate" → ✅ 新: 单 mode pexec_us_rr, 全 key 绑 fid1
