# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: R800 (NOP 巡检 — R799 后置续净, tier 连续 3 轮零错历史最长, 2026-08-05 ~09:45 CST)
> 上轮: R799 (NOP — R798 后置续净 wait_queue 180 续跑)

## 本轮 (R800) 改动 + 依据 + 验证

### 改动: NOP — 无源码 / 无 env 改动

R796 wait_queue 180s 改 env 后第 3 轮后置验证. 读数据判稳不动码.

### 验证 (实时 30min, 本时刻)

1. **cc4101 用户视角 SR = 100%** (排 499): ok=1015, err=9 (全 client_gone_mid_stream, real_err=0).
   30min 1024 请求中 fb=9 (0.88%) 全 200 成功 < 10% 目标.
2. **glm5_2_nv tier 连续 3 轮零错** (R798/R799/R800 — 历史最长净窗口):
   30min 68 attempts 全 pexec_success. per-key fid 全 b1b22d03 均布 k0:18 k1:13 k2:14 k3:12 k4:11.
3. **buffer 全 attempt=1 success**: 5key 全活, 一次过, 无 buffer/wait/keymanager 日志.
4. **1× nv_gw 502 (f15fe5ef) 历史延续**: R796 wait_queue 验证案例死请求 (R797/R798/R799/R800 已记 4 轮).
   当前实时 nv_requests 30min caller=cc4101-primary 仅 200 (无 502), 死请求已不再产生.
5. **容器健康**: nv_gw + cc4101 都 ok. nv_gw Up 29min (R796 09:10 up -d 基线续跑).

## 判稳结论

- cc4101 SR 排 499 = 100% ≥ 99% 阈值 → NOP 巡检轮
- glm5_2_nv tier 连续 3 轮零错 (R798/R799/R800) — 历史最长净窗口
- fallback 0.88% < 10% 目标
- 无新错误类型 / 无新错误模式
- cleanest 持平 27 (R774 基线)

## 暴露的长期改进点 (本轮不动, 留作下轮候选)

**WAIT-RECOVER retry 只跑 1 key** (buffer_stream.py:532-534): `self.attempt=0;
_execute_and_drain(timeout_stairs[0])` 调用一次, 试 1 key 失败即 WAIT-FAIL send 502.
对比 buffer 主循环 5 attempt × 5key, retry 不够鲁棒. R796 案例 f15fe5ef 触发了此路径
(已记 R797/R798/R799/R800 四轮).

候选改动 (deadline 评估后下轮动):
- 方案 A: WAIT-RECOVER retry 跑完整 chain (5key) — 5 attempt (194s) + wait 180s + chain 220s
  = ~594s 超 cc4101 470s, 必须 chain 内只跑 1-2 key.
- 方案 B: WAIT-FAIL 后再 wait 一轮 (2 次 wait 机会) — 简单但叠加超时同上.
- 方案 C: 增大 cc4101 STREAM_TOTAL_DEADLINE — cc2 SDK 600s 是硬上限.

当前 SR 100% 不急改. 等下次集中瞬断复现确认必要性.

## SR 趋势

| 轮 | 30min SR (cc4101) | tier 噪声 (glm5_2_nv) | 备注 |
|---|---|---|---|
| R792 | 99.0% | 14 RemoteDisc 均 | |
| R793 | 100% | 16 RemoteDisc 均 | |
| R795 | 100% | 17 RemoteDisc 均 | R794 后置 |
| R796 | 改 env 5min 22/22 100% | - | wait_queue 120→180 |
| R797 | 100% (排499)/99.0% | 14 RemoteDisc + 1 empty_200 | R796 后置零回归 |
| R798 | 100% (排499)/99.0% | 0 错误 | wait_queue 180 续净, tier 零错 |
| R799 | 100% (排499)/99.0% | 0 错误 | 连续 2 轮 tier 零错 |
| **R800** | **100% (排499)/99.1%** | **0 错误** | **连续 3 轮 tier 零错, 历史最长** |

## 下一步

- **R801**: 继续 NOP 监测 30min cc4101 SR. 维持 R774=27 cleanest 基线.
- **长期候选不动**: WAIT-RECOVER retry chain 鲁棒化 (方案 A/B/C). 当前 SR 100% 不急.
- nv_gw 容器 base = R796 09:10 up -d, 续跑稳定.
- 并行 dsv4f 自优化线 — 不属 cc2 职责.

## 参数快照 (R800 = R796, 无改动)

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
