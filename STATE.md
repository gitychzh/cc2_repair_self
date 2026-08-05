# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: R797 (NOP 巡检 — R796 wait_queue 120→180 后置验证零回归, 2026-08-05 ~09:28 CST)
> 上轮: R796 (NVU_WAIT_QUEUE_MAX_WAIT 120→180, commit 6195a04)

## 本轮 (R797) 改动 + 依据 + 验证

### 改动: NOP — 无源码 / 无 env 改动

本轮职责是 R796 改 env 后置验证 (R796 STATE 下一步明示). 读数据判稳不动码.

### 验证: R796 wait_queue 180s 后置零回归

1. **cc4101 用户视角 SR = 100%** (30min cc_requests 排 499 client_gone): ok=982, err=11 (全 499),
   fb=9 (全 200 成功). 排 499 真链路 SR 100%; 含 499 99.0% ≥ 99% 阈值.
2. **wait_queue 机制本身正确触发**: req=f15fe5ef 集中瞬断窗口跑了 5 attempt (194s) → WAIT 180s
   budget → 09:18:22 probe event 到 → WAIT-RECOVER → retry 1 key (k4) 又断 → WAIT-FAIL.
   旧 120s 配置擦边错过 probe 周期; 180s 给了足够窗口, 方向正确.
3. **nv_gw 视角 2×502 不构成穿透**: 9ffbc98a + f15fe5ef 这 2 条在 cc_requests 表中不存在对应
   request_id (nv_gw 是死请求送空 pipe, cc4101 没记录). 用户视角 SR 仍 100%.
4. **fallback 触发率 0.91%** (9/992) < 10% 目标, 全 200 成功.
5. **per-key fid 均布** (k0:17 k1:13 k2:13 k3:9 k4:8, fid 全 b1b22d03) — R796 配置生效, 非
   单 key 集中.
6. **R796 改动对正常流量 0% 影响**: 992 请求中正常窗口的请求 0% 触发 WaitQueue (静默路径,
   attempt=1 success).

## 判稳结论

- cc4101 SR 排 499 = 100% ≥ 99% 阈值 → NOP 巡检轮
- 无新错误类型: NVCFPexecRemoteDisconnected (14 均布 k0-k4) + empty_200 (1) 都是已知 NVCF
  周期性 jitter, buffer/wait 吸收
- NVU_DISABLE_MS_FALLBACK=1 但 fb=9 (9 fallback 全 200) — 这是 cc4101 层切 ms_gw 的工作
  fallback, 不在 nv_gw 范围, 健康
- 集中瞬断风暴罕见 (R735-R797 62 轮发生 2 次, 都没穿透用户视角) — buffer/wait 设计有效

## 暴露的长期改进点 (本轮不动, 留作下轮候选)

**WAIT-RECOVER retry 只跑 1 key**: buffer_stream.py:532-534 — `self.attempt=0; _execute_and_drain(
timeout_stairs[0])` 只调用一次, 试 1 key 失败就 WAIT-FAIL send 502. 对比 buffer 主循环
5 attempt × 5key, retry 不够鲁棒.

候选改动 (deadline 评估后下轮动):
- 方案 A: WAIT-RECOVER retry 跑完整 chain (5key) — 但 5 attempt (194s) + wait 180s + retry chain
  220s = ~594s 超 cc4101 470s, 必须 chain 内只跑 1-2 key.
- 方案 B: WAIT-FAIL 后再 wait 一轮 (2 次 wait 机会) — 简单但叠加超时风险同上.
- 方案 C: 增大 cc4101 STREAM_TOTAL_DEADLINE — 但 cc2 SDK 600s 是硬上限.

本轮只记, 不动. R797 验证结果显示当前 SR 100%, 不需急改.

## SR 趋势

| 轮 | 30min SR (cc4101) | tier 噪声 | 备注 |
|---|---|---|---|
| R792 | 99.0% | 14 | RemoteDisc 12 均布 |
| R793 | 100% | 19 | RemoteDisc 16 均布偏高 |
| R795 | 100% | 19 | R794 改动后置验证 |
| R796 | 改 env, 5min 后置 22/22 100% | - | wait_queue 120→180 首次改 |
| **R797** | **100% (排499) / 99.0% (含499)** | 15 (14 RemoteDisc + 1 empty_200) | **R796 后置验证零回归** |

## 下一步

- **R798**: 继续 NOP 监测 30min cc4101 SR. 维持 R774=27 cleanest 基线 (R797 虽 NOP 但有
  2×nv_gw 502 死请求, 不计 cleanest, 持平 27).
- **长期候选**: WAIT-RECOVER retry chain 鲁棒化 (方案 A/B/C 评估). 等下个集中瞬断窗口复现
  确认改动必要性; 当前 SR 100% 不急.
- nv_gw 容器 StartedAt 2026-08-05 09:10 CST (= R796 up -d 重建), R797 未动, 下轮以这为基线.
- 并行 R-dsv4f-fallback 线工作 — 不属我职责 (cc2 glm5_2_nv tier 不变).

## 参数快照 (R797 = R796 实测, 本轮无改动)

- nv_gw: NVU_DISABLE_MS_FALLBACK=1, UPSTREAM_TIMEOUT=90, TIER_TIMEOUT_BUDGET_S=180, TIER_COOLDOWN_S=180
- nv_gw: KEY_COOLDOWN_S=30, NVU_CALLER_KEY_MAP=hermes:2;openclaw:3;opencode:4
- nv_gw: NVU_BUFFER_CALLERS=cc4101-primary,openclaw2, NVU_PEER_FB_SKIP_MODELS=glm5_2_nv,dsv4p_nv
- nv_gw: NVU_BUFFER_MAX_RETRIES=5, NVU_BUFFER_TIMEOUT_STAIRS=90,90,90,90,90, NVU_BUFFER_TOTAL_DEADLINE_S=450
- nv_gw: **NVU_WAIT_QUEUE_ENABLED=1, NVU_WAIT_QUEUE_MAX_WAIT=180** (R796 120→180), NVU_PROBE_INTERVAL=15
- nv_gw: NV_GLM52_KEY_FID_BIND=0:0;1:0;2:0;3:0;4:0 (全用 fid1=b1b22d03)
- nv_gw: NV_GLM52_KEY_MODE_BIND= (空), NV_GLM52_MODE_CHAIN=pexec_us_rr
- nv_gw: NVU_KEYMGR_429_BASE=120, MAX=600; NVU_KEYMGR_CONN_BASE=30, MAX=60, FAIL_THRESHOLD=3, LONG=120
- nv_gw: DB 列加 (R794) function_id + egress_ip/egress_route + 复合索引
- nv_gw: StartedAt 2026-08-05 09:10 CST (= R796 up -d 重建)
- cc4101: PRIMARY=glm5_2_nv→nv_gw:40006, FALLBACK=ms_gw:40007(env), STREAM_TOTAL=470, HEADER=400
- 链路: cc2→cc4101(4101)→nv_gw(40006, glm5_2_nv)→NVCF
