# STATE — cc2 自优化 nv_gw 链路 (R-nvonly 方向)

## 当前轮基线 (2026-08-02 20:07 CST, R347 NOP 巡检轮 已完成, R348 待跑)
- 本仓 master: R346 (d8e3202) 已 push. hermes 仓: R347 round 文件待 commit+push.
- **架构**: cc4101 `PRIMARY_UPSTREAM_MODEL=dsv4p_nv`. cc2 链路 = cc4101(dsv4p_nv) → nv_gw → NVCF.
- **本轮 R347 (hm2_cc2)**: NOP 巡检轮. cc2 (cc4101-primary) 30min 0 req (session 间歇空闲).
  dsv4p_nv 30min 全 caller (hermes) SR=76.5% (13/17), 失败 4 = 3× all_tiers_exhausted
  (NVCF function 级 429 配额周期多波, 11:55-12:07 自恢复 13×200) + 1× NVStream_IncompleteRead (502,
  transport-level 偶发单发, R345/R347 出现 R346 清零, 周期低频不达介入阈值).
  错误类型无新增, 与 R268-R346 一致. cc2 无流量不受影响, 0 fallback 0 deadline.
  0 改动 0 restart. **七十轮一致 R268-R347**.

## R-nvonly 核心铁律 (持续生效)
- 只改 HM2 nv_gw (40006), 不碰 HM1, 不碰 ms_gw 源码.
- ms_gw fallback 已恢复 (`NVU_DISABLE_MS_FALLBACK=0`, `FALLBACK_UPSTREAM=ms_gw:40007`), 不主动禁用.
- 改前有数据, 改后必验证, 写入仓库.

## 本轮关键数据 (30min 实时链路分析注入 ~20:07 CST)

### 1. cc2 (cc4101-primary) 30min 0 req
- 同 R275-R346, session 间歇空闲, 链路空闲健康. 0 fallback 0 deadline.
- buffer/wait 日志 (BUFFER-/WAIT-) 30min 空 (无 buffer 流量).
- 30min caller×model×status 总览: hermes|dsv4p_nv|200×13, 429×3, 502×1.

### 2. dsv4p_nv 30min 全 caller (hermes) SR=76.5% (13/17)
| caller | model | status | count |
|---|---|---|---|
| hermes | dsv4p_nv | 200 | 13 |
| hermes | dsv4p_nv | 429 | 3 |
| hermes | dsv4p_nv | 502 | 1 |

per-key (dsv4p): key2 → 13×200 (avg_dur 10377) + 1×502 (35151); 空 key → 3×429 (2157).
per-egress: 203.10.96.139 → 14 (含 13×200 + 1×502); 空 IP → 3×429.
finish_reason (200): tool_calls×11, stop×2 (无 zombie).
分钟趋势: 11:40/11:45/11:50 持续 429 (3波); 11:55-12:07 恢复 13×200; 12:02 单发 502.
延迟 (200): avg_dur 10377, max 24137, min 4879, avg_ttfb 10052.
fallback 0/17.

### 3. 错误分类 (DB 实测)
- 4 错误: 3× all_tiers_exhausted (sub=all_tiers_failed_in_mapped_tier, avg_dur 2157) + 1× NVStream_IncompleteRead (avg_dur 35151, 502).
- 3× 429: NVCF function 级配额周期, 多波, key2 同时挂 → all_tiers_exhausted.
- 1× NVStream_IncompleteRead (502): transport-level 偶发单发 (R345 出现→R346 清零→R347 再单发), 不达介入阈值.
- 与 R268-R346 错误类型集合一致.
- tier_attempts 30min 0 行 (429 在 NVCF 侧, 未进 nv_gw tier 重试).
- buffer/wait 日志空.

### 4. 健康检查 (沿用 R346, 容器无 restart)
- 容器全 Up: nv_gw/cc4101 6h, nv_gw_stable 18h, ms_gw/logs_db 3 days 持续.
- 配置未变 (见参数快照).

## 根因: buffer 对 function 级 429 无保护 (设计盲区, 非代码缺陷, 沿用 R278-R346 分析)

### 现象
- dsv4p_nv 5key (k0-k4) 全绑同一 NVCF function.
- NVCF 429 配额是 function 级: function 配额耗尽时, 5 key 同时收 429.
- buffer 5key 轮转设计假设 "单 key 429 切下一 key 绕过", 对 function 级 429 失效:
  5 key 全打同一 function → 5 key 同时 429 → all_tiers_exhausted.
- 设计盲区非 nv_gw 代码缺陷. R-nvonly 5key 5IP 设计针对 key/IP 级隔离, 未覆盖 function 级配额.
- 多波 429 证明是 NVCF function 配额周期自恢复 (11:55-12:07 恢复 13×200), 非 nv_gw 代码缺陷.
- KEYMGR 指数退避 (120→180→480s) 正常工作, 429 后 key 进入冷却, 配额恢复后 ProbeWorker 探测唤醒.
- 本轮 1× NVStream_IncompleteRead (502) 是 mid-stream transport 断连偶发单发, 周期性低频不达介入阈值.

### 结论
- **非 nv_gw 代码缺陷, 无需本轮改码**. NVCF function 级配额是上游硬限制.
- buffer 5key 轮转对 key/IP 级 429 仍有效 (R268-R346 验证), 对 function 级 429 是已知盲区.
- 当前 cc2 流量极低, all_tiers_exhausted 罕见且自恢复, 不达介入阈值.
- NVStream_IncompleteRead 偶发单发不达介入阈值.

## 判稳
- **NOP 巡检轮**. cc2 primary 0 req, 链��空闲健康, 0 fallback 0 deadline.
- dsv4p_nv 本轮 SR=76.5% (13/17), 较 R346 63.6% (7/11) 回升 (429 波次减, 样本极小自然变动).
- 错误类型无新增, 与 R268-R346 一致 (七十轮一致).
- 七十轮一致 R268-R347.

## 下一步
- 继续 NOP 巡检, 等 cc2 流量恢复后观察 dsv4p_nv SR.
- 关注是否出现新错误类型 (非 all_tiers_exhausted/NVStream_IncompleteRead) 或 key/IP 级故障, 再决定是否介入.
- NVStream_IncompleteRead 若从偶发单发转为连续多发, 再评估 transport 错误分类/重试逻辑.

## 参数快照 (R347, 沿用主仓, 无改动)
- cc4101: FALLBACK_UPSTREAM_URL=http://ms_gw:40007/v1/chat/completions, CC4101_STREAM_TOTAL_DEADLINE_S=470, PRIMARY_HEADER_TIMEOUT=400, PRIMARY_UPSTREAM_MODEL=dsv4p_nv, UPSTREAM_TIMEOUT=130, UPSTREAM_IDLE_TIMEOUT=150, CC4101_PRIMARY_FAIL_THRESHOLD=3, CC4101_PRIMARY_SKIP_S=30.
- nv_gw: NVU_DISABLE_MS_FALLBACK=0, UPSTREAM_TIMEOUT=90, TIER_TIMEOUT_BUDGET_S=180, TIER_COOLDOWN_S=180, KEY_COOLDOWN_S=30, NVU_BUFFER_MAX_RETRIES=5 (5×90s=450s), NVU_BUFFER_TOTAL_DEADLINE_S=450, NV_INTEGRATE_KEY_COOLDOWN_S=90, NVU_BUFFER_CALLERS=cc4101-primary,openclaw2, MIN_OUTBOUND_INTERVAL_S=10, NVU_FORCE_STREAM_UPGRADE=0, NVU_CALLER_KEY_MAP=hermes:2;openclaw:3;opencode:4, NVU_PEER_FB_SKIP_MODELS=glm5_2_nv,dsv4p_nv.
