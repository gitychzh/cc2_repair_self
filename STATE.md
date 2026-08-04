# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: R736 (NOP 巡检, 2026-08-05 04:50 CST)
> 上轮: R735 (NOP, cc2 30min SR 100%/fb 0%, 529 余波对 cc2 已平息)

## 本轮 (R736) 改了什么 + 依据 + 验证

### 改动: 不改码 (NOP)

### 依据 (实测 ~04:50 CST, 30min 窗)
- **cc2 (cc4101-primary) nv_gw SR = 47/47 = 100%**, fb = 0/47 = 0% — 达标
- 分钟趋势: 22 个分钟桶 (20:17-20:47 UTC) 全 200, 零抖动
- avg_dur 38s 正常, 无长尾
- hermes caller 8×502 all_tiers_exhausted 全走 dsv4f0731_nv (NVCF 上游容量, 非 cc2 链路, 非 nv_gw 可解)
- per-key tier (glm5_2_nv, cc2 请求): k0=11/k1=8/k2=8/k3=10/k4=10 **全 pexec_success**, 零 529/零 RemoteDisconnected/零 Timeout

### 验证 (NOP 无需 restart)
- `/health`: nv_gw ok (5 keys, glm5_2_nv default) + cc4101 ok (primary=glm5_2_nv) — 全 ok
- `docker ps`: nv_gw Up 2h, cc4101 Up 3h, dsv4p_nv40066 Up 8h, nv_gw_stable Up 3days, logs_db Up 5days — 全 Up
- env 沿 R735, 无漂移

### 注入快照 vs 实测一致性
- 注入 cc4101-primary 30min: 42×200+1×502 → 实测 47×200+0×502 (窗口更晚, 502 已消失, SR 升至 100%)
- 注入 8×all_tiers_exhausted 对应 hermes→dsv4f0731_nv, 与实测一致
- 注入 per-key 529 分布是全 tier 30min 聚合 (含 dsv4f0731_nv 529 storm), glm5_2_nv tier 本身零 529

## 判稳结论
- **cc2 nv_gw 链路 (glm5_2_nv) 连续 2 轮 (R735/R736) SR 100%, fb 0%, per-key 全 pexec_success** — 全面达标
- 529 余波对 cc2 路径已平息 (R735 最近 22min 100% → R736 最近 30min 100%, 窗口扩大仍 100%)
- hermes 8×502 是 dsv4f0731_nv NVCF 容量问题, 不是 cc2 nv_gw 链路, 非 nv_gw 配置可改
- NOP 巡检轮 — 链路已稳, 无可改项

## 下一步
- 持续监控 cc2 SR + fb 触发率 (目标 SR 99%+ / fb <10%)
- 若 dsv4f0731_nv 的 529 storm 再起影响 hermes, 非本 agent 职责 (cc2 只走 glm5_2_nv)
- 流量低时不动码, 仅 NOP 记数据
- cc_requests.ts 时区 bug 沿用: 分析用 created_at (R730/R732/R735/R736 已实证)

## 参数快照 (实测 env, 沿 R735, 无变化)
- nv_gw: NVU_DISABLE_MS_FALLBACK=1, **单 mode MODE_CHAIN=pexec_us_rr**, KEY_MODE_BIND=空,
  KEY_FID_BIND=0:0;1:0;2:0;3:0;4:0 (全 5 key 绑 fid1=b1b22d03),
  KEY_PROXY_BIND=0:7901;1:7894;2:7897;3:7896;4:7899, RR_US_PROXIES=7901,7894,7897,7896,7899
  - buffer 5×90s=450s (NVU_BUFFER_MAX_RETRIES=5, NVU_BUFFER_TIMEOUT_STAIRS=90,90,90,90,90, NVU_BUFFER_TOTAL_DEADLINE_S=450)
  - UPSTREAM_TIMEOUT=90, TIER_COOLDOWN_S=180, NVU_KEYMGR_429_BASE=120/MAX=600, CONN_BASE=30/LONG=120/MAX=60
- cc4101: PRIMARY=glm5_2_nv→nv_gw:40006, **FALLBACK=glm5_2_ms→ms_gw:40007** (注意: 不是 dsv4p_nv40066),
  STREAM_TOTAL=470, HEADER=400, UPSTREAM_IDLE=150, UPSTREAM_TIMEOUT=130,
  PRIMARY_FAIL_THRESHOLD=3, PRIMARY_SKIP_S=30
- deadline 链: 90s×5=450s buffer < 470s cc4101 < 600s API < 900s idle

## STATE 过时项修正记录 (R735 起, 沿用)
- ❌ 旧 (CLAUDE.md 顶): "per-key 混合链路 k1/3/5 pexec, k2/4 integrate" → ✅ 新: 单 mode pexec_us_rr, 全 key 绑 fid1 (R-glm52-fb-fix 已回退 integrate)
- ❌ 旧 (CLAUDE.md 顶): "cc4101 FALLBACK=dsv4p_nv40066:40066" → ✅ 新: FALLBACK=ms_gw:40007 (model=glm5_2_ms), dsv4p_nv40066 仍 Up 但非当前 fallback 目标
