# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: R865 (NOP 巡检轮 — 近窗 cc4101-primary SR=100% (124×200) 零错误, 残留 all_tiers_exhausted×4+stream_cap×1 全为 hermes 外部 cron, 不改码, 2026-08-07 ~05:1x CST)
> 上轮: R864 (NOP — 近窗 127×200 零错误, hermes 周期 all_tiers_exhausted 属外部 cron, 不改码)

## 本轮 (R865) 改动 + 依据 + 验证

### 改动: 无 (巡检轮 — cc2 路径全净 124×200, hermes 周期 all_tiers_exhausted 与 cc2 无关)

### 本轮数据 (~05:1x CST, 实时拉取, DB UTC)

**最近 30min cc4101-primary (cc2 自己路径) SR = 100% (124×200, 零错误).**

| 指标 | 值 | 状态 |
|---|---|---|
| **最近 30min cc4101-primary SR** | **100% (124×200)** | ✅ |
| **primary 目标 tier** | **dsv4f0731_nv** (自适应轮转持有, /health 确认) | ✅ |
| **error 归属** | all_tiers_exhausted×4 + stream_absolute_cap×1 全为 caller=hermes (外部 cron) | ✅ 与 cc2 无关 |
| **per-key tier attempts** | 123 pexec_success, 瞬态错误跨 key round-robin 吸收 | ✅ |
| **buffer** | 全 attempt1 一次成交 (8-12s, verdict=success_tool_call, flushed), 无退化 | ✅ |
| **三容器 health** | nv_gw / cc4101 / dsv4p 均 ok | ✅ |

### 关键判断: cc2 路径全净, hermes 周期 all_tiers_exhausted 非本链路问题

30min 窗口 5 条非 200 (502) 经 caller 字段核验 **全部 caller=hermes** (外部客户端, 非 cc4101),
严格 ~6min 周期 (20:42/20:48/20:54/21:00/21:06/21:09), 全 fid=52e1ddb6.
per-key nv_tier_attempts 显示 5 key 均有足量 pexec_success (24-25 总 123),
瞬态错误 (NVCFPexecRemoteDisconnected×12 / NVCFPexecTimeout×5 / empty_200×3 / 529_nv_overloaded×2 / 504_nv_gateway_timeout×1)
被 KeyManager 跨 key round-robin 修复链平滑吸收, 未上抛到 cc2 用户请求. cc2 路径 124×200 零错误,
buffer 全 attempt1 一次成交 (8-12s, flushed trailing 16KB), 证明链路/KeyManager 无退化. 不改码.

## 修复链 (沿用, R827+R828+R829+R833+R813)
1. glm5_2_nv 全 key 疲劳 → R829/R833 fail-fast + cc4101 动态 primary → dsv4f0731_nv
2. dsv4f0731_nv 1-12s 一次成功, 用户无感知
3. 多 tier round-robin (dsv4p/dsv4f/glm5_2_nv) 自适应吸收底层跨 key 瞬态失败

## 健康检查
- `curl localhost:4101/health` → ok ✅ (cc4101, primary=dsv4f0731_nv)
- `curl localhost:40006/health` → ok ✅ (nv_gw, passthrough, 5 keys, nvcf_pexec_models 含 dsv4p_nv/dsv4f_nv/dsv4f0731_nv/glm5_2_nv)
- `curl localhost:40066/health` → ok ✅ (dsv4p, passthrough, 5 keys)

## 参数快照 (无变化, R865)

```
nv_gw(40006): pexec_us_rr 单模式, KEY_FID_BIND 全 bind b1b22d03, BUFFER 5×90s=450s,
              WAIT max 120s, TIER_COOLDOWN_S=180, TIER_TIMEOUT_BUDGET_S=180,
              NVU_DISABLE_MS_FALLBACK=0 (ms_gw fallback 已恢复), NVU_BUFFER_CALLERS=cc4101-primary,openclaw2,
              KEY_COOLDOWN_S=30, NV_INTEGRATE_KEY_COOLDOWN_S=90, UPSTREAM_TIMEOUT=90,
              NVU_FORCE_STREAM_UPGRADE=0, NVU_FORCE_STREAM_UPGRADE_TIMEOUT=150
cc4101(4101): PRIMARY 动态轮转 (primary=dsv4f0731_nv), FALLBACK=ms_gw:40007 (glm5_2_ms),
              STREAM_TOTAL_DEADLINE_S=470, PRIMARY_HEADER_TIMEOUT=400, UPSTREAM_TIMEOUT=130,
              PRIMARY_FAIL_THRESHOLD=3, PRIMARY_SKIP_S=30
DB tz: UTC (STATE 时间为 CST = UTC+8)
```