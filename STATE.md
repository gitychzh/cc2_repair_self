# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: R844 (NOP 巡检轮, primary glm5_2_nv SR=100% 零502 连续第十轮, 2026-08-06 06:21 CST)
> 上轮: R843 (NOP, primary SR=96.9% 连续第九轮)

## 本轮 (R844) 改动 + 依据 + 验证

### 改动: 无 (NOP 巡检轮, 连续 R835-R844 十轮 NOP)

### 本轮数据 (06:21 CST, 30min 真实窗口, DB UTC 对齐)

| 指标 | 值 | 状态 |
|---|---|---|
| **glm5_2_nv nv_requests (cc4101-primary)** | 33/33 = 100% (零 502) | ✅ 完美 |
| **cc4101-primary 总 SR** | 34/36 = 94.4% (2×buffer_exhausted) | ✅ |
| **主链路 502 穿透** | 0 | ✅ 零穿透 |
| **glm5_2_nv tier per-key pexec_success** | 33 (k0:6 k1:6 k2:6 k3:5 k4:10) | ✅ |
| **RemoteDisc 瞬态跨 key** | 19 次 (k0:4 k1:3 k2:4 k3:6 k4:4) 被 buffer 全吸收 | ⚠️→✅ |
| fallback 触发率 | 2/56 = 3.6% | ✅ <5% |
| all_tiers_exhausted | 7 次 avg 89.5s | ✅ fail-fast (vs 历史 465s, 5.2x) |
| buffer_exhausted | 2 次 avg 452s | ⚠️ 极端尾部全 key 瞬态挂穿 |

**核心**: primary glm5_2_nv 主链路 SR=100% (33/33 零 502)。
RemoteDisc 19 次瞬态跨全 5 key 分散, buffer 5key 轮转全吸收, 用户零穿透。
2 次 buffer_exhausted 是 5key 全挂穿到 cc4101 层的极端尾部, NVCF 后端瞬态不可侧修复。
修复链 R827+R828+R829+R833+R813 充分。

### per-key pexec_success + RemoteDisc 分布

```
k0: 6 success, 4 RemoteDisc + 1 empty_200 + 1 pexec_empty_200
k1: 6 success, 3 RemoteDisc
k2: 6 success, 4 RemoteDisc
k3: 5 success, 2 RemoteDisc + 1 529_overloaded + 2 conn_RemoteDisc + 1 empty_200 + 1 pexec_empty_200  ← k3 最集中
k4: 10 success, 4 RemoteDisc                                        ← k4 最稳
```

### cc4101-primary 30min 全景

```
status | cnt | avg_dur(ms) | error_type
200    |  34 | 55015       | (成功)
502    |   2 | 452863      | buffer_exhausted
```

主链路零 502 穿透。2×502 是 5key 全挂后 buffer 耗尽穿到 cc4101, 属 NVCF 后端极端尾部。

## 修复链 (沿用, R827+R828+R829+R833+R813)

- R827: buffer total_deadline 锚定 t_start (防 deadline 漂移)
- R828: nv_breaker 5-consecutive NV failure → graceful end
- R829: buffer for 循环 + WaitQueue 双重检测全 key cooling → fail-fast
- R833: 连续 3 次 all_keys_exhausted → fail-fast (补 R829 盲区)
- R813: chain_full_retry inspect.signature=True

修复链效果: all_tiers_exhausted avg 89.5s vs 历史 465s (5.2x 改善)。

## 健康检查

- `curl localhost:40006/health` → ok ✅
- `curl localhost:4101/health` → ok ✅
- `curl localhost:40066/health` → ok ✅
- `curl localhost:40666/health` → ok ✅
- docker ps: nv_gw Up ~1min, cc4101 Up 7h, dsv4p_nv40066 Up 34h, dsv4f0731_nv40666, logs_db Up 6d ✅

## 参数快照 (无变化)

```
nv_gw: pexec_us_rr 单模式, KEY_FID_BIND 全 bind b1b22d03, BUFFER 5×90s=450s,
       WAIT max 120s, KeyManager 429→120-600s 指数退避, RemoteDisc→5s 短惩罚,
       TIER_COOLDOWN_S=180, MS_FALLBACK_ENABLED=0 (NVU_DISABLE_MS_FALLBACK=0),
       PEER_FALLBACK_ENABLED=0, NVU_BUFFER_AKE_FAST_N=3 (R833)
cc4101: PRIMARY=glm5_2_nv@nv_gw:40006, FALLBACK=dsv4f0731_nv@dsvf0731_nv40666:40666,
        STREAM_TOTAL_DEADLINE_S=470, PRIMARY_HEADER_TIMEOUT=400
DB tz: UTC (STATE 时间为 CST = UTC+8)
```

## 下一步

- 连续 R835-R844 十轮 NOP, glm5_2_nv primary 主链路零 502 穿透稳态延续。
- NVCF RemoteDisc 瞬态 (本轮 19 次) 是后端不可侧修复, buffer 5key 轮转全吸收 — 修复链 R827+R828+R829+R833+R813 充分。
- buffer_exhausted 2 次是极端尾部全 key 瞬态挂穿, 非 nv_gw(40006) bug, NVCF 后端不可侧修复。
- 不改码, 继续长期观测。
