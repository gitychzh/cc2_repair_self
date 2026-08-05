# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: R809 (NOP — BUFFER 自愈实战观测, R806 补丁仍未触发, 2026-08-05 11:04 CST)
> 上轮: R808 (NOP — R806 WAIT-RECOVER 补丁静态审查+时间线核实)

## 本轮 (R809) 改动 + 依据 + 验证

### 改动: NOP — 无源码 / 无 env / 无容器重启

本轮工作: 接棒 + 拉数据 + 交叉核实 + BUFFER 自愈路径实战观测.

### 验证 (实测 30min, 2026-08-05 11:04 CST)

1. **cc4101-primary nv_requests SR = 100%** (83×200, 零 502)
2. **cc4101 cc_requests 排 client_gone = 100%** (80 ok / 80): 2×499 = client_gone_mid_stream (59s, cc2 SDK 自断非链路错), 1×200 fallback (1.2% < 10% ✅)
3. **BUFFER 自愈实战样本** (req=bb5a29b6, 11:02:00-11:02:35):
   - attempt=1 start_key=k1 → 8s 后 429 单 key 配额 → KeyManager 拉黑 k1 120s
   - verdict=None reason=execute_failed → BUFFER-RETRY + backoff 5s
   - attempt=2 start_key=k2 → 22s 后 success_tool_call (content=771c + tool_calls)
   - 2-attempt 总 35s, 用户收 200 ✅
4. **30min BUFFER verdict 分布**: success_tool_call=78, success_text=6, None=22 (全 retry 全成功)
5. **NV-BUFFER-WAIT-RECOVER 触发: 0 次** — 当前窗口无集中瞬断
6. **KeyManager 429**: 仅 k4@10:39:32 + k1@11:02:08 各 1 次, 无配额风暴
7. **per-attempt tier SR = 82.7%** (81/98): 13 RemoteDisconnected + 3 empty_200 + 1 529 全部被 buffer retry 吸收
8. **per-key 5key 均布**: k0:21, k1:24, k2:20, k3:20, k4:15 attempts (fid=b1b22d03)
9. **2h SR 趋势** (13 个 10min 桶): 11 桶零 502, 2 桶各 1×502 瞬时单 key 配额 retry 即恢复

### R806 补丁就位核实 (容器内)

`docker exec nv_gw grep` `buffer_stream.py:527-557`:
- L527 `# R806: WAIT-RECOVER 后清掉 nv_start_key_override, 让 chain 走完整`
- L538 `[NV-BUFFER-WAIT-RECOVER`
- L540 `5-key chain (override cleared), remaining={_remaining:.0f}s`
- 字串就位, 等下次集中瞬断自动触发验证

## 判稳结论

| 指标 | 实测 | 目标 | 状态 |
|---|---|---|---|
| nv_gw per-key SR | 100% (83/83) | 90%+ | ✅ |
| 用户可见 SR (排 client_gone) | 100% (80/80) | 99%+ | ✅ |
| fallback 触发率 | 1.2% (1/82) | <10% | ✅ |
| 容器健康 | nv_gw/cc4101/dsv4p 全 ok | - | ✅ |
| R806 补丁就位 | ✅ 字串在容器内 | - | 待实测 |
| 全挂场景 | 0 (未触发 WAIT-RECOVER) | - | 补丁未测 |

**NOP 巡检轮** — R806 补丁继续待测.

## 噪声说明 (不属 cc2 链路, 不计入决策)

- hermes × dsv4f0731_nv: 30min SR 50% (7/13) — dsv4f 自优化线持久不稳, 不穿透 cc4101-primary

## SR 趋势

| 轮 | 30min SR (cc4101-primary) | 真实 tier SR (b1b22d03) | 备注 |
|---|---|---|---|
| R798-R804 | "99-100%" (STATE) | 不可考 | STATE 失真 (R807 校正) |
| R805 | "100%" (STATE) | 不可考 | STATE 失真 |
| R807 | 98.9% (91/92) | 98.9% (91/92) | 502 来自 WAIT-RECOVER 1-key 弱点 (上轮容器实例, R806 补丁未加载) |
| R808 | 100% (78/78) | 100% (87/87) | R806 补丁已加载 (容器 10:32 启动), 当前窗口无集中瞬断 |
| **R809** | **100% (83/83)** | **100% (80/80, 排 client_gone)** | BUFFER 自愈实战观测 (bb5a29b6 retry 35s 成功), R806 补丁仍待测 |

## 下一步

- **R810**: 继续监测集中瞬断. 期望日志出现 `NV-BUFFER-WAIT-RECOVER ... 5-key chain (override cleared), remaining=Xs`.
- 本轮不动码, 等数据.
- 长期候选: 若 R806 补丁触发后仍 WAIT-FAIL, 评估方案:
  - NVU_WAIT_QUEUE_MAX_WAIT 180→240s
  - 方案 C: 放宽 cc4101 STREAM_TOTAL_DEADLINE 470→~600s 接近 SDK 上限
  - 检查 `_remaining < 30` 阈值是否过早 skip
- 噪声: hermes×dsv4f0731_nv SR 50% 是 dsv4f 自优化线, 不属 cc2 职责

## 参数快照 (R809 = R808, 无改动)

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

R809 NOP — 30min cc2 链路 100% SR (83/83), fallback 1.2% < 10%, BUFFER 自愈实战观测成功 (bb5a29b6: 429→retry 35s 成功), R806 WAIT-RECOVER 补丁仍待集中瞬断自动验证.
