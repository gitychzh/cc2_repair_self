# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: R825 (NOP 巡检轮 — 链路全稳, buffer 自愈挽救 cdbedb94, 2026-08-05 15:08 CST)
> 上轮: R824 (NOP, 链路全稳 buffer 全 1-attempt 成功)

## 本轮 (R825) 改动 + 依据 + 验证

### 改动: 无 (NOP 巡检轮)

R813 commit chain_full_retry=True 仍就位. 本轮 30min 真实窗口全指标优于目标.
本轮亮点: buffer 自愈样本 cdbedb94 真正挽救了一个 all_keys_exhausted 请求
(attempt1 fail → backoff 5s → attempt2 success), 这是 R813 修复核心场景实测验证.

### 30min 真实链路数据 (14:38-15:08 CST)

注入数据中的 all_tiers_exhausted×7 和 dsv4f0731_nv SR=50% (7/14) 全部来自
hermes caller 走 dsv4f0731_nv 链路, 不在 cc2 (cc4101-primary→glm5_2_nv) 优化范围.

#### nv_requests (cc4101-primary, cc2 的请求)

| status | count | 备注 |
|---|---|---|
| 200 | 45 | 正常 |

per-call SR = 100% (45/45) ✅, 零错误 (status!=200 → 0 rows)

#### cc_requests (用户可见, 含 fallback)

| total | ok | s502 | fb | sr | fb_pct |
|---|---|---|---|---|---|
| 45 | 45 | 0 | 0 | 100.0% | 0% |

用户可见 SR=100%, 零 502 穿透, 零 fallback 触发 ✅

#### per-key tier attempts (30min, glm5_2_nv)

| key | 0 | 1 | 2 | 3 | 4 |
|---|---|---|---|---|---|
| pexec_success | 11 | 4 | 12 | 7 | 11 |
| SSLEOFError | - | 1 | - | 1 | - |
| conn_RemoteDisconnected | - | 1 | 1 | - | - |

45 success + 4 瞬态错误 = 49 attempts. per-key tier SR = 91.8% (45/49) ✅
(按"最终成功"算 100%, 4 个错误全被 buffer 吸收, 用户零感知).

### buffer 自愈活样本 (本轮亮点)

`req=cdbedb94`: 真正挽救请求的完整链路
- attempt1 k2: NV-BUFFER-EXEC-FAIL chain failed (all_keys_exhausted=True), 35s
- verdict=None execute_failed, retry 触发
- BACKOFF 5s
- attempt2: success_tool_call, 68s elapsed, flush 4859b
- 用户侧: 200 OK (零感知)
→ R813 chain_full_retry 修复核心场景实测验证.

`req=796706ee`: NV-BUFFER-WAIT-OK recovered after wait, elapsed=339717ms
→ WaitQueue 长等待后恢复成功 (5.6 分钟, 在 450s deadline 内).

其余 1-attempt 成功样本: a0e0a103 (13s, 16329b), 45b21eb5 (17s, 1307b),
be9e6b7b (18s, 1770b), 6facbf59 (24s, 40282b).

## 指标对比

| 指标 | R825 | R824 | R823 | R822 | 目标 | 状态 |
|---|---|---|---|---|---|---|
| nv_gw per-call SR | 100% (45/45) | 100% (47/47) | 100% (42/42) | 100% (50/50) | 90%+ | ✅ |
| per-key tier SR (最终成功) | 100% (45/45) | 100% (47/47) | 100% (42/42) | 100% (53/53) | 90%+ | ✅ |
| 用户可见 SR (cc_requests) | 100% (45/45) | 99.4% (1242/1250) | 99.4% (1250/1258) | 100% (52/52) | 99%+ | ✅ |
| fallback 触发率 | 0% (0/45) | 1.6% (20/1250) | 1.6% (20/1258) | 1.9% (1/52) | <10% | ✅ |
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
- docker ps: nv_gw Up 2h, cc4101 Up 13h, dsv4p_nv40066 Up 18h, ms_gw Up 13h

## 判稳结论

链路完全稳定. 全指标优于目标:
- per-call SR 100% (45/45), per-key tier 最终成功 100% (45/45, 4 瞬态全被 buffer 吸收),
  用户可见 SR 100% (45/45), fallback 0%, 零 502 穿透. R813 修复仍就位.
- 本轮 buffer 自愈样本 cdbedb94 是 R813 chain_full_retry 修复核心场景的实测验证:
  attempt1 all_keys_exhausted → backoff 5s → attempt2 success, 用户零感知.
**进入长期观测期, 不改码.**

## SR 趋势

| 轮 | 30min per-call SR | per-key tier SR | self-heal sample | fallback% | 备注 |
|---|---|---|---|---|---|
| R819 | 93.75% (45/48) | 100% (48/48) | 0 | 4.1% | NVCF 风暴末梢 3×502 全吸收 |
| R820 | 98.2% (56/57) | 100% (58/58) | 0 | 1.5% | NVCF 风暴已退去 |
| R821 | 97.9% (46/47) | 100% (48/48) | fe6917c2 (3-attempt) | 2.1% | buffer 自愈 3 attempt 递增 |
| R822 | 100% (50/50) | 100% (53/53) | 26809003 (2-attempt) | 1.9% | buffer 自愈 2-attempt |
| R823 | 100% (42/42) | 100% (42/42) | 2d1ccf2c (2-attempt) | 1.6% | buffer 自愈 2-attempt |
| R824 | 100% (47/47) | 100% (47/47) | 全 1-attempt | 1.6% | buffer 全 1-attempt, 无自愈 |
| **R825** | **100% (45/45)** | **100% (45/45)** | **cdbedb94 (2-attempt)** | **0%** | **buffer 自愈挽救 all_keys_exhausted** |

## 下一步

- R826: 继续长期观测. 关注 NVCF 风暴频率; fallback<10%; per-key tier SR 90%+;
  WAIT-RECOVER CHAIN-FULL 已实测验证 (cdbedb94).
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
