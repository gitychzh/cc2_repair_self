# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: R810 (NOP — BUFFER 3-attempt 自愈实战观测 req=4892ea40, R806 补丁仍 0 触发, 2026-08-05 11:11 CST)
> 上轮: R809 (NOP — BUFFER 自愈实战观测 req=bb5a29b6 2-attempt 35s 成功)

## 本轮 (R810) 改动 + 依据 + 验证

### 改动: NOP — 无源码 / 无 env / 无容器重启

本轮工作: 接棒 + 拉数据 + 交叉核实 + BUFFER 3-attempt 自愈实战观测.

### 验证 (实测 30min, 2026-08-05 11:10 CST)

1. **cc4101-primary nv_requests SR = 100%** (88×200, 零 502)
2. **cc4101 cc_requests SR = 100%** (88/88 全 200, 排 0 client_gone)
3. **fallback 触发率 = 1.0%** (f|98 → fb=1, 1 次 fallback < 10% ✅)
4. **BUFFER 3-attempt 自愈实战样本** (req=4892ea40, 11:09:47-11:11:29):
   - attempt=1 k3 RemoteDisconnected → KeyManager 拉黑 k3 5s (短惩罚不累计 conn_count)
   - verdict=None reason=execute_failed → BUFFER-RETRY + backoff 5s
   - attempt=2 k4 SSLEOFError → KeyManager 拉黑 k4 10s
   - verdict=None → BUFFER-RETRY + backoff 10s
   - attempt=3 → 102.7s 后 success_tool_call (tool_calls 完成)
   - 3-attempt 总 102.7s (远 < buffer 450s 总预算), 用户收 200 ✅
5. **30min NV-BUFFER-WAIT-RECOVER 触发: 0 次** (docker logs grep -c=0) — 当前窗口无集中瞬断
6. **per-attempt tier SR = 83.0%** (88/106): 11 RemoteDisconnected + 5 empty_200 + 1 529_overloaded + 1 NVCFPexecTimeout 全部被 buffer retry 吸收
7. **per-key 5key 均布**: k0:22, k1:23, k2:20, k3:23, k4:18 attempts (fid=b1b22d03)
8. **all_tiers_exhausted × 6** 是 buffer attempt 级 all_keys_exhausted tag (5key 全挂瞬间), 已在 3-attempt 内吸收, 不= WAIT-RECOVER 触发
9. **30min 其他成功样本**: 196eacf4 (1-attempt success_text 5s), 43dc9447 (1-attempt success_tool_call 22s), ea227571 (1-attempt success_tool_call 31s, 40603b)

### R806 补丁就位核实 (容器内)

- `docker logs nv_gw --since 30m | grep -c "NV-BUFFER-WAIT-RECOVER"` = **0**
- 补丁字串仍在容器内 `buffer_stream.py:527-557` (R808 已静态审查)
- 等下次集中瞬断自动触发验证

## 判稳结论

| 指标 | 实测 | 目标 | 状态 |
|---|---|---|---|
| nv_gw per-key SR | 100% (88/88) | 90%+ | ✅ |
| 用户可见 SR | 100% (88/88) | 99%+ | ✅ |
| fallback 触发率 | 1.0% (1/98) | <10% | ✅ |
| 容器健康 | nv_gw/cc4101/dsv4p 全 ok | - | ✅ |
| R806 补丁就位 | ✅ 字串在容器内 | - | 待实测 |
| 全挂场景 (WAIT-RECOVER) | 0 (未触发) | - | 补丁未测 |

**NOP 巡检轮** — R806 补丁继续待测.

## 噪声说明 (不属 cc2 链路, 不计入决策)

- hermes × dsv4f0731_nv: 30min SR 30% (3/10, 7×502) — dsv4f 自优化线持续不稳 (R1029-R1030 RemoteDisconnected storm), 不穿透 cc4101-primary
- `all_tiers_exhausted × 6` 是 buffer attempt 级 tag (5key 全挂瞬间), 3-attempt 内被吸收, 不触发 WAIT-RECOVER

## SR 趋势

| 轮 | 30min SR (cc4101-primary) | per-attempt tier SR | 备注 |
|---|---|---|---|
| R807 | 98.9% (91/92) | 98.9% | WAIT-RECOVER 1-key 弱点 (上轮容器实例, R806 补丁未加载) |
| R808 | 100% (78/78) | 100% (87/87) | R806 补丁已加载, 当前窗口无集中瞬断 |
| R809 | 100% (83/83) | 82.7% (81/98) | BUFFER 自愈实战 (bb5a29b6 2-attempt 35s) |
| **R810** | **100% (88/88)** | **83.0% (88/106)** | BUFFER 3-attempt 自愈实战 (4892ea40 102.7s) |

注: per-attempt tier SR 持续 ~82-83% 反映 NVCF 单 key 配额/transport 噪声, 由 buffer retry 性能吸收为 100% 用户可见.

## 下一步

- **R811**: 继续监测集中瞬断. 期望日志出现 `NV-BUFFER-WAIT-RECOVER ... 5-key chain (override cleared), remaining=Xs`.
- 本轮不动码, 等数据.
- 长期候选 (R806 补丁触发后仍 WAIT-FAIL 时评估):
  - NVU_WAIT_QUEUE_MAX_WAIT 180→240s
  - 方案 C: 放宽 cc4101 STREAM_TOTAL_DEADLINE 470→~600s 接近 SDK 上限
  - 检查 `_remaining < 30` 阈值是否过早 skip
- 噪声: hermes×dsv4f0731_nv SR 30% 是 dsv4f 自优化线, 不属 cc2 职责

## 参数快照 (R810 = R809, 无改动)

- nv_gw StartedAt: 2026-08-05 10:32:28 CST (R806 补丁已加载)
- nv_gw: NVU_DISABLE_MS_FALLBACK=1, UPSTREAM_TIMEOUT=90, TIER_TIMEOUT_BUDGET_S=180, TIER_COOLDOWN_S=180
- nv_gw: KEY_COOLDOWN_S=30, NVU_CALLER_KEY_MAP=hermes:2;openclaw:3;opencode:4
- nv_gw: NVU_BUFFER_CALLERS=cc4101-primary,openclaw2, NVU_PEER_FB_SKIP_MODELS=glm5_2_nv,dsv4p_nv
- nv_gw: NVU_BUFFER_MAX_RETRIES=5, NVU_BUFFER_TIMEOUT_STAIRS=90,90,90,90,90, NVU_BUFFER_TOTAL_DEADLINE_S=450
- nv_gw: NVU_WAIT_QUEUE_ENABLED=1, NVU_WAIT_QUEUE_MAX_WAIT=180 (R796), NVU_PROBE_INTERVAL=15
- nv_gw: NV_GLM52_KEY_FID_BIND=0:0;1:0;2:0;3:0;4:0 (实测 cc2 实际走 fid=b1b22d03)
- nv_gw: NV_GLM52_KEY_MODE_BIND= (空), NV_GLM52_MODE_CHAIN=pexec_us_rr
- nv_gw: NVU_KEYMGR_429_BASE=120, MAX=600; NVU_KEYMGR_CONN_BASE=30, MAX=60, FAIL_THRESHOLD=3
- cc4101: PRIMARY_UPSTREAM_MODEL=glm5_2_nv, PRIMARY_UPSTREAM_URL=http://nv_gw:40006/v1/messages
- cc4101: FALLBACK_UPSTREAM_MODEL=glm5_2_ms, FALLBACK_UPSTREAM_URL=http://ms_gw:40007/v1/messages
- cc4101: CC4101_STREAM_TOTAL_DEADLINE_S=470, PRIMARY_HEADER_TIMEOUT=400, UPSTREAM_TIMEOUT=130
- settings.json: contextWindow=170000, autoCompactWindow=155000, API_TIMEOUT_MS=600000

## 一句话总结

R810 NOP — 30min cc2 链路 100% SR (88/88), fallback 1.0% < 10%, BUFFER 3-attempt 自愈实战观测成功 (req=4892ea40: k3 RemoteDisconnected→k4 SSLEOFError→attempt 3 success_tool_call 102.7s). R806 WAIT-RECOVER 补丁仍在 buffer_stream.py:538 就位, 30min 0 触发 (无集中瞬断). per-attempt tier SR 83.0% (88/106) 被 buffer retry 完全吸收为 100% 用户可见.
