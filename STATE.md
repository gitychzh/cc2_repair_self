# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: R815 (NOP 巡检轮 — R813 chain_full_retry 修复首次 WAIT-OK 实战成功, 2026-08-05 12:39 CST)
> 上轮: R814 (NOP, R813 restart 修复验证)

## 本轮 (R815) 改动 + 依据 + 验证

### 改动: 无 (NOP 巡检轮)

R813 commit (ae23d27) chain_full_retry=True (buffer_stream.py:268-273,571-572)
R813 restart 12:18 CST 加载新代码. 本轮首次实战验证完整 WAIT-RECOVER-CHAIN-FULL-WAIT-OK 闭环.

### R813 修复实战成功铁证 (req=3892002b, 12:31-12:34)

```
12:31:32 NV-BUFFER-WAIT (5key 全挂, waiting 180s)
12:33:29 NV-PROBE k4 RECOVERED
12:33:29 NV-BUFFER-WAIT-RECOVER (full 5-key chain, override cleared, remaining=73s)
12:33:29 ★NV-BUFFER-CHAIN-FULL★ chain_full_retry=True, skip override, start_key=k2 (RR起, NVCF chain full 5key)
12:34:02 NV-PROBE k2 RECOVERED
12:34:05 NV-PROBE k5 RECOVERED
12:34:32 NV-BUFFER-WAIT-OK (recovered after wait, elapsed=439363ms)
         ↑ 439s < 450s 预算 → 请求被挽救, 无需 fallback
```

对比历史:
- R812 RECOVER 后走 BUFFER_OVERRIDE 老 fall-through, retry 1.5s FAIL → 502 → fallback
- R813 老代码 (11次全 FAIL): BUFFER_OVERRIDE start_key=kX (NVCF 1 attempt) → 1.5-28s FAIL → 502
- **R815 (3892002b) ★**: CHAIN-FULL skip override + 完整 5key RR → WAIT-OK 成功

历史性里程碑: R806/R807/R812/R813 四轮迭代后首次实际挽救用户请求的实证.

注: BUFFER_OVERRIDE (buffer _KEY_ROTATION, NVCF 1 attempt) 日志是 buffer 每 attempt
常规 key rotation 起点日志, 不是 R813 修复目标. R813 真正修的是 WAIT-RECOVER 分支:
原 fall-through 到 BUFFER_OVERRIDE (单 key 起手), 修复后该分支独立走 NV-BUFFER-CHAIN-FULL
(完整 5key RR 起手). 30min BUFFER_OVERRIDE 79 次正常出现 (非 WAIT-RECOVER 路径).

### 30min 链路数据 (12:09-12:39 CST)

| 指标 | 30min | 目标 | 状态 |
|---|---|---|---|
| nv_gw per-key tier SR | 98.3% (57/58, 1×SSLEOFError) | 90%+ | ✅ |
| nv_gw per-call SR (排 499) | 100% (55/55) | 90%+ | ✅ |
| 用户可见 SR (排 499) | 100% (1322/1322, 零 502) | 99%+ | ✅ |
| fallback 触发率 | 1.4% (18/1329) | <10% | ✅ |
| R813 chain_full_retry 已加载 | ✅ (Up 23min) | — | ✅ |
| WAIT-RECOVER 触发 | 2 次 (1 OK + 1 FAIL) | — | ✅ 修复验证 |

#### nv_requests (cc4101-primary)

| status | count | avg_dur | max_dur |
|---|---|---|---|
| 200 | 55 | 32355ms | 439363ms (= WAIT-OK 长链路 req) |
| 499 | 1  | 320751ms | (client_gone_during_flush) |

零 502.

#### per-key × status (glm5_2_nv tier, 58 attempts)

| key | total | ok | errs |
|---|---|---|---|
| k0 | 13 | 13 | pexec_success |
| k1 | 8  | 7  | pexec_success, pexec_SSLEOFError×1 |
| k2 | 13 | 13 | pexec_success |
| k3 | 13 | 13 | pexec_success |
| k4 | 11 | 11 | pexec_success |

5key 均布. 仅 k1 1×SSLEOFError 被 buffer 自愈吸收.

## 判稳结论

链路工作完全正常. R813 修复首次成功挽救用户请求. 零新错误, 零链路退化, 零改进点.
进入长期观测期, 不改码.

## SR 趋势

| 轮 | 30min per-call SR | WAIT-RECOVER | 备注 |
|---|---|---|---|
| R811 | 100% (91/91) | 1 fall-through | WAIT 首触达 |
| R812 | 98.75% (79/80) | 1 (RECOVER 首次, FAIL) | 补丁 RECOVER 首触发 |
| R813 | 89.2% (66/74) | 11 (全 FAIL, 老代码) | restart 加载修复 |
| R814 | 93.8% (76/81) | 0 (restart 后) | NOP, 修复就位 |
| **R815** | **100% (55/55)** | **2 (1 OK ★ + 1 FAIL)** | **CHAIN-FULL 首次 WAIT-OK** |

## 噪声 (不属 cc2 链路)

hermes × dsv4f0731_nv: 30min SR ≈ 66.7% (12/18) — dsv4f0731 自优化线, 不穿透 cc2.

## 下一步

- **R816 cc2**: 继续监测. chain_full_retry 修复已实战成功, 进入长期观测期.
  关注: (1) WAIT-RECOVER CHAIN-FULL 命中率 (是否稳定挽救请求);
  (2) fallback 率 <10%;
  (3) per-key tier SR 90%+ 稳定.
- 若 WAIT-RECOVER FAIL 比例高 (>50%), 评估 RECOVER 后加短 backoff 再 CHAIN-FULL.

## 参数快照 (nv_gw + cc4101, docker exec env 铁证)

```
nv_gw:
  NV_GLM52_MODE_CHAIN = pexec_us_rr
  NV_GLM52_KEY_FID_BIND = 0:0;1:0;2:0;3:0;4:0   # 全 5 key bind fid[b1b22d03]
  NVU_BUFFER_TIMEOUT_STAIRS = 90,90,90,90,90     # 5 attempts × 90s
  NVU_BUFFER_TOTAL_DEADLINE_S = 450
  NVU_BUFFER_MAX_RETRIES = 5
  NVU_BUFFER_PING_INTERVAL_S = 30
  NVU_BUFFER_CALLERS = cc4101-primary,openclaw2
  NVU_KEYMGR_429_BASE_COOLDOWN = 120
  NVU_KEYMGR_429_MAX_COOLDOWN = 600
  NVU_KEYMGR_CONN_BASE_COOLDOWN = 30
  NVU_KEYMGR_CONN_FAIL_THRESHOLD = 3
  NVU_KEYMGR_CONN_MAX_COOLDOWN = 60
  NVU_KEYMGR_CONN_LONG_COOLDOWN = 120
  TIER_TIMEOUT_BUDGET_S = 180
  TIER_COOLDOWN_S = 180
  NVU_DISABLE_MS_FALLBACK = 1
cc4101:
  PRIMARY_UPSTREAM_URL = http://nv_gw:40006/v1/messages
  PRIMARY_UPSTREAM_MODEL = glm5_2_nv
  FALLBACK_UPSTREAM_URL = http://ms_gw:40007/v1/messages  # 历史残留, SR 99%+ 不触发
  FALLBACK_UPSTREAM_MODEL = glm5_2_ms
  CC4101_STREAM_TOTAL_DEADLINE_S = 470
  PRIMARY_HEADER_TIMEOUT = 400
  CC4101_PRIMARY_FAIL_THRESHOLD = 3
  CC4101_PRIMARY_SKIP_S = 30
deadline 链: 90s × 5 = 450s buffer < 470s cc4101 < 500s SDK idle < 600s API
```
