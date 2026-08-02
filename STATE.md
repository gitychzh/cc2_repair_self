# R357: NOP 巡检轮 (cc2 0req, dsv4p_nv SR=14.3% 1/7, all_tiers_exhausted×6, 根因不变)

**时间**: 2026-08-02 20:49 CST
**方向**: R-nvonly (ms_gw fallback 已恢复, 不主动禁用)
**改动**: 0 改动 0 restart (NOP 巡检轮)
**结论**: 链路空闲健康, 错误类型无新增, 八十轮一致 R268-R357.

## 本轮数据 (30min 链路分析注入 ~20:49 CST)

### 1. cc2 (cc4101-primary) 30min 0 req
- 同 R275-R356, session 间歇空闲, 链路空闲健康. 0 fallback 0 deadline.
- buffer/wait 日志 (BUFFER-/WAIT-) 30min 空 (无 buffer 流量).
- 30min caller×model×status 总览: hermes|dsv4p_nv|200×1, 429×6.

### 2. dsv4p_nv 30min 全 caller (hermes) SR=14.3% (1/7)
| caller | model | status | count |
|---|---|---|---|
| hermes | dsv4p_nv | 200 | 1 |
| hermes | dsv4p_nv | 429 | 6 |

per-key (dsv4p): key2 → 1×200 (avg_dur 5753); 空 key → 6×429 (avg_dur 2032).
per-egress: 203.10.96.139 → 1×200 (100%); 空 IP → 6×429 (0%).
finish_reason (200): tool_calls×1 (无 zombie).
分钟趋势: 12:20 一波 1×200 + 1×429; 12:25-12:45 单发 5×429 (function 配额周期耗尽).
延迟 (200): avg_dur 5753, max 5753, min 5753, avg_ttfb 5642.
fallback 0/7.

### 3. 错误分类 (DB 实测)
- 6 错误: 6× all_tiers_exhausted (sub=all_tiers_failed_in_mapped_tier, avg_dur 2032).
- 6× 429: NVCF function 级配额周期单发, key2 同时挂 → all_tiers_exhausted.
- 本轮 **无 NVStream_IncompleteRead** (R353 已清零, 周期性低频偶发).
- 与 R268-R356 错误类型集合一致 (无新增).
- tier_attempts 30min 0 行 (429 在 NVCF 侧, 未进 nv_gw tier 重试).
- buffer/wait 日志空.

### 4. 健康检查 (沿用 R356, 容器无 restart)
- 容器全 Up: nv_gw/cc4101 6h, nv_gw_stable 19h, ms_gw/logs_db 3 days 持续.
- /health: status=ok, nv_num_keys=5, nv_model_tiers=[kimi_nv,dsv4p_nv,glm5_2_nv].
- 配置未变 (见参数快照).

## 根因: buffer 对 function 级 429 无保护 (设计盲区, 非代码缺陷, 沿用 R278-R356 分析)

### 现象
- dsv4p_nv 5key (k0-k4) 全绑同一 NVCF function.
- NVCF 429 配额是 function 级: function 配额耗尽时, 5 key 同时收 429.
- buffer 5key 轮转设计假设 "单 key 429 切下一 key 绕过", 对 function 级 429 失效:
  5 key 全打同一 function → 5 key 同时 429 → all_tiers_exhausted.
- 设计盲区非 nv_gw 代码缺陷. R-nvonly 5key 5IP 设计针对 key/IP 级隔离, 未覆盖 function 级配额.
- 单波 429 证明是 NVCF function 配额周期自恢复 (12:20 恢复 1×200), 非 nv_gw 代码缺陷.
- KEYMGR 指数退避 (120→180→480s) 正常工作, 429 后 key 进入冷却, 配额恢复后 ProbeWorker 探测唤醒.
- avg_dur 2032s 是 all_tiers_exhausted 累积 KEYMGR 指数退避等待时长 (429 后 key 进入 120-600s 冷却, 配额恢复前全 key cooling).

### 结论
- **非 nv_gw 代码缺陷, 无需本轮改码**. NVCF function 级配额是上游硬限制.
- buffer 5key 轮转对 key/IP 级 429 仍有效 (R268-R356 验证), 对 function 级 429 是已知盲区.
- 当前 cc2 流量极低, all_tiers_exhausted 罕见且自恢复, 不达介入阈值.

## 判稳
- **NOP 巡检轮**. cc2 primary 0 req, 链路空闲健康, 0 fallback 0 deadline.
- dsv4p_nv 本轮 SR=14.3% (1/7), 较 R356 25.0% (2/8) 略低 (样本极小自然变动, +1 all_tiers_exhausted).
- 错误类型无新增, 与 R268-R356 一致 (八十轮一致).
- 八十轮一致 R268-R357.

## 下一步
- 继续 NOP 巡检, 等 cc2 流量恢复后观察 dsv4p_nv SR.
- 关注是否出现新错误类型 (非 all_tiers_exhausted/NVStream_IncompleteRead) 或 key/IP 级故障, 再决定是否介入.
- NVStream_IncompleteRead 若从偶发单发转为连续多发, 再评估 transport 错误分类/重试逻辑.

## 参数快照 (未变)
- cc4101: FALLBACK_UPSTREAM_URL=ms_gw:40007, CC4101_STREAM_TOTAL_DEADLINE_S=470, PRIMARY_HEADER_TIMEOUT=400, PRIMARY_UPSTREAM_MODEL=dsv4p_nv.
- nv_gw: NVU_DISABLE_MS_FALLBACK=0 (ms_gw fallback 已恢复), UPSTREAM_TIMEOUT=90, NVU_BUFFER_MAX_RETRIES=5 (90s×5=450s), TIER_COOLDOWN_S=180, KEY_COOLDOWN_S=30.
- KeyManager: 429→120-600s 指数退避; RemoteDisconnected→5-10s 短惩罚不累计 conn_count.
- deadline 链: 90s/buffer-attempt ×5 = 450s buffer < 470s cc4101 < 500s SDK idle.
