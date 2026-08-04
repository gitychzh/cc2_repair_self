# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: R742 (NOP 巡检, 2026-08-05 05:06 CST)
> 上轮: R741 (NOP, cc2 30min SR 100%/fb 0%, 第 7 连续 100%)

## 本轮 (R742) 改了什么 + 依据 + 验证

### 改动: 不改码 (NOP)

### 依据 (实测 ~05:06 CST, 30min 窗, 注入数据 + created_at 实测核验)
- **cc2 (cc4101-primary) glm5_2_nv: nv_requests 81×200 (SR=100%) + cc_requests 83×200 (SR=100%, fb=0)** — 连续第 8 轮 100%
- per-key tier 分布: k0-k4 各 15-17 pexec_success = 合计 81, 与 cc2 81×200 完全一致
- 529_nv_overloaded 散布全 key (各 6-8) + NVCFPexecRemoteDisconnected (各 1-2) → 被 buffer 兜住
- k3 empty_200×1, k4 529_integrate_overloaded×2 — 微噪声, cc2 不可见
- hermes→dsv4f0731_nv: 14×200 + 7×502 (66.7%) — NVCF 容量, 非 cc2 链路
- ⚠️ 注入数据 "f|102" 是 ts 列时区 bug 口径的截断行, 非真实 fb 计数; created_at 实测: 83 req / 0 fb
- ⚠️ cc_requests.ts 时区 bug 沿用 (R730 实证): ts 列拉到 516total/34fb 是旧数据混入, 用 created_at 才是真实当前 30min

### 验证 (NOP 无需 restart)
- `/health`: nv_gw ok (5 keys, glm5_2_nv default) + cc4101 ok (primary=glm5_2_nv) — 全 ok
- `docker ps`: nv_gw Up 2h, cc4101 Up 3h, dsv4p_nv40066 Up 8h, dsvf0731_nv40666 Up ~1h — 全 Up
- env 沿 R741, 无漂移

## 判稳结论
- **cc2 nv_gw 链路连续 8 轮 (R735~R742) SR 100%, fb 0%** — 全面达标
- 529 storm + empty_200/integrate_overloaded 微噪声持续, 但被 buffer 兜住, cc2 不可见
- hermes 7×502 是 dsv4f0731_nv NVCF 容量, 不是 cc2 nv_gw 链路
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
| R742 | 100% (81 nv_req / 83 cc_req) | 8th consecutive, fb=0 (created_at 实测), 注入 "f\|102" 是 ts 时区 bug |

## 下一步
- 持续监控 cc2 SR + fb 触发率 (目标 SR 99%+ / fb <10%)
- 529 noise + empty_200 持续观察, 若泄漏到 cc2 (buffer 失效) 再查
- 流量低时不动码, 仅 NOP 记数据
- cc_requests.ts 时区 bug 沿用: 分析用 created_at (R730 起 已实证)

## 参数快照 (实测 env, 沿 R741, 无变化)
- nv_gw: NVU_DISABLE_MS_FALLBACK=1, 单 mode MODE_CHAIN=pexec_us_rr, KEY_MODE_BIND=空,
  KEY_FID_BIND=全 5 key 绑 fid1=b1b22d03,
  KEY_PROXY_BIND=0:7901;1:7894;2:7897;3:7896;4:7899, RR_US_PROXIES=7901,7894,7897,7896,7899
  - buffer 5×90s=450s (NVU_BUFFER_MAX_RETRIES=5, NVU_BUCKET_CALLERS=cc4101-primary,openclaw2)
  - UPSTREAM_TIMEOUT=90, TIER_COOLDOWN_S=180, KEY_COOLDOWN_S=30, NVU_KEYMGR_429_BASE=120/MAX=600
- cc4101: PRIMARY=glm5_2_nv→nv_gw:40006, FALLBACK=glm5_2_ms→ms_gw:40007,
  STREAM_TOTAL=470, HEADER=400, UPSTREAM_IDLE=150, UPSTREAM_TIMEOUT=130,
  PRIMARY_FAIL_THRESHOLD=3, PRIMARY_SKIP_S=30
- deadline 链: 90s×5=450s buffer < 470s cc4101 < 600s API < 900s idle

## STATE 过时项修正记录 (R735 起, 沿用)
- ❌ 旧 (CLAUDE.md 顶): "per-key 混合链路 k1/3/5 pexec, k2/4 integrate" → ✅ 新: 单 mode pexec_us_rr, 全 key 绑 fid1
- ❌ 旧 (CLAUDE.md 顶): "cc4101 FALLBACK=dsv4p_nv40066:40066" → ✅ 新: FALLBACK=ms_gw:40007 (model=glm5_2_ms), dsv4p_nv40066 仍 Up 但非当前 fallback
- ⚠️ R738 起观察: tier attempts 出现 52e1ddb6 fid (非 fid1 b1b22d03), 与 KEY_FID_BIND "全 fid1" 不符 — 多 caller 共用 key 副作用, 对 cc2 不可见 (buffer 兜住)
- ℹ️ R741 起: 新容器 dsvf0731_nv40666 出现 — 不在 cc2 链路 (cc4101 primary/fallback 均未指向), 无影响
- ⚠️ R742 实证: 注入链路分析的 "fallback 发生率" 段用 ts 列时区 bug 口径, 拉到旧数据混入; cc_requests 真实 fb 计数必须用 created_at 列 (R730 起实证)
