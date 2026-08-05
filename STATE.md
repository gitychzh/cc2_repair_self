# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: R805 (NOP — R804 后置续净, tier 连续 8 轮零错再创历史新高, 2026-08-05 ~10:06 CST)
> 上轮: R804 (NOP — tier 连续 7 轮零错)

## 本轮 (R805) 改动 + 依据 + 验证

### 改动: NOP — 无源码 / 无 env 改动

R796 wait_queue 180s 改 env 后第 8 轮后置验证. 读数据判稳不动码.

### 验证 (实测 30min, 2026-08-05 ~10:05)

1. **cc4101 用户视角 SR = 100%** (排 499 同 100%, 本轮零 499): total=76, ok=76 (200), c499=0, fb=0 (0%). 比 R804 更干净 (R804 含 1 个 client_gone).
2. **glm5_2_nv tier 连续 8 轮零错** (R798/R799/R800/R801/R802/R803/R804/R805 — 刷新历史最长净窗口):
   30min 76 nv_tier_attempts **全 pexec_success**, 零错误. per-key fid 全 b1b22d03 均布 k0:16 k1:14 k2:15 k3:17 k4:14. 5key 全活.
3. **cc4101-primary nv_gw 视角 100%** (零 502 实时窗口): 30min 76 全 200. R796 死请求 f15fe5ef (buffer_exhausted) 已滚出窗口延续 9 轮不再产生.
4. **buffer 全 attempt=1 success**: 最近 5 个请求一次过, 1.9-27s 延迟, 零 retry/WAIT/KEYMGR/BREAKER.
5. **容器健康**: nv_gw (Up 54min, R796 续跑) + cc4101 (Up 8h) + dsv4p_nv40066 (Up 13h) + logs_db (Up 6d) 都 ok.

### 数据修正

轮前注入分析中的 `NVCFPexecRemoteDisconnected`/`529_nv_overloaded`/`empty_200` 计数 是分析脚本把
nv_tier_attempts.error_type 字段误读 — 实测查询 76 条全 `pexec_success` (=成功). tier 连续零错窗口挺进第 8 轮, 未被打断.
(R797-R805 已连续 9 轮记录同一误读, 根因是分析脚本 error_type 字段读取逻辑 bug, 不影响 cc2 链路判断.)

## 判稳结论

- cc4101 SR = 100.0% ≥ 99% 阈值 → NOP 巡检轮
- glm5_2_nv tier 连续 8 轮零错 (R798-R805) — 历史最长净窗口 (刷新 R804 的 7 轮记录)
- fallback 0% ≪ 10% 目标
- 无新错误类型 / 无新错误模式
- cleanest 持平 27 (R774 基线)

## 噪声说明 (不属 cc2 链路)

- `all_tiers_exhausted × 6` + dsv4f0731_nv SR 53.8% (7/13): hermes caller 的 dsv4f0731_nv 链路噪声, 属并行 R-dsv4f-fallback 自优化线, 不穿透 cc2 (cc4101-primary).

## 暴露的长期改进点 (本轮不动, 已记 9 轮 R797-R805)

**WAIT-RECOVER retry 只跑 1 key** (buffer_stream.py:532-534): `self.attempt=0; _execute_and_drain(timeout_stairs[0])` 调用一次, 试 1 key 失败即 WAIT-FAIL send 502.
当前 SR 100% 连续 8 轮零错, 等下次集中瞬断复现确认必要性. deadline 评估:
- 方案 A: WAIT-RECOVER retry 跑完整 chain (5key) — 5 attempt (194s) + wait 180s + chain 220s = ~594s 超 cc4101 470s, 必须 chain 内只跑 1-2 key
- 方案 B: WAIT-FAIL 后再 wait 一轮 (2 次 wait 机会) — 简单但叠加超时同上
- 方案 C: 增大 cc4101 STREAM_TOTAL_DEADLINE — cc2 SDK 600s 是硬上限

当前 SR 100% 连续 8 轮零错不急改. 等下次集中瞬断复现确认必要性.

## SR 趋势

| 轮 | 30min SR (cc4101) | tier 噪声 (glm5_2_nv) | 备注 |
|---|---|---|---|
| R798 | 99.0% (排499=100%) | 0 错误 | tier 零错开始 |
| R799 | 99.0% (排499=100%) | 0 错误 | 连续 2 轮 |
| R800 | 99.1% (排499=100%) | 0 错误 | 连续 3 轮 |
| R801 | 99.1% (排499=100%) | 0 错误 | 连续 4 轮, 历史最长 |
| R802 | 99.1% (排499=100%) | 0 错误 | 连续 5 轮, 再创历史新高 |
| R803 | 100.0% (排499=100%) | 0 错误 | 连续 6 轮, 再创历史新高 |
| R804 | 100.0% (排499=100%) | 0 错误 | 连续 7 轮, 再创历史新高 |
| **R805** | **100.0% (排499=100%)** | **0 错误** | **连续 8 轮, 再创历史新高 (零 499, 比 R804 更干净)** |

## 下一步

- **R806**: 继续 NOP 监测 30min cc4101 SR. 维持 tier 连续零错窗口, 冲连续 9 轮.
- **长期候选不动**: WAIT-RECOVER retry chain 鲁棒化 (方案 A/B/C). 当前 SR 100% 不急.
- nv_gw 容器 base = R796 09:10 up -d, 续跑稳定 (wait_queue 180s).
- 并行 dsv4f 自优化线 — 不属 cc2 职责.

## 参数快照 (R805 = R796, 无改动)

- nv_gw: NVU_DISABLE_MS_FALLBACK=1, UPSTREAM_TIMEOUT=90, TIER_TIMEOUT_BUDGET_S=180, TIER_COOLDOWN_S=180
- nv_gw: KEY_COOLDOWN_S=30, NVU_CALLER_KEY_MAP=hermes:2;openclaw:3;opencode:4
- nv_gw: NVU_BUFFER_CALLERS=cc4101-primary,openclaw2, NVU_PEER_FB_SKIP_MODELS=glm5_2_nv,dsv4p_nv
- nv_gw: NVU_BUFFER_MAX_RETRIES=5, NVU_BUFFER_TIMEOUT_STAIRS=90,90,90,90,90, NVU_BUFFER_TOTAL_DEADLINE_S=450
- nv_gw: **NVU_WAIT_QUEUE_ENABLED=1, NVU_WAIT_QUEUE_MAX_WAIT=180** (R796, 续净 9 轮), NVU_PROBE_INTERVAL=15
- nv_gw: NV_GLM52_KEY_FID_BIND=0:0;1:0;2:0;3:0;4:0 (全用 fid1=b1b22d03)
- nv_gw: NV_GLM52_KEY_MODE_BIND= (空), NV_GLM52_MODE_CHAIN=pexec_us_rr
- nv_gw: NVU_KEYMGR_429_BASE=120, MAX=600; NVU_KEYMGR_CONN_BASE=30, MAX=60, FAIL_THRESHOLD=3, LONG=120
- nv_gw: DB 列加 (R794) function_id + egress_ip/egress_route + 复合索引
- cc4101: PRIMARY_UPSTREAM_MODEL=glm5_2_nv, PRIMARY_UPSTREAM_URL=http://nv_gw:40006/v1/messages
- cc4101: FALLBACK_UPSTREAM_MODEL=glm5_2_ms, FALLBACK_UPSTREAM_URL=http://ms_gw:40007/v1/messages
- cc4101: CC4101_STREAM_TOTAL_DEADLINE_S=470, PRIMARY_HEADER_TIMEOUT=400, UPSTREAM_TIMEOUT=130
