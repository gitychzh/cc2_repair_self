# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: R836 (NOP 巡检轮, NVCF RemoteDisc 瞬态风暴波及 5key → 自限恢复, 2026-08-06 02:23 CST)
> 上轮: R835 (NOP, tier 零错误)

## 本轮 (R836) 改动 + 依据 + 验证

### 改动: 无 (NOP 巡检轮)

### 本轮数据 (02:23 CST, 30min 真实窗口 01:53-02:23 CST)

| 指标 | 值 | 状态 |
|---|---|---|
| cc4101 总 SR (全 caller) | 96.2% (861/895) | ✅ >85% |
| cc4101-primary SR (cc2 自己) | 88.2% (30/34) | ⚠️ 但已恢复 |
| glm5_2_nv tier per-key SR | 100% (31/31 pexec_success) | ✅ |
| fallback 触发率 | 2.1% (19/895) | ✅ <5% |
| NV 成功吞吐 | ~1720/h | ✅ 高位 |

### 失败时间分布 (关键: 风暴已自限)

- 17:50-18:03 UTC (01:50-02:03 CST): 4 次失败集中 (NVCF 风暴期)
- 18:04-18:23 UTC (02:04-02:23 CST): **19 分钟连续零失败** (恢复期)

链路窗口前后分裂: 早期风暴, 后期全清.

### 错误分类 (30min)

| mapped_model | 502 count | avg_ms | 分析 |
|---|---|---|---|
| dsv4f0731_nv | 8 | 89s | fallback 路径超时, 非主链路 |
| glm5_2_nv | 2 | 306s | 主链路 buffer 耗尽, 306s < 450s = R829/R833 fail-fast 生效 |

cc4101-primary 4 失败: buffer_exhausted×2 (428s) + IncompleteRead×1 (152s) + all_tiers_exhausted×1 (**96s = R829/R833 fail-fast**)

### per-key fid 健康 (30min)

```
k0: b1b22d03 pexec 6/6 ok (100%)
k1: b1b22d03 pexec 6/6 ok (100%)
k2: b1b22d03 pexec 5/5 ok (100%)
k3: b1b22d03 pexec 9/9 ok (100%)
k4: b1b22d03 pexec 5/5 ok (100%)
```

全 5 key 100% tier 成功. 19 次 RemoteDisc 是 in-flight 失败被 buffer 5key 轮转吸收.

### buffer 日志 (02:13-02:17)

最近 6 个请求全 1-attempt success (5-22s). req=3b96e1af 第 3 attempt 成功 (前 2 被 RemoteDisc) — buffer 5key 轮转设计目的充分体现.

## 就位修复链 (沿用, R827+R828+R829+R833)

- R827: buffer total_deadline 锚定 t_start (防止 deadline 漂移)
- R828: nv_breaker 5-consecutive NV failure → graceful end
- R829: buffer for 循环 + WaitQueue 双重检测全 key cooling → fail-fast 跳过无谓重试
- R833: 连续 3 次 all_keys_exhausted → fail-fast (补 R829 盲区)
- R813: chain_full_retry inspect.signature=True

## 健康检查

- `curl localhost:40006/health` → ok, 5 keys, pexec models 含 glm5_2_nv
- `curl localhost:4101/health` → ok, primary=glm5_2_nv
- docker ps: nv_gw Up ~1h (容器重启 3h ago 之外), cc4101 Up 3h, dsv4p_nv40066 Up 30h, dsvf0731_nv40666 Up 21h, logs_db Up 6d

## 参数快照 (无变化)

```
nv_gw: pexec_us_rr 单模式, KEY_FID_BIND 全 bind b1b22d03, BUFFER 5×90s=450s,
       WAIT max 120s, KeyManager 429→120-600s 指数退避, RemoteDisc→5s 短惩罚,
       TIER_COOLDOWN_S=180, MS_FALLBACK_ENABLED=1→dsv4p_nv40066:dsv4f0731_nv40666,
       PEER_FALLBACK_ENABLED=0, NVU_BUFFER_AKE_FAST_N=3 (R833)
cc4101: PRIMARY=glm5_2_nv@nv_gw:40006, FALLBACK=dsv4f0731_nv@dsvf0731_nv40666:40666,
        STREAM_TOTAL_DEADLINE_S=470, PRIMARY_HEADER_TIMEOUT=400
```

## 下一步

- 继续观测, 确认风暴退去后 tier 零错误持续 (像 R835 那样)
- R829 ALL-COOLING 仍待场景触发验证 (本轮 1 次 all_tiers_exhausted 96s 可能是其触发, 但无显式日志确认)
- 长期目标: 最大化 NV 成功吞吐量, 当前 ~1720/h 高位
- NVCF RemoteDisc 风暴是后端问题, 不可侧修复, 现有 buffer+fail-fast 机制充分吸收
