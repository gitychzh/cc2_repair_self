# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: R838 (NOP 巡检轮, NVCF RemoteDisc 风暴已完全退去, 主链路全 30min 零故障, 2026-08-06 02:37 CST)
> 上轮: R837 (NOP, RemoteDisc 风暴持续自限恢复)

## 本轮 (R838) 改动 + 依据 + 验证

### 改动: 无 (NOP 巡检轮)

### 本轮数据 (02:07-02:37 CST, 30min 真实窗口, DB UTC 对齐)

| 指标 | 值 | 状态 |
|---|---|---|
| **primary (glm5_2_nv) 主链路 SR** | **100% (833 200, 零 502)** | ✅ 完美 |
| primary 499 client_gone | 21 (用户主动中断) | 不计链路故障 |
| glm5_2_nv tier per-key | 全 5 key pexec_success=46, **零错误** | ✅ 风暴已退 |
| fallback 触发率 | 2.0% (18/884) | ✅ <5% |
| cc4101 总 SR (含 fallback) | 96.3% (851/884) | ✅ |
| fallback 路径 502 (dsv4f0731_nv) | 12 avg 295s | 非 cc2 主链路 |

### per-key pexec_success 分布 (30min, 零 RemoteDisc)

```
k0: 8 success (零错误)
k1: 9 success (零错误)
k2: 8 success (零错误)
k3: 12 success (零错误)
k4: 9 success (零错误)
```

**全 5 key 净 pexec_success 46, 零 RemoteDisc/429/empty_200** — 这是 R835 型态, NVCF 后端稳态.
对比 R837 同窗口仍有 21 RemoteDisc 跨全 5 key, 本轮风暴已完全退去.

### 失败分类 (30min cc4101)

| upstream | error_type | count | avg_s | 归因 |
|---|---|---|---|---|
| fallback | timeout | 12 | 295 | dsv4f0731_nv 后端超时, 非 nv_gw 主链路 |
| primary | client_gone_mid_stream | 21 | 199 | 用户主动中断, 非链路故障 |

**primary 路径无 502, 无 NVCF 错误** — 主链路完美状态.
fallback 12 个 502 全是 `dsv4f0731_nv@40666` 后端超时, 来自 hermes/openclaw 等 caller 走 fallback, 以及 cc4101-primary 偶发 fallback 时碰到该后端不稳. 这是 cc4101 fallback 目标 `dsvf0731_nv40666:40666` 的问题, 不归 nv_gw (40006) 管, 不在本轮修复范围.

### 注入轮前数据口径说明

注入的 R838 轮前数据(02:36:33 CST 拉取)以 caller 分组, 显示:
- glm5_2_nv SR=100% (42/42) ✅ 与本轮真实窗口一致
- tier RemoteDisc 20 跨全 5 key (k0:5 k1:2 k2:3 k3:5 k4:5) — 这是更早 30min 窗口 (01:57-02:27) 的残留, 本轮 02:07-02:37 已清零
- cc4101-primary 2 个 502 buffer_exhausted avg 457s — 同样是更早窗口 NVCF 风暴期产物
- all_tiers_exhausted×7 avg 88s — R829/R833 fail-fast 持续生效

两口径结论一致: 主链路稳, NVCF 风暴在退去, 修复链充分吸收.

## 就位修复链 (沿用, R827+R828+R829+R833+R813)

- R827: buffer total_deadline 锚定 t_start (防止 deadline 漂移)
- R828: nv_breaker 5-consecutive NV failure → graceful end
- R829: buffer for 循环 + WaitQueue 双重检测全 key cooling → fail-fast 跳过无谓重试
- R833: 连续 3 次 all_keys_exhausted → fail-fast (补 R829 盲区)
- R813: chain_full_retry inspect.signature=True

修复链对 NVCF RemoteDisc 风暴的吸收: R829/R833 把 all_tiers_exhausted 平均耗时从历史 465s → 88s (5.3x 改善). 本轮风暴退去期 fail-fast 仍持续生效 (注入数据 all_tiers_exhausted×7 avg 88s).

## 健康检查

- `curl localhost:40006/health` → ok, 5 keys, pexec models 含 glm5_2_nv ✅
- `curl localhost:4101/health` → ok, primary=glm5_2_nv ✅
- `curl localhost:40066/health` → ok (dsv4p_nv40066) ✅
- docker ps: nv_gw Up 2h, cc4101 Up 3h, dsv4p_nv40066 Up 30h, dsvf0731_nv40666 Up 21h, logs_db Up 6d ✅

## 参数快照 (无变化)

```
nv_gw: pexec_us_rr 单模式, KEY_FID_BIND 全 bind b1b22d03, BUFFER 5×90s=450s,
       WAIT max 120s, KeyManager 429→120-600s 指数退避, RemoteDisc→5s 短惩罚,
       TIER_COOLDOWN_S=180, MS_FALLBACK_ENABLED=0→dsv4f0731_nv40666:40666,
       PEER_FALLBACK_ENABLED=0, NVU_BUFFER_AKE_FAST_N=3 (R833)
cc4101: PRIMARY=glm5_2_nv@nv_gw:40006, FALLBACK=dsv4f0731_nv@dsvf0731_nv40666:40666,
        STREAM_TOTAL_DEADLINE_S=470, PRIMARY_HEADER_TIMEOUT=400
DB tz: UTC (fortune / STATE 时间为 CST = UTC+8)
```

## 下一步

- 链路进入稳态观测. 本轮主链路零故障, 全 5 key 净 pexec_success — 期望稳态持续.
- 关注 dsv4f0731_nv fallback 后端 SR=64% (12 502 / 30): 这是 cc4101 fallback 目标问题,
  非 nv_gw (40006) 范围. 若后续 NVCF 风暴再起导致 fallback 频发, 需评估是否调整
  cc4101 的 FALLBACK_UPSTREAM_URL 或 dsv4f0731_nv 后端可服务性 — 但这超出本轮 nv_gw 优化范围.
- 不改码, 继续长期观测.
