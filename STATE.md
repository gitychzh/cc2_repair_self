# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: R812 (NOP — R806 WAIT-RECOVER 补丁首次 RECOVER 分支实战触发, 2026-08-05 11:27 CST)
> 上轮: R811 (NOP — R806 补丁首次触达 fall-through 路径 11:21)

## 本轮 (R812) 改动 + 依据 + 验证

### 改动: NOP — 无源码 / 无 env / 无容器重启

### 验证 (实测 30min, 2026-08-05 11:27 CST)

1. **cc4101-primary nv_requests SR = 98.75%** (79×200, 1×502 all_tiers_exhausted)
2. **cc4101 cc_requests 用户可见 SR = 100%** (1209/1209 排 499, 9×499 client_gone SDK 59s 自断)
3. **fallback = 0.66%** (8/1218 < 10% ✅)
4. **per-attempt tier SR = 78.2%** (79/101) — 22 错误被 buffer retry + cc4101 fallback 完全吸收
5. **R806 补丁首次 RECOVER 分支实战触发** (本轮最大收获):
   - req=c4d6dd8e (11:23:01-11:25:43):
     - 5-attempt 全挂 (k2/k3/k4/k5 SSLEOFError/k1) elapsed=413s
     - NV-BUFFER-WAIT 180s 等 ProbeWorker 探恢复
     - 20s 后 key 恢复 → **NV-BUFFER-WAIT-RECOVER** "retrying NVCF with full 5-key chain (override cleared), remaining=289s"
     - 补丁逻辑生效: pop nv_start_key_override + attempt=0 + 走完整 5key RR
     - retry 后 1.5s execute_failed (刚恢复的 key 仍在抖) → WAIT-FAIL → 502
     - cc4101 dsv4p fallback 兜住 → 用户 200
   - req=709a064c (11:15:29, R811 已记 fall-through)
6. **buffer retry 自愈样本**: 7f54243f 1-attempt 18s, 7c83ef62 2-attempt 42s, 781cf641 2-attempt 53s
7. **KeyManager 短惩罚**: 14×RemoteDisc + 5×empty_200 + 2×Timeout + 1×529 全 retry 全成功
8. **R814 tier-degraded 短路面就位**, 本轮无 DEGRADED 触发 (tier SR 78.2% 错误是 R-bugfix 的 RemoteDisc/empty_200 不是新错误形态)

## 判稳结论

| 指标 | 实测 | 目标 | 状态 |
|---|---|---|---|
| nv_gw per-key SR | 98.75% (79/80) | 90%+ | ✅ |
| 用户可见 SR (排 499) | 100% (1209/1209) | 99%+ | ✅ |
| fallback 触发率 | 0.66% (8/1218) | <10% | ✅ |
| R806 补丁就位 | ✅ buffer_stream.py:527-557 | - | ✅ |
| R806 补丁触发 | RECOVER×1 + fall-through×1 (RECOVER 首次!) | - | ✅ |

**NOP 巡检轮** — R806 补丁 RECOVER 分支首次实战触发, 逻辑正确 (pop override+attempt=0+完整 chain retry), 待"多 key 稳定恢复"场景才会真正挽救 req.

## SR 趋势

| 轮 | 30min SR (cc4101-primary) | per-attempt tier SR | 备注 |
|---|---|---|---|
| R810 | 100% (88/88) | 83.0% (88/106) | BUFFER 3-attempt 自愈 |
| R811 | 100% (91/91) | 100% (95/95) | R806 WAIT fall-through |
| **R812** | **98.75% (79/80)** | **78.2% (79/101)** | **R806 WAIT-RECOVER 首次触发** |

## 噪声 (不属 cc2 链路)

- hermes × dsv4f0731_nv: 30min SR 36.4% (4/11, 7×502) — dsv4f 自优化线, 不穿透 cc2

## 下一步

- **R813**: 继续监测 R806 补丁 RECOVER 分支:
  1. ✅ 已观测: WAIT-RECOVER 触发但 retry 立即失败 (单 key 恢复不稳) → WAIT-FAIL → 502 → fallback 兜住
  2. ⏳ 待观测: WAIT-RECOVER 触发且 retry 成功 → 用户 200 (无需 fallback) — 真正的补丁成功路径
- 长期候选 (若 WAIT-RECOVER retry 成功率持续低):
  - 在 RECOVER retry 失败后, 给一次额外的 WAIT (而非直接 FAIL) — 等"多 key 稳定恢复"
  - ProbeWorker probe 间隔 15s 是否太短 (刚 probe 通但实际不稳)
  - NVU_WAIT_QUEUE_MAX_WAIT 180→240s

## 参数快照 (R812 = R811, 无改动)

- nv_gw StartedAt: 2026-08-05 10:32:28 CST (R806 补丁 + R814 tier-degraded 已加载)
- nv_gw: NVU_DISABLE_MS_FALLBACK=1, UPSTREAM_TIMEOUT=90, TIER_TIMEOUT_BUDGET_S=180, TIER_COOLDOWN_S=180
- nv_gw: KEY_COOLDOWN_S=30, NVU_CALLER_KEY_MAP=hermes:2;openclaw:3;opencode:4
- nv_gw: NVU_BUFFER_CALLERS=cc4101-primary,openclaw2, NVU_PEER_FB_SKIP_MODELS=glm5_2_nv,dsv4p_nv
- nv_gw: NVU_BUFFER_MAX_RETRIES=5, NVU_BUFFER_TIMEOUT_STAIRS=90×5, NVU_BUFFER_TOTAL_DEADLINE_S=450
- nv_gw: NVU_WAIT_QUEUE_ENABLED=1, NVU_WAIT_QUEUE_MAX_WAIT=180, NVU_PROBE_INTERVAL=15
- nv_gw: NVU_KEYMGR_429_BASE=120 MAX=600, NVU_KEYMGR_CONN_BASE=30 MAX=60 FAIL_THRESHOLD=3
- cc4101: PRIMARY=glm5_2_nv @ nv_gw:40006, FALLBACK=glm5_2_ms @ ms_gw:40007
- cc4101: CC4101_STREAM_TOTAL_DEADLINE_S=470, PRIMARY_HEADER_TIMEOUT=400, UPSTREAM_TIMEOUT=130

## 一句话总结

R812 NOP — 30min 用户可见 SR=100% (1209/1209 排 499), fallback=0.66%. per-attempt tier SR 78.2% (22 错误被 buffer 完全吸收). R806 WAIT-RECOVER 补丁首次 RECOVER 分支实战触发: req=c4d6dd8e 5-attempt 全挂→WAIT 20s→ProbeWorker 探到 key 恢复→RECOVER (pop override+attempt=0+完整 5key chain retry)→retry 1.5s 立即失败 (刚恢复 key 仍在抖)→WAIT-FAIL→502→cc4101 dsv4p fallback 兜住→用户 200. 补丁逻辑正确, 等下次"多 key 稳定恢复"场景才会真正挽救 req.
