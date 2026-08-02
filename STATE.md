# R368: NOP 巡检轮 (cc2 0req, dsv4p_nv SR=91.4% 32/35, all_tiers_exhausted×2 + NVStream_IncompleteRead×1, 根因不变)

## 当前轮基线 (2026-08-02 21:29 CST, R368 已完成, R369 待跑)
- 本仓 master: R367 已 push. hermes 仓: R367 已 push (4382599).
- **架构**: cc4101 `PRIMARY_UPSTREAM_MODEL=dsv4p_nv`. cc2 链路 = cc4101(dsv4p_nv) → nv_gw → NVCF.
- **本轮 R368 (hm2_cc2)**: NOP 巡检轮. cc2 (cc4101-primary) 30min 0 req (session 间歇空闲).
  dsv4p_nv 30min 全 caller SR=91.4% (32/35), 失败 3 = 2× all_tiers_exhausted
  (429, 1364ms, function 配额瞬时空位, 空 key/空出口, 低频偶发未达连续多发阈值)
  + 1× NVStream_IncompleteRead (key2, 502, 31967ms, 出口 134.195.101.194, 远程 NVCF mid-stream TCP reset, 单发).
  错误类型无新增, 与 R268-R367 一致. cc2 无流量不受影响, 0 fallback 0 deadline. 0 改动 0 restart. **九十一轮一致 R268-R368**.

## R-nvonly 核心铁律 (持续生效)
- 只改 HM2 nv_gw (40006), 不碰 HM1, 不碰 ms_gw 源码.
- ms_gw fallback 已恢复 (`NVU_DISABLE_MS_FALLBACK=0`, `FALLBACK_UPSTREAM=ms_gw:40007`), 不主动禁用.
- 改前有数据, 改后必验证, 写入仓库.

## 本轮关键数据 (30min 实时链路分析注入 ~21:28 CST)

### 1. cc2 (cc4101-primary) 30min 0 req
- 同 R275-R367, session 间歇空闲, 链路空闲健康. 0 fallback 0 deadline.
- buffer/wait 日志 (BUFFER-/WAIT-) 30min 空 (无 buffer 流量).

### 2. dsv4p_nv 30min 全 caller SR=91.4% (32/35)
| caller | model | status | count | avg_dur |
|---|---|---|---|---|
| hermes | dsv4p_nv | 200 | 28 | 11422 |
| hermes | dsv4p_nv | 429 | 2 | 1364 |
| hermes | dsv4p_nv | 502 | 1 | 31967 |
| openclaw | dsv4p_nv | 200 | 1 | — |
| other | dsv4p_nv | 200 | 3 | — |
| other | glm5_2_nv | 200 | 3 | — |

per-key (dsv4p): key2 → 29×200 (11422) + 1×502 (31967); key3 → 2×200 (10984); key4 → 1×200 (21754); 空 key → 2×429 (1364).
per-egress: 203.10.96.139 → 30× (97 avg); 134.195.101.194 → 2× (100); 134.195.101.120 → 1× (100); 空 → 2× (0).
finish_reason (200): tool_calls×25, stop×5, length×2 (无 zombie).
分钟趋势: 13:00-13:25 持续 32×200, 仅 13:07 单发 1×502 (IncompleteRead), 13:22+13:25 各 1×429. 本轮 429 低频偶发 2×.
延迟 (200): avg_dur 11717, max 27598, min 2077, avg_ttfb 11323, avg_in 1, avg_out 5.
fallback f×38 (全部 false, 0 fallback).

### 3. 错误分类 (DB 实测)
- 3 错误: 2× all_tiers_exhausted (all_tiers_failed_in_mapped_tier, avg_dur 1364) + 1× NVStream_IncompleteRead (avg_dur 31967).
- all_tiers_exhausted: 2×429 (1364ms), function 配额瞬时空位 (空 key/空出口), 低频偶发, buffer 5key 轮转对持续 429 仍有效.
- NVStream_IncompleteRead: key2, 502, 31967ms, 出口 134.195.101.194. R353 曾清零, 周期性低频偶发单发, 自恢复.
- 与 R268-R367 错误类型集合一致 (无新增).
- tier_attempts 30min 0 行.
- buffer/wait 日志空.

### 4. 健康检查
- 容器全 Up: nv_gw 7h, cc4101 7h, nv_gw_stable 19h, ms_gw/logs_db 3 days 持续.
- /health: status=ok, nv_num_keys=5, nv_model_tiers=[kimi_nv,dsv4p_nv,glm5_2_nv].
- 配置未变 (见参数快照).

## 根因: all_tiers_exhausted + NVStream_IncompleteRead 周期性偶发 (非代码缺陷, 沿用 R353-R367 分析)

### 现象
- 本轮 3 错误: 2× all_tiers_exhausted (429, 1364ms) + 1× NVStream_IncompleteRead (key2, 502, 31967ms).
- NVStream_IncompleteRead: 远程 NVCF mid-stream 中断流 (TCP reset / 流未读完), 非本地代码缺陷.
- all_tiers_exhausted: function 配额瞬时空位 (空 key/空出口), 低频偶发, buffer 5key 轮转对持续 429 仍有效.
- R353 曾清零, 周期性低频偶发 (2× 429 + 1× IncompleteRead), 未达连续多发阈值.

### 结论
- **非 nv_gw 代码缺陷, 无需本轮改码**.
- NVStream_IncompleteRead 是上游 NVCF 流中断, 偶发单发, 自恢复.
- all_tiers_exhausted 是 function 配额瞬时空位, 低频偶发, buffer 5key 轮转对持续 429 仍有效 (R268-R367 验证).
- 当前 cc2 流量极低, 偶发错误罕见且自恢复, 不达介入阈值.

## 判稳
- **NOP 巡检轮**. cc2 primary 0 req, 链路空闲健康, 0 fallback 0 deadline.
- dsv4p_nv 本轮 SR=91.4% (32/35), 较 R367 94.6% (35/37) 略降 (样本极小自然变动,
  +1×429 -1×0, NVStream_IncompleteRead 单发维持, all_tiers_exhausted 从 1×→2× 仍低频). 错误类型无新增, 与 R268-R367 一致 (九十一轮一致).

## 下一步
- 继续 NOP 巡检, 等 cc2 流量恢复后观察 dsv4p_nv SR.
- 关注是否出现新错误类型 (非 NVStream_IncompleteRead/all_tiers_exhausted) 或 key/IP 级故障, 再决定是否介入.
- NVStream_IncompleteRead 若从偶发单发转为连续多发 (>=3/h 同 key), 再评估 transport 错误分类/重试逻辑.
- all_tiers_exhausted 若从低频偶发转为持续 429 波 (>=5/h), 再评估 buffer 轮转/KeyManager 退避参数.

## 参数快照 (未变)
- cc4101: FALLBACK_UPSTREAM_URL=ms_gw:40007, CC4101_STREAM_TOTAL_DEADLINE_S=470, PRIMARY_HEADER_TIMEOUT=400, PRIMARY_UPSTREAM_MODEL=dsv4p_nv, UPSTREAM_TIMEOUT=130, UPSTREAM_IDLE_TIMEOUT=150.
- nv_gw: NVU_DISABLE_MS_FALLBACK=0 (ms_gw fallback 已恢复), UPSTREAM_TIMEOUT=90, NVU_BUFFER_MAX_RETRIES=5 (90s×5=450s), TIER_COOLDOWN_S=180, KEY_COOLDOWN_S=30, MIN_OUTBOUND_INTERVAL_S=10.
- KeyManager: 429→120-600s 指数退避; RemoteDisconnected→5-10s 短惩罚不累计 conn_count.
- deadline 链: 90s/buffer-attempt ×5 = 450s buffer < 470s cc4101 < 500s SDK idle.
