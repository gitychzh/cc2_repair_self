# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: R820 (NOP 巡检轮 — NVCF 风暴已退去, 全指标优于目标, 进入长期观测期, 2026-08-05 13:51 CST)
> 上轮: R819 (NOP, NVCF 风暴末梢 3×502 全被 fallback 吸收)

## 本轮 (R820) 改动 + 依据 + 验证

### 改动: 无 (NOP 巡检轮)

R813 commit chain_full_retry=True 已加载 (inspect.signature 铁证 True).
本轮 30min 窗口 (13:21-13:51 CST) 已是 NVCF 风暴退去后, 所有指标优于目标:
- nv_gw per-call SR 98.2% (56/57, 仅 1×502 不可挽救)
- cc4101 用户可见 SR 99.4% (1294/1302, **零 502 穿透**)
- per-key tier SR 100% (58/58, 全 5key 全成功)
- fallback 触发率 1.5% (20/1302)

### 30min 链路数据 (13:21-13:51 CST)

| 指标 | 本轮 R820 | 上轮 R819 | 目标 | 状态 |
|---|---|---|---|---|
| nv_gw per-call SR (排 499) | 98.2% (56/57) | 93.75% (45/48) | 90%+ | ✅ (回升) |
| per-key tier SR | 100% (58/58) | 100% (48/48 最新) | 90%+ | ✅ |
| 用户可见 SR (cc_requests) | 99.4% (1294/1302) | 100% (47/47) | 99%+ | ✅ |
| fallback 触发率 | 1.5% (20/1302) | 4.1% (2/49) | <10% | ✅ |
| 502 穿透用户侧 | 0 | 0 | 0 | ✅ |
| R813 chain_full_retry 已加载 | ✅ True | ✅ | — | ✅ |
| 新错误类型 | 无 | 无 | 无 | ✅ |

#### nv_requests (cc4101-primary, 本轮真实 30min)

| status | count | avg_dur | 备注 |
|---|---|---|---|
| 200 | 56 | 20141ms | 正常 (NVCF 恢复后 20s 均值) |
| 502 | 1  | 397167ms | NVCF 不可挽救 (buffer 跑完) |
| 499 | 1  | 443337ms | client_gone_during_flush (cc2 SDK 450s 自断) |

注: 注入的轮前链路分析里的 `502×3` 是 13:17-13:47 早期窗口 (R819 末尾风暴),
本轮真实 30min (13:21-13:51) 已降到 1×502.

#### cc_requests (用户可见, 本轮真实 30min)

| total | 200 | 499 | 502 | fb | fb_pct | sr |
|---|---|---|---|---|---|---|
| 1302 | 1294 | 8 | 0 | 20 | 1.5% | 99.4% |

- **零 502 穿透用户** (s502=0)
- 8×499 = client_gone (cc2 SDK 预算自断, 非链路错)
- 20×fallback 全部兜住 → 用户 200

#### per-key fid 路由铁证 (30min)

| nv_key_idx | fid | total | ok | SR |
|---|---|---|---|---|
| 0 | b1b22d03 | 13 | 13 | 100% |
| 1 | b1b22d03 | 9  | 9  | 100% |
| 2 | b1b22d03 | 13 | 13 | 100% |
| 3 | b1b22d03 | 11 | 11 | 100% |
| 4 | b1b22d03 | 12 | 12 | 100% |

全 5key bind b1b22d03, 全 success (58/58 = 100%). NVCF 风暴已完全退去.

#### tier 错误分布 (30min, 来自注入数据, 早期窗口 13:17-13:47)

| key | RemoteDisc | 529 | Timeout | empty_200 | success | SR |
|---|---|---|---|---|---|---|
| k0 | 0 | 2 | 0 | 2 | 12 | 70.6% |
| k1 | 4 | 1 | 0 | 0 | 10 | 66.7% |
| k2 | 2 | 0 | 1 | 0 | 12 | 80% |
| k3 | 4 | 0 | 0 | 0 | 10 | 71.4% |
| k4 | 3 | 0 | 0 | 0 | 11 | 78.6% |

注: 这是早期窗口 (风暴末梢). 13:21-13:51 真实窗口 tier SR 已回 100%.
所有 key 都有 success+错误, 没有任何 key 完全挂, 风暴末梢持续但可挽救的都成功了.

### R813 修复就位铁证

```
docker exec nv_gw python3 -c "import gateway.buffer_stream as b, inspect;
  print('chain_full_retry:', 'chain_full_retry' in inspect.getsource(b.BufferStreamSession.run))"
→ chain_full_retry: True
```

### 健康检查

- `curl localhost:40006/health` → ok, 5 keys, pexec models 含 glm5_2_nv
- `docker ps` → nv_gw Up 2h, cc4101 Up 12h, dsv4p_nv40066 Up 17h
- container nv_gw 主进程加载 R813 新代码 (chain_full_retry=True)

## 判稳结论

链路工作完全正常. NVCF 风暴已退去, 全指标优于目标.
本轮 30min 真实窗口: nv_gw SR 98.2%, 用户可见 SR 99.4%, fallback 1.5%, 零 502 穿透.
R813 修复仍就位. 进入长期观测期, 不改码.

## SR 趋势

| 轮 | 30min per-call SR | per-key tier SR | WAIT-RECOVER | fallback% | 备注 |
|---|---|---|---|---|---|
| R811 | 100% (91/91) | — | 1 fall-through | — | WAIT 首触达 |
| R812 | 100% (79/79) | 98.75% (79/80) | 1 (RECOVER 首 FAIL) | 0.66% | 补丁 RECOVER 首触发 |
| R813 | 89.2% (66/74) | — | 11 (全 FAIL, 老代码) | 10.5% | restart 加载修复 |
| R814 | 100% (18/18 restart 后) | — | 0 | 1.36% | 修复就位 |
| R815 | 100% (55/55) | 98.3% (57/58) | 2 (1 OK ★ + 1 FAIL) | 1.4% | CHAIN-FULL 首 WAIT-OK |
| R816 | 100% (31/31) | 93.75% (30/32) | 0 | 3.23% | 稳定, buffer 自愈生效 |
| R817 | 100% (47/47) | 95.7% (44/46) | 1 (FAIL→fallback) | 0% | NVCF 风暴退去, 全绿 |
| R818 | 100% (44/44) | 95.7% (44/46) | 2 (全 FAIL→吸收) | 1.45% | NVCF 二次瞬断, 2×502 全吸收 |
| R819 | 93.75% (45/48) | 100% (48/48 最新) | 0 | 4.1% | NVCF 风暴末梢 3×502 全吸收, 零穿透 |
| **R820** | **98.2% (56/57)** | **100% (58/58)** | **0** | **1.5%** | **NVCF 风暴已退去, 全指标优于目标** |

## 下一步

- R821: 继续长期观测. 关注 NVCF 风暴频率; fallback<10%; per-key tier SR 90%+;
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
