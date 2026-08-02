# STATE — cc2 自优化 nv_gw 链路 (R-nvonly 方向)

## 当前轮基线 (2026-08-02 20:01 CST, R346 NOP 巡检轮 已完成, R347 待跑)
- 本仓 master: R345 (ff97a2c) 已 push, R346 round 文件待 commit+push. hermes 仓: R346 round 待 commit+push.
- **架构**: cc4101 `PRIMARY_UPSTREAM_MODEL=dsv4p_nv`. cc2 链路 = cc4101(dsv4p_nv) → nv_gw → NVCF.
- **本轮 R346 (hm2_cc2)**: NOP 巡检轮. cc2 (cc4101-primary) 30min 0 req (session 间歇空闲).
  dsv4p_nv 30min 全 caller (hermes) SR=63.6% (7/11), 失败 4 = 4× all_tiers_exhausted
  (NVCF function 级 429 配额周期多波, 11:55-12:01 自恢复 7×200). 本轮无 NVStream_IncompleteRead, 无 502.
  错误类型无新增, 与 R268-R346 一致. cc2 ���流量不受影响, 0 fallback 0 deadline.
  0 改动 0 restart. **六十九轮一致 R268-R346**.

## R-nvonly 核心铁律 (持续生效)
- 只改 HM2 nv_gw (40006), 不碰 HM1, 不碰 ms_gw 源码.
- ms_gw fallback 已恢复 (`NVU_DISABLE_MS_FALLBACK=0`, `FALLBACK_UPSTREAM=ms_gw:40007`), 不主动禁用.
- 改前有数据, 改后必验证, 写入仓库.

## 本轮关键数据 (30min 实时链路分析注入 ~20:01 CST)

### 1. cc2 (cc4101-primary) 30min 0 req
- 同 R275-R346, session 间歇空闲, 链路空闲健康. 0 fallback 0 deadline.
- buffer/wait 日志 (BUFFER-/WAIT-) 30min 空 (无 buffer 流量).
- 30min caller×model×status 总览: hermes|dsv4p_nv|200×7, 429×4.

### 2. dsv4p_nv 30min 全 caller SR=63.6% (7/11)
| caller | model | status | count |
|---|---|---|---|
| hermes | dsv4p_nv | 200 | 7 |
| hermes | dsv4p_nv | 429 | 4 |

per-key (dsv4p): key2 → 7×200 (avg_dur 11162); 空 key → 4×429 (2167).
per-egress: 203.10.96.139 → 7×100%; 空 IP → 4×0%.
finish_reason (200): tool_calls×6, stop×1 (无 zombie).
分钟趋势: 11:35/11:40/11:45/11:50 持续 429 (4波); 11:55-11:56 恢复 3×200; 12:00-12:01 恢复 4×200.
延迟 (200): avg_dur 11162, max 24137, min 4879, avg_ttfb 10759.
fallback 0/11.

### 3. 错误分类 (DB 实测)
- 4 错误: 4× all_tiers_exhausted (sub=all_tiers_failed_in_mapped_tier, avg_dur 2167).
- 429 (4×): NVCF function 级配额周期, 多波, key2 同时挂 → all_tiers_exhausted.
- 本轮无 NVStream_IncompleteRead, 无 502 (较 R345 502×1 清零, transport-level 偶发单发).
- 与 R268-R346 错误类型集合一致.
- tier_attempts 30min 0 行 (429 在 NVCF 侧, 未进 nv_gw tier 重试).
- buffer/wait 日志空.

### 4. 健康检查 (本轮实测 20:01)
- /health 200, nv_num_keys=5, default glm5_2_nv, pexec_models=[kimi_nv, dsv4p_nv, glm5_2_nv].
- 容器全 Up: nv_gw/cc4101 5-6h, nv_gw_stable 18h, ms_gw/logs_db 3 days 持续.

## 根因: buffer 对 function 级 429 无保护 (设计盲区, 非代码缺陷, 沿用 R278-R346 分析)

### 现象
- dsv4p_nv 5key (k0-k4) 全绑同一 NVCF function.
- NVCF 429 配额是 function 级: function 配额耗尽时, 5 key 同时收 429.
- buffer 5key 轮转设计假设 "单 key 429 切下一 key 绕过", 对 function 级 429 失效:
  5 key 全打同一 function → 5 key 同时 429 → all_tiers_exhausted.
- 设计盲区非 nv_gw 代码缺陷. R-nvonly 5key 5IP 设计针对 key/IP 级隔离, 未覆盖 function 级配额.
- 多波 429 证明是 NVCF function 配额周期自恢复 (11:55-12:01 恢复 7×200), 非 nv_gw 代码缺陷.
- KEYMGR 指数退避 (120→180→480s) 正常工作, 429 后 key 进入冷却, 配额恢复后 ProbeWorker 探测唤醒.
- 本轮无 502 RemoteDisconnected transport hang (R345 偶发单发本轮清零, 不达介入阈值).

### 结论
- **非 nv_gw 代码缺陷, 无需本轮改码**. NVCF function 级配额是上游硬限制.
- buffer 5key 轮转对 key/IP 级 429 仍有效 (R268-R346 验证), 对 function 级 429 是已知盲区.
- 当前 cc2 流量极低, all_tiers_exhausted 罕见且自恢复, 不达介入阈值.

## 判稳
- **NOP 巡检轮**. cc2 primary 0 req, 链路空闲健康, 0 fallback 0 deadline.
- dsv4p_nv 本轮 SR=63.6% (7/11), 较 R345 33.3% (3/9) 回升 (429 波次略减, 样本极小 (11req) 自然变动).
- 错误类型无新增, 与 R268-R346 一致.
- 六十九轮一致 R268-R346.

## 下一步
- 继续 NOP 巡检, 等 cc2 流量恢复后观察 dsv4p_nv SR.
- 关注是否出现新错误类型 (非 all_tiers_exhausted/NVStream_IncompleteRead) 或 key/IP 级故障, 再决定是否介入.

## 参数快照 (R346, 沿用主仓, 无改动)
- cc4101: FALLBACK_UPSTREAM_URL=http://ms_gw:40007/v1/chat/completions, CC4101_STREAM_TOTAL_DEADLINE_S=470, PRIMARY_HEADER_TIMEOUT=400, PRIMARY_UPSTREAM_MODEL=dsv4p_nv, UPSTREAM_TIMEOUT=130, UPSTREAM_IDLE_TIMEOUT=150, CC4101_PRIMARY_FAIL_THRESHOLD=3, CC4101_PRIMARY_SKIP_S=30.
- nv_gw: NVU_DISABLE_MS_FALLBACK=0, UPSTREAM_TIMEOUT=90, TIER_TIMEOUT_BUDGET_S=180, TIER_COOLDOWN_S=180, KEY_COOLDOWN_S=30, NVU_BUFFER_MAX_RETRIES=5 (5×90s=450s), NVU_BUFFER_TOTAL_DEADLINE_S=450, NV_INTEGRATE_KEY_COOLDOWN_S=90, NVU_BUFFER_CALLERS=cc4101-primary,openclaw2, MIN_OUTBOUND_INTERVAL_S=10, NVU_FORCE_STREAM_UPGRADE=0, NVU_CALLER_KEY_MAP=hermes:2;openclaw:3;opencode:4, NVU_PEER_FB_SKIP_MODELS=glm5_2_nv,dsv4p_nv.
