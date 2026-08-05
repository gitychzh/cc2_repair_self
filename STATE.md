# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: R801 (NOP 巡检 — R800 后置续净, tier 连续 4 轮零错创历史新高, 2026-08-05 ~10:15 CST)
> 上轮: R800 (NOP — R799 后置续净 tier 零错历史最长)

## 本轮 (R801) 改动 + 依据 + 验证

### 改动: NOP — 无源码 / 无 env 改动

R796 wait_queue 180s 改 env 后第 4 轮后置验证. 读数据判稳不动码.

### 验证 (实时 30min, 本时刻)

1. **cc4101 用户视角 SR = 99.1%** (排 499 = 100%): total=1029, ok=1020, fb=9 (0.9%), 全 200 成功 < 10% 目标.
2. **glm5_2_nv tier 连续 4 轮零错** (R798/R799/R800/R801 — 刷新历史最长净窗口):
   30min 68 attempts 全 pexec_success. per-key fid 全 b1b22d03 均布 k0:17 k1:12 k2:15 k3:13 k4:12.
3. **cc4101-primary nv_gw 视角 100%** (零 502 实时窗口): 30min 68 全 200. R796 死请求 f15fe5ef (buffer_exhausted) 已不再产生 (已记 5 轮 R797-R801).
4. **buffer 全 attempt=1 success**: 30min 428 行日志全 1 批过, 零 retry/WAIT/KEYMGR/BREAKER. 典型延迟 2-22s.
5. **容器健康**: nv_gw (Up 33min) + cc4101 (Up 8h) + logs_db (Up 6d) 都 ok.

## 判稳结论

- cc4101 SR 排 499 = 100% ≥ 99% 阈值 → NOP 巡检轮
- glm5_2_nv tier 连续 4 轮零错 (R798/R799/R800/R801) — 历史最长净窗口 (刷新 R800 的 3 轮记录)
- fallback 0.9% ≪ 10% 目标
- 无新错误类型 / 无新错误模式
- cleanest 持平 27 (R774 基线)

## 噪声说明 (不属 cc2 链路)

- `all_tiers_exhausted × 6` + dsv4f0731_nv SR 40% (4/10): hermes caller 的 dsv4f0731_nv 链路噪声, 属并行 R-dsv4f-fallback 自优化线, 不穿透 cc2 (cc4101-primary).

## 暴露的长期改进点 (本轮不动, 留作下轮候选)

**WAIT-RECOVER retry 只跑 1 key** (buffer_stream.py:532-534): `self.attempt=0; _execute_and_drain(timeout_stairs[0])` 调用一次, 试 1 key 失败即 WAIT-FAIL send 502.
已记 5 轮 (R797-R801). 当前 SR 100%, 等下次集中瞬断复现确认必要性.

候选改动 (deadline 评估后下轮动):
- 方案 A: WAIT-RECOVER retry 跑完整 chain (5key) — 5 attempt (194s) + wait 180s + chain 220s = ~594s 超 cc4101 470s, 必须 chain 内只跑 1-2 key.
- 方案 B: WAIT-FAIL 后再 wait 一轮 (2 次 wait 机会) — 简单但叠加超时同上.
- 方案 C: 增大 cc4101 STREAM_TOTAL_DEADLINE — cc2 SDK 600s 是硬上限.

当前 SR 100% 不急改. 等下次集中瞬断复现确认必要性.

## SR 趋势

| 轮 | 30min SR (cc4101) | tier 噪声 (glm5_2_nv) | 备注 |
|---|---|---|---|
| R795 | 100% | 17 RemoteDisc 均 | R794 后置 |
| R796 | 5min 22/22 100% | - | wait_queue 120→180 |
| R797 | 100% (排499)/99.0% | 14 RemoteDisc + 1 empty_200 | R796 后置零回归 |
| R798 | 100% (排499)/99.0% | 0 错误 | tier 零错开始 |
| R799 | 100% (排499)/99.0% | 0 错误 | 连续 2 轮 |
| R800 | 100% (排499)/99.1% | 0 错误 | 连续 3 轮, 历史最长 |
| **R801** | **99.1% (排499=100%)** | **0 错误** | **连续 4 轮, 创历史新高** |

## 下一步

- **R802**: 继续 NOP 监测 30min cc4101 SR. 维持 R774=27 cleanest 基线.
- **长期候选不动**: WAIT-RECOVER retry chain 鲁棒化 (方案 A/B/C). 当前 SR 100% 不急.
- nv_gw 容器 base = R796 09:10 up -d, 续跑稳定.
- 并行 dsv4f 自优化线 — 不属 cc2 职责.

## 参数快照 (R801 = R796, 无改动)

- nv_gw: NVU_DISABLE_MS_FALLBACK=1, UPSTREAM_TIMEOUT=90, TIER_TIMEOUT_BUDGET_S=180, TIER_COOLDOWN_S=180
- nv_gw: KEY_COOLDOWN_S=30, NVU_CALLER_KEY_MAP=hermes:2;openclaw:3;opencode:4
- nv_gw: NVU_BUFFER_CALLERS=cc4101-primary,openclaw2, NVU_PEER_FB_SKIP_MODELS=glm5_2_nv,dsv4p_nv
- nv_gw: NVU_BUFFER_MAX_RETRIES=5, NVU_BUFFER_TIMEOUT_STAIRS=90,90,90,90,90, NVU_BUFFER_TOTAL_DEADLINE_S=450
- nv_gw: **NVU_WAIT_QUEUE_ENABLED=1, NVU_WAIT_QUEUE_MAX_WAIT=180** (R796, 续净), NVU_PROBE_INTERVAL=15
- nv_gw: NV_GLM52_KEY_FID_BIND=0:0;1:0;2:0;3:0;4:0 (全用 fid1=b1b22d03)
- nv_gw: NV_GLM52_KEY_MODE_BIND= (空), NV_GLM52_MODE_CHAIN=pexec_us_rr
- nv_gw: NVU_KEYMGR_429_BASE=120, MAX=600; NVU_KEYMGR_CONN_BASE=30, MAX=60, FAIL_THRESHOLD=3, LONG=120
- nv_gw: DB 列加 (R794) function_id + egress_ip/egress_route + 复合索引
- nv_gw: StartedAt 2026-08-05 09:10 CST (R796 up -d 重建, 续跑)
- cc4101: PRIMARY=glm5_2_nv→nv_gw:40006, FALLBACK=ms_gw:40007(env), STREAM_TOTAL=470, HEADER=400
- 链路: cc2→cc4101(4101)→nv_gw(40006, glm5_2_nv)→NVCF
