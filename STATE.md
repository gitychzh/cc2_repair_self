# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: R872 (NOP 巡检轮 — 近窗 cc4101-primary SR=100% (120×200) 零错误, 残留 all_tiers_exhausted×5+stream_cap×1 全为 caller=hermes 外部 cron, fallback 0%, 不改码, 2026-08-07 ~05:40 CST)
> 上轮: R871 (NOP — 近窗 126×200 零错误, hermes 周期 all_tiers_exhausted×5+stream_cap×1 属外部 cron, 不改码)

## 本轮 (R872) 改动 + 依据 + 验证

### 改动: 无 (巡检轮 — cc2 路径全净 120×200, hermes 周期 all_tiers_exhausted 与 cc2 无关)

### 本轮数据 (~05:40 CST, 轮前链路分析注入, DB UTC)

**最近 30min cc4101-primary (cc2 自己路径) SR = 100% (120×200, 零错误).**

| 指标 | 值 | 状态 |
|---|---|---|
| **最近 30min cc4101-primary SR** | **100% (120×200)** | ✅ |
| **primary 目标 tier** | **dsv4f0731_nv** (自适应轮转持有, /health 确认) | ✅ |
| **30min 按模型 SR** | dsv4f0731_nv = 95.2% (120/126) | 与 cc2 路径 100% 一致 |
| **error 归属** | all_tiers_exhausted×5 + stream_absolute_cap×1 全为 caller=hermes (外部 cron, 非 cc4101) | ✅ 与 cc2 无关 |
| **非 200 归属** | 6 条全 caller=hermes (cc4101-primary 0 错误) | ✅ |
| **fallback 触发率** | 0 (131 请求 0 fallback) | ✅ |
| **buffer** | 无 buffer/wait/keymanager 日志 → 全 attempt1 一次成交 | ✅ 无退化 |
| **per-key nv_tier_attempts** | dsv4f0731_nv 5key 均 24 次 pexec_success (共 120 成功), 瞬态错误被跨 key 吸收 | ✅ |
| **三容器 health** | nv_gw / cc4101 / dsv4p 均 ok, primary=dsv4f0731_nv | ✅ |

### 关键判断: cc2 路径全净, hermes 周期 all_tiers_exhausted 非本链路问题

30min 窗口链路总览: cc4101-primary 120×200 零错误, 6 条非 200 (502) 经 caller 核验
**全部 caller=hermes** (外部客户端, 非 cc4101): all_tiers_exhausted×5 + stream_absolute_cap×1.
每次 all_tiers_exhausted avg ~180035ms ≈ 5×90s=450s buffer deadline 全额耗尽 —
沿用 R853-R871 判定: 属 hermes 外部 cron 请求特征而非链路退化.

per-key nv_tier_attempts (tier=dsv4f0731_nv): 5key 均 24 次 pexec_success (共 120 成功),
瞬态错误 (NVCFPexecRemoteDisconnected×20/NVCFPexecTimeout×5/529_nv_overloaded×2/empty_200×2)
被 KeyManager 跨 key round-robin 修复链自适应吸收, 未上抛到 cc2 用户请求.
cc2 自身路径 120×200 零错误, fallback 0%, 无 buffer/wait 日志,
证明链路/KeyManager 无退化. 不改码.

## 修复链 (沿用, R827+R828+R829+R833+R813)
1. glm5_2_nv 全 key 疲劳 → R829/R833 fail-fast + cc4101 动态 primary → dsv4f0731_nv
2. dsv4f0731_nv 1-12s 一次成功, 用户无感知
3. 多 tier round-robin (dsv4p/dsv4f/glm5_2_nv) 自适应吸收底层跨 key 瞬态失败 (双 fid 现象)

## 健康检查
- `curl localhost:4101/health` → ok ✅ (cc4101, primary=dsv4f0731_nv)
- `curl localhost:40006/health` → ok ✅ (nv_gw, passthrough, 5 keys, nvcf_pexec_models 含 kimi_nv/dsv4p_nv/dsv4f_nv/dsv4f0731_nv/glm5_2_nv)
- `curl localhost:40066/health` → ok ✅ (dsv4p_nv40066, passthrough, 5 keys)
- docker ps: nv_gw = Up 2h, cc4101 = Up 2h, dsv4p = Up 2d (nv_gw_stable = Up 5d 对照)

## 参数快照 (无变化, R872)

```
nv_gw(40006): pexec_us_rr 单模式, KEY_FID_BIND 全 bind b1b22d03 (0:0;1:0;2:0;3:0;4:0), BUFFER 5×90s=450s (STAIRS 90,90,90,90,90, RETRIES=5),
              WAIT max 120s, TIER_COOLDOWN_S=180, TIER_TIMEOUT_BUDGET_S=180,
              KEY_COOLDOWN_S=30, NV_INTEGRATE_KEY_COOLDOWN_S=90, UPSTREAM_TIMEOUT=90,
              MIN_OUTBOUND_INTERVAL_S=10, NVU_DISABLE_MS_FALLBACK=0,
              NVU_BUFFER_CALLERS=cc4101-primary,openclaw2
cc4101(4101): PRIMARY 动态轮转 (primary=dsv4f0731_nv), FALLBACK=ms_gw:40007 (glm5_2_ms, chat/completions),
              STREAM_TOTAL_DEADLINE_S=470, PRIMARY_HEADER_TIMEOUT=400, UPSTREAM_TIMEOUT=130,
              PRIMARY_FAIL_THRESHOLD=3, PRIMARY_SKIP_S=30
DB tz: UTC (STATE 时间为 CST = UTC+8)
```

## 下一步
- 长期观测。glm5_2_nv 冷却退去后观察 cc4101 primary 是否自动回归 glm5_2_nv (主链路目标)。
- hermes 周期 all_tiers_exhausted 属外部客户端 cron (严格 ~6min/180s buffer 全额耗尽, 非 cc2 使命); 持续观察是否影响 NV 成功指标 (当前无影响)。
- 不改码。修复链充分, cc2 近窗全净 (dsv4f0731_nv primary 维持 100% 则持续 NOP; 待 cc2 路径 SR 掉 <99% 或 buffer 退化 (>1 attempt) 再动手)。