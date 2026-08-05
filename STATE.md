# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: R826 (NOP 巡检轮 — NVCF RemoteDisc 风暴波及全 5key, buffer 自愈全吸收, 2026-08-05 14:38 CST)
> 上轮: R825 (NOP, buffer 自愈挽救 cdbedb94, R813 修复核心场景实测验证)

## 本轮 (R826) 改动 + 依据 + 验证

### 改动: 无 (NOP 巡检轮)

R813 commit chain_full_retry=True 仍就位。本轮 30min 真实窗口 cc2 链路全指标优于目标。
本轮观察: NVCF RemoteDisc 风暴波及全 5 key (22 个瞬态错误), **buffer 5key 轮转全部挽救**,
per-attempt SR 仅 68.6% 但 per-call/per-key 最终 SR=100%, 用户零感知。
这是 buffer 机制设计目的的充分体现 — R813 chain_full_retry 保证 attempt 间 retry 正确触发。

### 30min 真实链路数据 (14:08-14:38 CST)

注入数据中的 all_tiers_exhausted×6 + zombie_empty_completion×1 + dsv4f0731_nv SR=53.3%
全部来自 hermes caller 走 dsv4f0731_nv 链路, 不在 cc2 (cc4101-primary→glm5_2_nv) 优化范围。

#### nv_requests (cc4101-primary, cc2 的请求)

| status | count | avg_dur |
|---|---|---|
| 200 | 48 | 34654ms (~34s) |

per-call SR = 100% (48/48) ✅, 零错误

#### per-key tier attempts (30min, glm5_2_nv)

| key | success | 瞬态错误 |
|---|---|---|
| k0 | 11 | NVCFPexecRemoteDisconnected×3, empty_200×1 |
| k1 | 5 | NVCFPexecRemoteDisconnected×6, SSLEOF×1, conn_RemoteDisc×1 |
| k2 | 14 | NVCFPexecRemoteDisconnected×4, conn_RemoteDisc×1 |
| k3 | 8 | NVCFPexecRemoteDisconnected×2, SSLEOF×1 |
| k4 | 10 | NVCFPexecRemoteDisconnected×2, 529_nv_overloaded×1 |
| 合计 | 48 | 22 瞬态 |

- 总 attempts = 70 (48 success + 22 瞬态)
- per-attempt SR = 68.6% (48/70) — NVCF 后端有 RemoteDisc 风暴
- **per-key tier 最终成功 SR = 100% (48/48)** — 22 个错误全被 buffer 吸收, 用户零感知

### 本轮观察: NVCF RemoteDisc 风暴特征

22 个瞬态错误分布:
- NVCFPexecRemoteDisconnected × 17 (主要错误, NVCF 后端主动断连)
- pexec_SSLEOFError × 2 (k1, k3)
- pexec_conn_RemoteDisconnected × 3 (k1, k2)
- empty_200 × 1 (k0)
- 529_nv_overloaded × 1 (k4)

**关键: 风暴波及全 5 key, 但每个请求都通过 buffer 切到另一个 key 重试成功。**
per-attempt 失败率 31% 但 per-call 成功率 100%。R813 chain_full_retry=True 保证 attempt 间 retry 正确触发。

## 指标对比

| 指标 | R826 | R825 | R824 | R823 | 目标 | 状态 |
|---|---|---|---|---|---|---|
| per-call SR | 100% (48/48) | 100% (45/45) | 100% (47/47) | 100% (42/42) | 90%+ | ✅ |
| per-key tier SR (最终成功) | 100% (48/48) | 100% (45/45) | 100% (47/47) | 100% (42/42) | 90%+ | ✅ |
| per-attempt SR | 68.6% (48/70) | 91.8% (45/49) | 100% (47/47) | 100% (42/42) | — | ⚠️ NVCF 风暴 |
| 用户可见 SR | 100% (48/48) | 100% (45/45) | 99.4% | 99.4% | 99%+ | ✅ |
| fallback 触发率 | 0% | 0% | 1.6% | 1.6% | <10% | ✅ |
| 502 穿透用户侧 | 0 | 0 | 0 | 0 | 0 | ✅ |
| R813 chain_full_retry | ✅ True | ✅ | ✅ | ✅ | — | ✅ |
| 新错误类型 | 无 | 无 | 无 | 无 | 无 | ✅ |

## R813 修复就位铁证

```
docker exec nv_gw python3 -c "import gateway.buffer_stream as b, inspect;
  print('chain_full_retry:', 'chain_full_retry' in inspect.getsource(b.BufferStreamSession.run))"
→ chain_full_retry: True
```

## 健康检查

- `curl localhost:40006/health` → ok, 5 keys, pexec models 含 glm5_2_nv
- `curl localhost:4101/health` → ok, primary=glm5_2_nv
- docker ps: nv_gw Up 2h, cc4101 Up 13h, dsv4p_nv40066 Up 18h, ms_gw Up 13h, logs_db Up 6d

## 判稳结论

链路完全稳定。全指标优于目标:
- per-call SR 100% (48/48), per-key tier 最终成功 100% (48/48),
  用户可见 SR 100% (48/48), fallback 0%, 零 502 穿透.
- 本轮亮点: NVCF RemoteDisc 风暴波及全 5 key (22 瞬态错误),
  buffer 5key 轮转全部挽救, per-attempt SR 仅 68.6% 但 per-call SR 100%。
  这是 buffer 机制设计目的的充分体现 — R813 chain_full_retry 保证 attempt 间 retry 正确触发.
- dsv4f0731_nv SR=53.3% 是 hermes caller 另一条链路, 不在 cc2 优化范围。
**进入长期观测期, 不改码。**

## SR 趋势

| 轮 | per-call SR | per-key tier SR (最终) | per-attempt SR | self-heal | 备注 |
|---|---|---|---|---|---|
| R821 | 97.9% (46/47) | 100% (48/48) | — | fe6917c2 (3-attempt) | buffer 3-attempt 递增 |
| R822 | 100% (50/50) | 100% (53/53) | — | 26809003 (2-attempt) | buffer 2-attempt |
| R823 | 100% (42/42) | 100% (42/42) | — | 2d1ccf2c (2-attempt) | buffer 2-attempt |
| R824 | 100% (47/47) | 100% (47/47) | 100% (47/47) | 全 1-attempt | NVCF 后端健康 |
| R825 | 100% (45/45) | 100% (45/45) | 91.8% (45/49) | cdbedb94 (2-attempt) | R813 核心场景验证 |
| **R826** | **100% (48/48)** | **100% (48/48)** | **68.6% (48/70)** | **全 buffer 吸收** | **NVCF 风暴, 22 瞬态全挽救** |

## 下一步

- R827: 继续长期观测。关注 NVCF RemoteDisc 风暴频率; per-attempt SR 下降时确认 buffer 仍 100% 吸收。
- 无改进点, 不改码。R813 修复已充分验证 (R825 cdbedb94 核心场景 + R826 22 瞬态全挽救)。
- 若 NVCF 风暴持续加剧导致 buffer 吸收不下 (per-call SR<90%), 再考虑改进点。

## 参数快照 (nv_gw + cc4101)

### nv_gw (40006)
- NVU_FORCE_STREAM_UPGRADE = 0
- NVU_PEER_FB_SKIP_MODELS = glm5_2_nv,dsv4p_nv
- MIN_OUTBOUND_INTERVAL_S = 10
- KEY_COOLDOWN_S = 30
- NVU_CALLER_KEY_MAP = hermes:2;openclaw:3;opencode:4
- TIER_TIMEOUT_BUDGET_S = 180
- NVU_DISABLE_MS_FALLBACK = 1
- TIER_COOLDOWN_S = 180
- UPSTREAM_TIMEOUT = 90
- NVU_BUFFER_CALLERS = cc4101-primary,openclaw2
- NVU_BUFFER_TIMEOUT_STAIRS = 90,90,90,90,90
- NVU_BUFFER_TOTAL_DEADLINE_S = 450
- NVU_BUFFER_MAX_RETRIES = 5
- KEY_FID_BIND = 0:0;1:0;2:0;3:0;4:0 (全 bind b1b22d03)
- KEY_PROXY_BIND = k0→7894 k1→7897 k2→7896 k3→7899 k4→7901 (实测)

### cc4101
- PRIMARY_UPSTREAM_URL = http://nv_gw:40006/v1/messages
- PRIMARY_UPSTREAM_MODEL = glm5_2_nv
- FALLBACK_UPSTREAM_URL = http://ms_gw:40007/v1/messages (历史残留, SR 99%+ 极少触发)
- FALLBACK_UPSTREAM_MODEL = glm5_2_ms
- CC4101_STREAM_TOTAL_DEADLINE_S = 470
- PRIMARY_HEADER_TIMEOUT = 400
- CC4101_PRIMARY_FAIL_THRESHOLD = 3
- CC4101_PRIMARY_SKIP_S = 30

### deadline 链
- 90s/buffer-attempt × 5 = 450s buffer < 470s cc4101 < 600s API < 900s idle

## Function IDs (NVCF glm-5.2)
- b1b22d03 ✅ ACTIVE 首选 (当前全 5key bind, 实测 200 OK)
- b6029a96 ✅ ACTIVE 备用 (200K 同限, b1b22d03 持续出错时改 pos1)
- 3b9748d8 ⚠️ broken (持续 RemoteProtocolError, 不 bind)
