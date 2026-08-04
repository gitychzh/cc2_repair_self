# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: R762 (NOP 巡检, 2026-08-05 ~06:36 CST)
> 上轮: R761 (NOP, cc2 30min SR 100%/fb 0%, 第 27 连续 100%)

## 本轮 (R762) 改了什么 + 依据 + 验证

### 改动: 不改码 (NOP)

### 依据 (created_at 实测校验, ~06:36 CST)
- **cc2 (cc4101-primary) glm5_2_nv: nv_requests 99×200 (SR=100%), cc_requests 99 total / 99 ok / fb=0** — 连续第 28 轮 100%
- glm5_2_nv tier: 104 pexec_success + 1 pexec_429 (buffer 吸收, 零穿透 cc2) — 连续第 16 轮最干净
- **5 key 全 0 错误** (per-key k0=20/k1=23/k2=18/k3=25/k4=19 全 pexec_success)
- 注入口径 "f|149" / 14 RemoteDisc / 3 empty_200 / 1×529 实测全 0 — ts 列时区 bug + 注入器拼入历史/其他 tier 噪声 (沿 R730/R742~R761 实证)
- 本轮再次实证: cc2 决策必须以 created_at 实测为准, 注入数据仅作背景参考

### 验证 (NOP 无需 restart)
- `/health`: nv_gw ok (nv_num_keys=5, pexec_models 含 glm5_2_nv), cc4101 ok (primary=glm5_2_nv) — 全 ok
- `docker ps`: nv_gw Up 4h, cc4101 Up 5h, dsv4p_nv40066 Up 10h, dsvf0731_nv40666 Up 1h — 全 Up

## 判稳结论
- **cc2 nv_gw 链路连续 28 轮 (R735~R762) SR 100%, fb 0%** — 全面达标 (目标 SR 99%+/fb <10%)
- 本轮 glm5_2_nv tier 1×pexec_429 (buffer 吸收) — 数量极小 (<1%), 不影响 cc2 可见 SR
- 流量 99 req/30min (上轮 R761 实测 90→本轮 99, 小幅上升), 链路稳
- NOP 巡检轮 — 链路已稳, 无可改项

### SR 趋势
| 轮 | 30min 窗 SR | 备注 |
|---|---|---|
| R735 | 100% (最近 22min) | 30min 91.6% 被 529 余波拖低 |
| R742 | 100% (81 nv / 83 cc) | 8th consecutive, fb=0 (created_at) |
| R748 | 100% (75 nv / 75 cc) | 14th consecutive, fb=0, 最干净一轮 |
| R755 | 100% (89 nv / 88 cc) | 21th consecutive, fb=0 |
| R758 | 100% (84 nv / 84 cc) | 24th consecutive, fb=0 |
| R760 | 100% (85 nv / 87 cc) | 26th consecutive, fb=0, 14th cleanest (tier 零错误) |
| R761 | 100% (90 nv / 90 cc) | 27th consecutive, fb=0, 15th cleanest (95 pexec_success + 1 pexec_429) |
| R762 | 100% (99 nv / 99 cc) | **28th consecutive, fb=0, 16th cleanest (104 pexec_success + 1 pexec_429, 5key 全 0 错误)** |

## 下一步
- 持续监控 cc2 SR + fb 触发率 (目标 SR 99%+/fb <10%)
- glm5_2_nv tier 间歇 pexec_429 (R761/R762 各 1 次) — 数量极小 (<1%), 若累积或穿透 cc2 再查 KeyManager 退避状态
- 注入数据噪声 (RemoteDisc / empty_200 / 529 / f\|149) 持续出现但 created_at 实测全 0 — 沿 ts 列时区 bug 解释
- 流量低时不动码, 仅 NOP 记数据
- cc_requests.ts 时区 bug 沿用: 分析用 created_at (R730 起实证)

## 参数快照 (实测 env, 沿 R761, 无变化)
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
- ❌ 旧 (CLAUDE.md 顶): "per-key 混合链路 k1/3/5 pexec, k2/4 integrate" → ✅ 新: 单 mode pexec_us_rr, 全 key 绑 fid1=b1b22d03
- 注: cc2 round 文件 (rounds/) 与 HM2 其他工作流共用目录, R761 起加 `cc2_` 前缀区分
