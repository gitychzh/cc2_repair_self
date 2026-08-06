# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: R883 (巡检轮 — **cc2 路径曾遭 NVCF/fid 级 429 全 5 key 同时冷却撞击** (06:41 CST, all_tiers_exhausted+buffer_exhausted), 30min cc4101-primary SR=47.8% (11×200/12×502), 但 fail-fast+cooldown 180s 后 auto-recover (06:43:44 起全 attempt1 ~10s), 22:41:37 UTC 后 0 错误, 无新错误类, **系统自愈、不改码**, 2026-08-07 ~06:46 CST)
> 上轮: R882 (NOP — 近窗 104×200 零错误, all_tiers_exhausted×6 全为 hermes 外部 cron, 不改码)

## 本轮 (R883) 改动 + 依据 + 验证

### 改动: 无 (瞬态全键 429 事件, 系统设计内自愈, 非代码缺陷, 不改码)

### 本轮数据 (~06:46 CST, 轮前链路分析注入 + 独立复核, DB UTC 22:46)

**近 30min cc4101-primary (cc2 路径) SR = 47.8% (11×200 / 12×502)** — 被单次瞬态 429 突发拉起。
**近 8min (22:37~22:45 UTC): 11×200 + 5×502 (502 全 ≤22:41:37 残留, 22:44 后全 200).**

| 指标 | 值 | 状态 |
|---|---|---|
| **近 30min cc4101-primary SR** | **47.8% (11/23)** — 单次瞬态 429 撞击 | ⚠️ 已自愈 |
| **primary 目标 tier** | **dsv4f0731_nv** (自适应轮转持有, /health 确认) | ✅ |
| **30min caller×tier×status** | cc4101-primary\|dsv4f0731_nv\|200\|11 (avg 7s); 同\|502\|7 (avg 203s); cc4101-primary\|\|502\|5 (avg 47s); hermes\|dsv4f0731_nv\|502\|13 (avg 30s) | cc2 受撞击 |
| **502 时间窗 (cc2)** | 仅 UTC 22:16~22:41:37 (all_tiers_exhausted, dur 45~235s); **22:41:37 后 0 错误** | ✅ 已止 |
| **错误分类** | all_tiers_exhausted×20, buffer_exhausted×5 | 已知类, 无新错误 |
| **fallback 触发率** | buffer exhausted 后试 ms_gw, ms_gw 亦 fail (发错误回 CC) | 触发即告警 |
| **buffer 行为** | 06:41:42 全 5 key 429(180s)→k4 SSLEOFError→all_keys_exhausted→fail-fast attempt1→WAIT 180s→06:43:44 恢复全 attempt1 success (~10s) | ✅ 按设计 |
| **per-key nv_tier_attempts** | dsv4f0731_nv 5 key NVCFPexecRemoteDisconnected 1~2/key + pexec_success 2/key (恢复期), k5 无 error | ✅ |
| **三容器 health** | nv_gw / cc4101 / dsv4p 均 ok, primary=dsv4f0731_nv, 5 keys, nv_gw/cc4101 Up 3h | ✅ |

### 关键判断: 瞬态 NVCF/fid 级 429 突发, 系统设计内自愈, 非代码缺陷

本次与 R875-R882 的 hermes 外部 cron all_tiers_exhausted **不同**: cc4101-primary (cc2 自身路径)
本次真被撞击 (12×502)。nv_gw 日志铁证 (06:41:42~06:43:17):

```
[06:41:42] NV-KEYMGR 429 tier=dsv4f0731_nv k3/k4/k5... count=8 cooldown=180s   # 全 key 同时 429
[06:41:47] NV-KEYMGR transport_err k4 type=SSLEOFError penalty=10s
[06:41:47] NV-BUFFER-EXEC-FAIL all_keys_exhausted=True                          # 5 key 全冷却
[06:41:47] NV-BUFFER-ALL-COOLING fail-fast → WAIT 180s
[06:43:17] NV-BUFFER-EXHAUSTED → ms_gw fallback → ms_gw 亦 fail               # ms_gw 未恢复
[06:43:44+] 全 request attempt1 SUCCESS ~10s (cooldown 恢复, fail-fast+recovery 生效)  # 自愈
```

关键点: **5 个 key 走不同 socks5h egress (7894/7897/7896/7899/7901) 却在同一秒同收 429 →
属 NVCF fid 级/上游级 rate limit, 非单 IP 问题**, 非 nv_gw 可 per-key 修复的外部限流。
系统设计内行为 (fail-fast → 180s cooldown → recovery) 正确自愈, 无新错误类,
当前 (22:41:37 UTC 后) 已 100% 干净。不改码 — 对已自愈瞬态事件做风险改动违反审慎原则。

## 修复链 (沿用, R827+R828+R829+R833+R813)
1. glm5_2_nv 全 key 疲劳 → R829/R833 fail-fast + cc4101 动态 primary → dsv4f0731_nv
2. dsv4f0731_nv 一次成功, 用户无感知
3. 多 tier round-robin (dsv4p/dsv4f/glm5_2_nv) 自适应吸收底层跨 key 瞬态失败 (双 fid 现象)

## 健康检查
- `curl localhost:4101/health` → ok ✅ (cc4101, primary=dsv4f0731_nv)
- `curl localhost:40006/health` → ok ✅ (nv_gw, passthrough, 5 keys, nvcf_pexec_models 含 kimi_nv/dsv4p_nv/dsv4f_nv/dsv4f0731_nv/glm5_2_nv)
- `curl localhost:40066/health` → ok ✅ (dsv4p_nv40066, passthrough, 5 keys)
- docker ps: nv_gw = Up 3h, cc4101 = Up 3h, dsv4p_nv40066 = Up 2d (nv_gw_stable = Up 5d 对照)

## 参数快照 (无变化, R883, 与注入配置一致)

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
- **观测窗口**: 寒本次全键 429 属 fid 级瞬态, 已自愈。持续观察 dsv4f0731_nv (fid=281478d0)
  是否再发生全 5 key 同时 429。若 **>1 次/日 频率** → 属该 fid NVCF 级限流不稳,
  届时应评估 cc4101 primary 切换更稳 fid (但 cc4101 primary 决定逻辑不在 nv_gw scope, 只记录观察)。
- **不改码**。cc2 路径当前已恢复 (22:44 后全 200, ~10s)。待 cc2 路径 SR 再掉 <99% 或
  全键 429 恢复期 >30min 或出现新错误类 再动手。