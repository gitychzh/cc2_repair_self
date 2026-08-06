# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: R884 (巡检轮/NOP — 近 30min 窗口 cc4101-primary SR=69% (27×200+12×502), 但 **12×502 全
> ≤22:41:37 UTC (06:41:37 CST), 正是 R883 已记录的同一次 fid 级全局 429 突发的事件尾部**, 非新事件;
> **自末次错误后 32×200 + 0 错误 = 100% SR, 8 分钟干净**, 系统按设计自愈, 无新错误类, **不改码**,
> 2026-08-07 ~06:49 CST / DB UTC 22:49)
> 上轮: R883 (巡检轮 — cc2 路径遭瞬态 NVCF/fid 级 429 全 5 key 同时冷却撞击 (06:41 CST), 但 fail-fast
> +cooldown 180s auto-recover, 22:41:37 UTC 后 0 错误, 系统自愈、不改码)

## 本轮 (R884) 改动 + 依据 + 验证

### 改动: 无 (窗口内 502 为 R883 06:41 同源事件尾部, 事件后 100% 干净, 非代码缺陷, 不改码)

### 本轮数据 (~06:49 CST, 轮前链路分析注入 + 独立复核, DB UTC 22:49)

**近 30min cc4101-primary (cc2 路径) SR = 69% (27×200 / 12×502) — 窗口伪象, 含 R883 事件尾部。**
**自末次错误 (22:41:37 UTC) 后: 32×200 + 0 错误 = 100% SR (8 个干净分钟).**

| 指标 | 值 | 状态 |
|---|---|---|
| **近 30min cc4101-primary SR (窗口)** | **69% (27/39)** — 全 12×502 ≤22:41:37, 为 R883 事件尾部伪象 | ⚠️ 窗口伪象 |
| **自末次错误 SR (真实当前态)** | **100% (32/32)** — 8 分钟干净 | ✅ 已自愈 |
| **primary 目标 tier** | **dsv4f0731_nv** (成功请求全 fid=281478d0, /health 确认) | ✅ |
| **30min caller×tier×status** | cc4101-primary\|dsv4f0731_nv\|200\|27 (fid 281478d0); 同\|502\|8 (dur 80~235s); cc4101-primary\|\|502\|4 (dur 45~55s) | cc2 受撞击 |
| **502 时间窗 (cc2)** | 全 ≤22:41:37 UTC (all_tiers_exhausted dur 80~235s, buffer_exhausted 45~55s); **22:41:37 后 0 错误** | ✅ 与 R883 同源 |
| **错误分类** | all_tiers_exhausted×8, buffer_exhausted×4 | 已知类, 无新错误 |
| **current fid 分布** | 34×nvcf_pexec 全 @ 281478d0 (dsv4f0731_nv, 全 200); KEY_FID_BIND=0:0;1:0;2:0;3:0;4:0 (b1b22d03) | ✅ 与 R883 一致 |
| **DB now vs 末次错误** | DB now=22:49:52 UTC, 末次 cc4101-primary 错误=22:41:37 UTC (**8 分钟前**) | ✅ 事件已滑出 |
| **per-key nv_tier_attempts** | dsv4f0731_nv 近 20min 各 key 残留 NVCFPexecRemoteDisconnected/529/timeout ×1 (事件恢复期) | ✅ 无新错误 |
| **三容器 health** | nv_gw / cc4101 / dsv4p 均 ok, primary=dsv4f0731_nv, 5 keys, nv_gw/cc4101 Up 3h | ✅ |

### 关键判断: 窗口内 502 非新事件, 是 R883 06:41 同源突发的尾部残留; 系统按设计自愈, 不改码

与 R875-R882 的 hermes 外部 cron all_tiers_exhausted **不同**: cc4101-primary (cc2 自身路径)
曾真被 06:41 全键 429 突发撞击。**本轮独立复核"末次错误之后"重切窗口: 32/32 全 200 = 100%**, 
与 R883 记录 (22:44 后全 200) 完全吻合。nv_gw 日志铁证 (R883 已录, 06:41:42~06:43:17):

```
[06:41:42] NV-KEYMGR 429 tier=dsv4f0731_nv k3/k4/k5... count=8 cooldown=180s   # 全 key 同时 429
[06:41:47] NV-BUFFER-ALL-COOLING fail-fast → WAIT 180s
[06:43:17] NV-BUFFER-EXHAUSTED → ms_gw fallback → ms_gw 亦 fail
[06:43:44+] 全 request attempt1 SUCCESS ~10s (cooldown 恢复, fail-fast+recovery 生效)  # 自愈
```

关键点: **5 个 key 走不同 socks5h egress (7894/7897/7896/7899/7901) 同一秒同收 429 →
属 NVCF fid 级/上游级 rate limit, 非单 IP 问题**, 非 nv_gw 可 per-key 修复的外部限流。
系统设计内行为 (fail-fast → 180s cooldown → recovery) 正确自愈, 无新错误类,
当前 (22:41:37 UTC 后 8 分钟) 已 100% 干净, 成功请求全 fid=281478d0 未漂移。不改码 —
对**已记录、已自愈、当前 100% 干净**的同源事件尾部做风险改动违反审慎原则。

## 修复链 (沿用, R827+R828+R829+R833+R813)
1. glm5_2_nv 全 key 疲劳 → R829/R833 fail-fast + cc4101 动态 primary → dsv4f0731_nv
2. dsv4f0731_nv 一次成功, 用户无感知
3. 多 tier round-robin (dsv4p/dsv4f/glm5_2_nv) 自适应吸收底层跨 key 瞬态失败 (双 fid 现象)

## 健康检查
- `curl localhost:4101/health` → ok ✅ (cc4101, primary=dsv4f0731_nv)
- `curl localhost:40006/health` → ok ✅ (nv_gw, passthrough, 5 keys, nvcf_pexec_models 含 kimi_nv/dsv4p_nv/dsv4f_nv/dsv4f0731_nv/glm5_2_nv)
- `curl localhost:40066/health` → ok ✅ (dsv4p_nv40066, passthrough, 5 keys)
- docker ps: nv_gw = Up 3h, cc4101 = Up 3h, dsv4p_nv40066 = Up 2d (nv_gw_stable = Up 5d 对照)

## 参数快照 (无变化, R884, 与注入配置一致)

```
nv_gw(40006): pexec_us_rr 单模式, KEY_FID_BIND 全 bind b1b22d03, BUFFER 5×90s=450s, WAIT max 120s,
              TIER_COOLDOWN_S=180, TIER_TIMEOUT_BUDGET_S=180, KEY_COOLDOWN_S=30,
              NV_INTEGRATE_KEY_COOLDOWN_S=90, UPSTREAM_TIMEOUT=90, MIN_OUTBOUND_INTERVAL_S=10,
              FORCE_STREAM_UPGRADE=0 (FORCE_STREAM_UPGRADE_TIMEOUT=150), NVU_DISABLE_MS_FALLBACK=0,
              NVU_PEER_FB_SKIP_MODELS=glm5_2_nv,dsv4p_nv,
              NVU_BUFFER_CALLERS=cc4101-primary,openclaw2, NVU_CALLER_KEY_MAP=hermes:2;openclaw:3;opencode:4
cc4101(4101): PRIMARY 动态轮转 (primary=dsv4f0731_nv), FALLBACK=ms_gw:40007 (glm5_2_ms, chat/completions),
              STREAM_TOTAL_DEADLINE_S=470, PRIMARY_HEADER_TIMEOUT=400, UPSTREAM_TIMEOUT=130,
              UPSTREAM_IDLE_TIMEOUT=150, PRIMARY_FAIL_THRESHOLD=3, PRIMARY_SKIP_S=30,
              FALLBACK_UPSTREAM_MODEL=glm5_2_ms, PRIMARY_UPSTREAM_MODEL=dsv4f0731_nv
DB tz: UTC (STATE 时间为 CST = UTC+8)
```

## 下一步
- **观测窗口**: 确认 06:41 fid 级全键 429 事件是否**再出现独立新峰** (非本事件尾部)。判据:
  22:41:37 UTC 之后是否再现 `all_tiers_exhausted` 新错误。若 **新事件 >1 次/日** → 属
  dsv4f0731_nv (fid=281478d0) NVCF 级限流不稳定, 届时应评估 cc4101 primary 切换更稳 fid
  (cc4101 primary 决定逻辑不在 nv_gw scope, 只记录观察)。
- **不改码**。cc2 路径当前 (22:41:37 UTC 后) 已 100% 干净 (~10s)。待 cc2 路径 SR 掉 <99%
  且**非已知事件尾部** (即出现新错误峰) 或全键 429 恢复期 >30min 或出现新错误类 再动手。