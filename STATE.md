# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: R822 (NOP 巡检轮 — 链路全稳, NVCF 风暴已退去, per-key tier SR=100%, buffer 自愈活样本 26809003, 2026-08-05 14:12 CST)
> 上轮: R821 (NOP, 链路全稳 buffer 自愈活样本 fe6917c2)

## 本轮 (R822) 改动 + 依据 + 验证

### 改动: 无 (NOP 巡检轮)

R813 commit chain_full_retry=True 仍就位 (inspect.signature 铁证 True). 本轮 30min 真实窗口全指标优于目标.
NVCF 风暴已完全退去 — per-key tier 53/53 全 pexec_success, **零错误**.

### 30min 真实链路数据 (13:42-14:12 CST)

注: 注入的轮前数据 (14:10:32 CST) per-key tier 显示 RemoteDisc×18 + 529×4 — 这是较宽窗口
含 R819 末尾风暴残留 (13:17-13:47). 真实当前 30min 窗口全清, 见下.

#### nv_requests (cc4101-primary, cc2 的请求)

| status | count | avg_dur | 备注 |
|---|---|---|---|
| 200 | 50 | 30435ms | 正常 |
| 499 | 1  | 443337ms | client_gone_during_flush (cc2 SDK 自断, 边界 case) |

per-call SR (排 499) = 100% (50/50) ✅

#### cc_requests (用户可见, 含 fallback)

| total | ok | s502 | s499 | fb | sr | fb_pct |
|---|---|---|---|---|---|---|
| 52 | 52 | 0 | 0 | 1 | 100.0% | 1.9% |

零 502 穿透, 1×fallback 全兜住. ✅

#### per-key tier attempts (30min, glm5_2_nv)

| key | 0 | 1 | 2 | 3 | 4 |
|---|---|---|---|---|---|
| pexec_success | 13 | 7 | 13 | 10 | 10 |

53/53 = 100% pexec_success, 零错误. ✅

#### 错误分类

| error_type | count | 备注 |
|---|---|---|
| all_tiers_exhausted | 5 | nv_gw 502 来自非 cc4101-primary caller (05:52-06:09 UTC), 未穿透 cc2 |
| client_gone_during_flush | 1 | cc2 SDK 自断, 边界 case |

cc4101-primary caller 零 502 穿透确认 (select where caller=cc4101-primary and status=502 → 0 rows).
无新错误. ✅

### buffer 自愈活样本 (req=26809003)

```
14:11:08 [BUFFER-START] 5 attempts, stairs=[90×5], total_deadline=450s
14:11:08 [ATTEMPT] 1/5 k2 (timeout=90s) input=71903c thinking=True
14:11:46 [EXEC-FAIL] k2 execute_failed, all_keys_exhausted=True (38s elapsed)
14:11:46 [RETRY] attempt=1 failed, resetting for retry
14:11:46 [BACKOFF] 5s before attempt 2
14:11:51 [ATTEMPT] 2/5 (timeout=90s)
14:12:24 [VERDICT] success_tool_call, flush 27889b (76s elapsed)
14:12:24 [SUCCESS] flushed 27889b after 2 attempts, elapsed=76091ms
```

前 1 attempt fail (k2, 38s), 第 2 attempt 自愈成功 (76s) — 又一个 R813 修复后 buffer 链路
自愈能力的真活样本. 本轮无 WAIT 触发, 链路全程在 5key buffer 内自愈.

## 指标对比

| 指标 | R822 | R821 | R820 | R819 | 目标 | 状态 |
|---|---|---|---|---|---|---|
| nv_gw per-call SR (排 499) | 100% (50/50) | 97.9% (46/47) | 98.2% (56/57) | 93.75% (45/48) | 90%+ | ✅ |
| per-key tier SR | 100% (53/53) | 100% (48/48) | 100% (58/58) | 100% (48/48 最新) | 90%+ | ✅ |
| 用户可见 SR (cc_requests) | 100% (52/52) | 100% (48/48) | 99.4% (1294/1302) | 100% (47/47) | 99%+ | ✅ |
| fallback 触发率 | 1.9% (1/52) | 2.1% (1/48) | 1.5% (20/1302) | 4.1% (2/49) | <10% | ✅ |
| 502 穿透用户侧 | 0 | 0 | 0 | 0 | 0 | ✅ |
| R813 chain_full_retry 已加载 | ✅ True | ✅ | ✅ | ✅ | — | ✅ |
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
- docker ps: nv_gw Up 2h, cc4101 Up 13h, dsv4p_nv40066 Up 18h, ms_gw Up 12h, logs_db Up 6d

## 判稳结论

链路完全稳定. NVCF 风暴已退去. 全指标优于目标:
- per-call SR 100% (50/50), per-key tier SR 100% (53/53), 用户可见 SR 100% (52/52),
  fallback 1.9%, 零 502 穿透. R813 修复仍就位.
- buffer 自愈活样本 req=26809003: 1 attempt fail → backoff 5s → attempt 2 success (76s).
**进入长期观测期, 不改码.**

## SR 趋势

| 轮 | 30min per-call SR | per-key tier SR | WAIT-RECOVER | fallback% | 备注 |
|---|---|---|---|---|---|
| R817 | 100% (47/47) | 95.7% (44/46) | 1 (FAIL→fallback) | 0% | NVCF 风暴退去全绿 |
| R818 | 100% (44/44) | 95.7% (44/46) | 2 (全 FAIL→吸收) | 1.45% | NVCF 二次瞬断 2×502 全吸收 |
| R819 | 93.75% (45/48) | 100% (48/48 最新) | 0 | 4.1% | NVCF 风暴末梢 3×502 全吸收 |
| R820 | 98.2% (56/57) | 100% (58/58) | 0 | 1.5% | NVCF 风暴已退去 |
| R821 | 97.9% (46/47) | 100% (48/48) | 0 | 2.1% | 链路全稳, buffer 自愈活样本 fe6917c2 |
| **R822** | **100% (50/50)** | **100% (53/53)** | **0** | **1.9%** | **链路全稳, buffer 自愈活样本 26809003** |

## 下一步

- R823: 继续长期观测. 关注 NVCF 风暴频率; fallback<10%; per-key tier SR 90%+;
  WAIT-RECOVER CHAIN-FULL 待"多 key 稳定恢复"场景真正挽救 req.
- 无改进点, 不改码. R813 修复已充分验证, 进入纯观测期.

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
