# R364: NOP 巡检轮 (cc2 0req, dsv4p_nv SR=85.7% 18/21, all_tiers_exhausted×2, 根因不变)

## 当前轮基线 (2026-08-02 21:16 CST, R364 已完成, R365 待跑)
- 本仓 master: R363 已 push, R364 待 push. hermes 仓: 未同步 (本仓 rounds 独立, hermes 仓 R359 最近).
- **架构**: cc4101 `PRIMARY_UPSTREAM_MODEL=dsv4p_nv`. cc2 链路 = cc4101(dsv4p_nv) → nv_gw → NVCF.
- **本轮 R364 (hm2_cc2)**: NOP 巡检轮. cc2 (cc4101-primary) 30min 0 req (session 间歇空闲).
  dsv4p_nv 30min 全 caller (hermes) SR=85.7% (18/21), 失败 3 = 2× all_tiers_exhausted
  (NVCF function 级 429 配额周期单发, 12:45-12:50 自恢复 18×200 后 13:07 单发 1×NVStream_IncompleteRead).
  本轮 **1× NVStream_IncompleteRead** (R353 曾清零, 周期性低频偶发, 单发未达连续多发阈值).
  错误类型无新增, 与 R268-R363 一致. cc2 无流量不受影响, 0 fallback 0 deadline.
  0 改动 0 restart. **八十七轮一致 R268-R364**.

## R-nvonly 核心铁律 (持续生效)
- 只改 HM2 nv_gw (40006), 不碰 HM1, 不碰 ms_gw 源码.
- ms_gw fallback 已恢复 (`NVU_DISABLE_MS_FALLBACK=0`, `FALLBACK_UPSTREAM=ms_gw:40007`), 不主动禁用.
- 改前有数据, 改后必验证, 写入仓库.

## 本轮关键数据 (30min 实时链路分析注入 ~21:15 CST)

### 1. cc2 (cc4101-primary) 30min 0 req
- 同 R275-R363, session 间歇空闲, 链路空闲健康. 0 fallback 0 deadline.
- buffer/wait 日志 (BUFFER-/WAIT-) 30min 空 (无 buffer 流量).
- 30min caller×model×status 总览: hermes|dsv4p_nv|200×17, 429×2, 502×1; openclaw|dsv4p_nv|200×1.

### 2. dsv4p_nv 30min 全 caller (hermes) SR=85.7% (18/21)
| caller | model | status | count | avg_dur |
|---|---|---|---|---|
| hermes | dsv4p_nv | 200 | 17 | 10868 |
| hermes | dsv4p_nv | 429 | 2 | 1383 |
| hermes | dsv4p_nv | 502 | 1 | 31967 |
| openclaw | dsv4p_nv | 200 | 1 | 3393 |

per-key (dsv4p): key2 → 17×200 (avg_dur 10868) + 1×502 (31967); key3 → 1×200 (3393); 空 key → 2×429 (1383).
per-egress: 203.10.96.139 → 18×200 (100%); 134.195.101.194 → 1×100; 空 IP → 2×429.
finish_reason (200): tool_calls×14, stop×4 (无 zombie).
分钟趋势: 12:45-12:50 单发 2×429 (function 配额周期耗尽); 12:55-13:11 恢复 18×200; 13:07 单发 1×502 (IncompleteRead).
延迟 (200): avg_dur 10453, max 20897, min 3393, avg_ttfb 9767.
fallback f×21 (全部 false, 0 fallback).

### 3. 错误分类 (DB 实测)
- 3 错误: 2× all_tiers_exhausted (sub=all_tiers_failed_in_mapped_tier, avg_dur 1383) + 1× NVStream_IncompleteRead (avg_dur 31967).
- 2× 429: NVCF function 级配额周期单发, key2 同时挂 → all_tiers_exhausted.
- 1× NVStream_IncompleteRead: R353 曾清零, 周期性低频偶发, 本轮单发未达连续多发阈值.
- 与 R268-R363 错误类型集合一致 (无新增).
- tier_attempts 30min 0 行 (429 在 NVCF 侧, 未进 nv_gw tier 重试).
- buffer/wait 日志空.

### 4. 健康检查
- 容器全 Up: nv_gw 19h, cc4101 7h, nv_gw_stable 19h, ms_gw/logs_db 3 days 持续.
- /health: status=ok, nv_num_keys=5, nv_model_tiers=[kimi_nv,dsv4p_nv,glm5_2_nv].
- 配置未变 (见参数快照).

## 根因: buffer 对 function 级 429 无保护 (设计盲区, 非代码缺陷, 沿用 R278-R363 分析)

### 现象
- dsv4p_nv 5key (k0-k4) 全绑同一 NVCF function.
- NVCF 429 配额是 function 级: function 配额耗尽时, 5 key 同时收 429.
- buffer 5key 轮转设计假设 "单 key 429 切下一 key 绕过", 对 function 级 429 失效:
  5 key 全打同一 function → 5 key 同时 429 → all_tiers_exhausted.
- 设计盲区非 nv_gw 代码缺陷. R-nvonly 5key 5IP 设计针对 key/IP 级隔离, 未覆盖 function 级配额.
- 单波 429 证明是 NVCF function 配额周期自恢复 (12:55-13:11 恢复 18×200), 非 nv_gw 代码缺陷.
- KEYMGR 指数退避 (120→180→480s) 正常工作, 429 后 key 进入冷却, 配额恢复后 ProbeWorker 探测唤醒.
- avg_dur 1383s 是 all_tiers_exhausted 累积 KEYMGR 指数退避等待时长.

### NVStream_IncompleteRead 评估
- 本轮单发 1× (key2, 502, 31967ms, 出口 134.195.101.194).
- R353 已清零, 周期性低频偶发, 单发未达连续多发阈值.
- 远程 NVCF 中断流 (mid-stream TCP reset), 非本地代码缺陷.
- 若从偶发单发转为连续多发 (>=3/h 同 key), 再评估 transport 错误分类/重试逻辑.

### 结论
- **非 nv_gw 代码缺陷, 无需本轮改码**. NVCF function 级配额是上游硬限制.
- buffer 5key 轮转对 key/IP 级 429 仍有效 (R268-R363 验证), 对 function 级 429 是已知盲区.
- 当前 cc2 流量极低, all_tiers_exhausted 罕见且自恢复, 不达介入阈值.

## 判稳
- **NOP 巡检轮**. cc2 primary 0 req, 链路空闲健康, 0 fallback 0 deadline.
- dsv4p_nv 本轮 SR=85.7% (18/21), 较 R363 76.5% (13/17) 略升 (样本极小自然变动, +5×200 -1×429, NVStream_IncompleteRead 单发维持).
- 错误类型无新增, 与 R268-R363 一致 (八十七轮一致).
- 八十七轮一致 R268-R364.

## 下一步
- 继续 NOP 巡检, 等 cc2 流量恢复后观察 dsv4p_nv SR.
- 关注是否出现新错误类型 (非 all_tiers_exhausted/NVStream_IncompleteRead) 或 key/IP 级故障, 再决定是否介入.
- NVStream_IncompleteRead 若从偶发单发转为连续多发 (>=3/h), 再评估 transport 错误分类/重试逻辑.

## 参数快照 (未变)
- cc4101: FALLBACK_UPSTREAM_URL=ms_gw:40007, CC4101_STREAM_TOTAL_DEADLINE_S=470, PRIMARY_HEADER_TIMEOUT=400, PRIMARY_UPSTREAM_MODEL=dsv4p_nv, UPSTREAM_TIMEOUT=130, UPSTREAM_IDLE_TIMEOUT=150.
- nv_gw: NVU_DISABLE_MS_FALLBACK=0 (ms_gw fallback 已恢复), UPSTREAM_TIMEOUT=90, NVU_BUFFER_MAX_RETRIES=5 (90s×5=450s), TIER_COOLDOWN_S=180, KEY_COOLDOWN_S=30, MIN_OUTBOUND_INTERVAL_S=10.
- KeyManager: 429→120-600s 指数退避; RemoteDisconnected→5-10s 短惩罚不累计 conn_count.
- deadline 链: 90s/buffer-attempt ×5 = 450s buffer < 470s cc4101 < 500s SDK idle.
