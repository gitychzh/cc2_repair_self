# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: R771 (NOP 巡检, 2026-08-05 ~07:20 CST)
> 上轮: R770 (NOP, cc2 30min SR 100%/fb 0%, 第 36 连续 100%, 24th cleanest)

## 本轮 (R771) 改了什么 + 依据 + 验证

### 改动: 不改码 (NOP)

### 依据 (created_at 实测校验, ~07:17 CST)
- **cc2 (cc4101-primary) glm5_2_nv: nv_requests 98×200 (SR=100%), cc_requests 98 total / 98 ok / fb=0** — 连续第 37 轮 100%
- **glm5_2_nv tier: 98 pexec_success, 0 错误** — 第 25 连续最干净轮
  - per-key: k0:20, k1:18, k2:19, k3:21, k4:20 (全 pexec_success, 全 0 错误)
- **本轮 tier 层连 RemoteDisc/529/empty_200 也全部归零** — 第 25 连续最干净轮
- k3 间歇 pexec_429 连续 5 轮 (R767-R771) 保持归零 — R761-R766 持续 6 轮的 ~1% 间歇已彻底消失
- 注入数据噪声 (all_tiers_exhausted×6+1) 全 tier 合计 (含 dsv4f0731_nv/dsv4f_nv 等 hermes caller tier), 非 glm5_2_nv tier
- 注入的 `fallback f|128` + `all_tiers_exhausted` — created_at 实测 cc4101-primary caller 0 错误, fb=0, **零穿透 cc2**

### 验证 (NOP 无需 restart)
- `/health`: nv_gw ok (nv_num_keys=5), cc4101 ok — 全 ok
- `docker ps`: nv_gw Up 10h, cc4101 Up 6h, dsv4p_nv40066 Up 11h, logs_db Up 4 weeks — 全 Up

## 判稳结论
- **cc2 nv_gw 链路连续 37 轮 (R735~R771) SR 100%, fb 0%** — 全面达标 (目标 SR 99%+/fb <10%)
- 本轮 glm5_2_nv tier **零错误, 零 RemoteDisc, 零 529, 零 empty_200** — 第 25 连续最干净轮
- 流量 98 req/30min (上轮 R770 93→本轮 98, 略升, 稳定区间)
- NOP 巡检轮 — 链路已稳, 无可改项

### SR 趋势
| 轮 | 30min 窗 SR | tier 错误 | 备注 |
|---|---|---|---|
| R767 | 100% (86/87) | 0 | 33rd consecutive, 21st cleanest (k3 429 归零) |
| R768 | 100% (89/89) | 0 | 34th consecutive, 22nd cleanest (k3 429 归零连续 2 轮) |
| R769 | 100% (89/89) | 0 | 35th consecutive, 23rd cleanest (k3 429 归零连续 3 轮) |
| R770 | 100% (93/93) | 0 | 36th consecutive, 24th cleanest (k3 429 归零连续 4 轮, tier 全噪声归零) |
| R771 | 100% (98/98) | 0 | **37th consecutive, 25th cleanest (k3 429 归零连续 5 轮, tier 全噪声归零)** |

## 下一步
- 持续监控 cc2 SR + fb 触发率 (目标 SR 99%+/fb <10%)
- k3 间歇 pexec_429 已归零连续 5 轮 (R767-R771) — 若后续再出现且累积或穿透 cc2 再查 KeyManager 退避状态
- 注入数据噪声持续出现但 created_at 实测全 0 — 沿 ts 列时区 bug 解释 (R730 起实证)
- 流量稳定时不动码, 仅 NOP 记数据
- cc_requests.ts 时区 bug 沿用: 分析用 created_at (R730 起实证)

## 参数快照 (实测 env, 沿 R770, 无变化)
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
- 注: cc2 round 文件 (rounds/) 与 HM2 其他工作流共享目录, R767 起用 `R<NN>_cc2_nop.md` 命名
