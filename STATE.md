# R370: NOP 巡检轮 (cc2 0req, dsv4p_nv SR=74.2% 23/31, all_tiers_exhausted×7[含3×NV-TIER-SKIP 1ms] + NVStream_IncompleteRead×1, NVCF 429波)

## 当前轮基线 (2026-08-02 21:37 CST, R370 已完成, R371 待跑)
- 本仓 master: R369 已 push. hermes 仓: R368 已 push (1f9ed02).
- **架构**: cc4101 `PRIMARY_UPSTREAM_MODEL=dsv4p_nv`. cc2 链路 = cc4101(dsv4p_nv) → nv_gw → NVCF.
- **本轮 R370 (hm2_cc2)**: NOP 巡检轮. cc2 (cc4101-primary) 30min 0 req (session 间歇空闲).
  dsv4p_nv 30min 全 caller SR=74.2% (23/31), 失败 8 = 7× all_tiers_exhausted (其中 3× 为 NV-TIER-SKIP 1ms
  瞬拒, 4× 为 429 配额瞬时空位 1.3-1.9s) + 1× NVStream_IncompleteRead (502, 31967ms, 远程 NVCF mid-stream reset).
  根因: 21:25/21:30/21:35 三波 NVCF dsv4p function 配额 429 波, 全 key cooling 期间 (21:30:43+180s 窗口)
  撞 3 笔非缓冲 caller 请求触发 NV-TIER-SKIP 直接 1ms 502 (upstream.py:1676-1693, 不进 buffer/WaitQueue).
  **cc2 是缓冲 caller (NVU_BUFFER_CALLERS), 走 buffer 5key 轮转路径, 不走 NV-TIER-SKIP, 不受影响.**
  另: glm5_2_nv other caller 1× stream_first_byte_timeout (key0, 502, 29952ms, 非 cc2 流量, 单发).
  错误类型无新增 (dsv4p 仍 all_tiers_exhausted + NVStream_IncompleteRead, 九十三轮一致 R268-R370).
  cc2 无流量不受影响, 0 fallback 0 deadline. 0 改动 0 restart. **九十三轮一致 R268-R370**.

## R-nvonly 核心铁律 (持续生效)
- 只改 HM2 nv_gw (40006), 不碰 HM1, 不碰 ms_gw 源码.
- ms_gw fallback 已恢复 (`NVU_DISABLE_MS_FALLBACK=0`, `FALLBACK_UPSTREAM=ms_gw:40007`), 不主动禁用.
- 改前有数据, 改后必验证, 写入仓库.

## 本轮关键数据 (30min 实时链路分析注入 ~21:36 CST + DB 复核)

### 1. cc2 (cc4101-primary) 30min 0 req
- 同 R275-R369, session 间歇空闲, 链路空闲健康. 0 fallback 0 deadline.
- buffer/wait 日志 (BUFFER-/WAIT-) 30min 空 (无 buffer 流量).

### 2. dsv4p_nv 30min 全 caller SR=74.2% (23/31)
| caller | model | status | count | avg_dur |
|---|---|---|---|---|
| hermes | dsv4p_nv | 200 | 20 | 12469 |
| hermes | dsv4p_nv | 429 | 4 | 1482 |
| hermes | dsv4p_nv | 502 | 1 | 31967 |
| other | dsv4p_nv | 200 | 3 | 95 |
| other | dsv4p_nv | 502 | 3 | 1 |
| other | glm5_2_nv | 200 | 5 | — |
| other | glm5_2_nv | 502 | 1 | 29952 |

per-key (dsv4p): key2 → 21×200 (12469) + 1×502 (31967); key3 → 1×200 (18574); key4 → 1×200 (21754); 空 key → 4×429 (1482) + 3×502 (1).
per-egress: 203.10.96.139 → 22× (95 avg); 134.195.101.120 → 1× (100); 134.195.101.194 → 1× (100); 空 → 7× (0).
finish_reason (200): tool_calls×18, stop×3, length×2 (无 zombie).
分钟趋势: 13:06-13:30 持续 23×200, 13:07 单发 1×502 (IncompleteRead), 13:22/13:25/13:30/13:35 各 1×429, **13:33:36/38/40 三连 502 (1ms NV-TIER-SKIP)**.
延迟 (200): avg_dur 13138, max 27598, min 2077, avg_ttfb 12738, avg_in 1, avg_out 6.
fallback f×37 (全部 false, 0 fallback).

### 3. 错误分类 (DB 实测 30min)
- 8 dsv4p 错误: 7× all_tiers_exhausted (avg 847ms) + 1× NVStream_IncompleteRead (31967ms).
  - 7× all_tiers_exhausted 细分: 4×429 (1250-1949ms, NVCF function 配额瞬时空位) + 3×502 (1ms, NV-TIER-SKIP 全 cooling 瞬拒).
  - NVStream_IncompleteRead: key2, 502, 31967ms, 出口 134.195.101.194. R353 曾清零, 周期性低频偶发单发, 自恢复.
- 1 glm5_2_nv 错误: stream_first_byte_timeout (key0, 502, 29952ms, other caller, 非 cc2 流量, 单发).
- dsv4p 错误类型集合与 R268-R369 一致 (all_tiers_exhausted + NVStream_IncompleteRead, 无新增).
- tier_attempts 30min 0 行 (全 key cooling 时 KeyManager 直接 NV-TIER-SKIP, 不做 tier attempt).
- buffer/wait 日志空.

### 4. KEYMGR 日志 (429 退避自恢复实测, 21:25-21:35)
- 21:25:42 全 key 429 → k3 count=4 cooldown=180s, k1/k2/k4/k5 count=2 cooldown=180s → NV-GLOBAL-COOLDOWN 180s.
- 21:30:43 全 key decayed (>300s) resetting → count=1, cooldown 120-180s → 第二波 429 → NV-GLOBAL-COOLDOWN 180s.
- **21:33:36/38/40 NV-TIER-SKIP ×3** (全 key cooling 窗口 21:30:43+180s 内撞请求, 1ms 瞬拒, 不进 buffer).
- 21:35:42 第三波 429 → k3 count=3 cooldown=480s (指数退避生效), NV-GLOBAL-COOLDOWN 180s. **自恢复确认**.
- 429 退避链 (120→180→480s 指数) + ProbeWorker 15s 探测 + decayed reset 三机制协同.

### 5. 健康检查
- 容器全 Up: nv_gw 7h, cc4101 7h, nv_gw_stable 20h, ms_gw/logs_db 3 days 持续.
- /health: status=ok, nv_num_keys=5, nv_model_tiers=[kimi_nv,dsv4p_nv,glm5_2_nv].
- 6h stream_total_deadline 频次 0 (deadline 链对齐稳定).
- 30min fallback_occurred: f×35 (0 fallback).
- 配置未变 (见参数快照).

## 根因: NVCF dsv4p function 429 波 + NV-TIER-SKIP (非代码缺陷, 沿用 R353-R369 分析)

### 现象
- 本轮 8 dsv4p 错误: 4×429 (NVCF 配额瞬时空位) + 3×NV-TIER-SKIP 1ms (全 cooling 窗口撞请求) + 1×NVStream_IncompleteRead (远程 mid-stream reset).
- NV-TIER-SKIP (upstream.py:1676-1693): 全 5 key cooling 时直接 continue 跳过 tier, 0 attempt 0ms → 1ms 502.
  发生在 agent_type=_nv 非缓冲 caller. cc2 (cc4101-primary) 是缓冲 caller, 走 buffer 5key 轮转 + WaitQueue, 不走此路径.
- NVStream_IncompleteRead: 远程 NVCF mid-stream 中断流 (TCP reset), 非本地代码缺陷.
- all_tiers_exhausted (429): NVCF dsv4p function 配额瞬时空位, 低频偶发, buffer 5key 轮转 + KeyManager 指数退避
  + ProbeWorker 探测 + decayed reset 对持续 429 仍有效 (R268-R369 验证, 本轮 KEYMGR 日志实测自恢复).

### 结论
- **非 nv_gw 代码缺陷, 无需本轮改码**.
- NV-TIER-SKIP 是全 cooling 时的快速失败路径, 对非缓冲 caller 设计如此 (不等 NVCF 恢复, 快速返 5xx 让上层决策).
  cc2 缓冲 caller 不受影响. STATE.md R268 标注的"全 key cooling 时 buffer 零 tier attempt"潜在改进点
  对 cc2 缓冲路径不触发 (cc2 走 buffer, 不走 NV-TIER-SKIP).
- NVStream_IncompleteRead 是上游 NVCF 流中断, 偶发单发, 自恢复.
- stream_first_byte_timeout 是 glm5_2_nv other caller 单发, 非 cc2 流量, 自恢复.
- 当前 cc2 流量极低, 偶发错误罕见且自恢复, 不达介入阈值.

## 判稳
- **NOP 巡检轮**. cc2 primary 0 req, 链路空闲健康, 0 fallback 0 deadline.
- dsv4p_nv 本轮 SR=74.2% (23/31), 较 R369 87.9% (29/33) 下降 (样本极小自然变动,
  本轮遇 NVCF 429 三波 + NV-TIER-SKIP 三连 1ms, 但全部非缓冲 caller, cc2 不受影响).
  dsv4p 错误类型无新增, 与 R268-R369 一致 (九十三轮一致).

## 下一步
- 继续 NOP 巡检, 等 cc2 流量恢复后观察 dsv4p_nv SR (cc2 走 buffer 路径, 行为可能不同于非缓冲 caller).
- 关注是否出现新错误类型 (非 NVStream_IncompleteRead/all_tiers_exhausted) 或 key/IP 级故障, 再决定是否介入.
- NVStream_IncompleteRead 若从偶发单发转为连续多发 (>=3/h 同 key), 再评估 transport 错误分类/重试逻辑.
- all_tiers_exhausted 若从低频偶发转为持续 429 波 (>=5/h), 再评估 buffer 轮转/KeyManager 退避参数.
- NV-TIER-SKIP 若在 cc2 缓冲 caller 上出现 (理论上不应, 因 cc2 走 buffer), 再评估 buffer 与 NV-TIER-SKIP 路径关系.

## 参数快照 (未变)
- cc4101: FALLBACK_UPSTREAM_URL=ms_gw:40007, CC4101_STREAM_TOTAL_DEADLINE_S=470, PRIMARY_HEADER_TIMEOUT=400, PRIMARY_UPSTREAM_MODEL=dsv4p_nv, UPSTREAM_TIMEOUT=130, UPSTREAM_IDLE_TIMEOUT=150.
- nv_gw: NVU_DISABLE_MS_FALLBACK=0 (ms_gw fallback 已恢复), UPSTREAM_TIMEOUT=90, NVU_BUFFER_MAX_RETRIES=5 (90s×5=450s), TIER_COOLDOWN_S=180, KEY_COOLDOWN_S=30, MIN_OUTBOUND_INTERVAL_S=10.
- nv_gw: NVU_BUFFER_CALLERS=cc4101-primary,openclaw2 (cc2 走 buffer 路径, 不走 NV-TIER-SKIP).
- KeyManager: 429→120-600s 指数退避 (实测 120→180→480s); RemoteDisconnected→5-10s 短惩罚不累计 conn_count.
- deadline 链: 90s/buffer-attempt ×5 = 450s buffer < 470s cc4101 < 500s SDK idle.
