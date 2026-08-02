# STATE — cc2 自优化 nv_gw 链路 (R-nvonly 方向)

## 当前轮基线 (2026-08-02 ~19:05 CST, R333 NOP 巡检轮)
- 本仓 master: 上轮 R332 (6c97363) 已 push. 本仓 up to date.
- **架构**: cc4101 `PRIMARY_UPSTREAM_MODEL=dsv4p_nv`. cc2 链路 = cc4101(dsv4p_nv) → nv_gw → NVCF.
- **本轮 R333 (hm2_cc2)**: NOP 巡检轮. cc2 (cc4101-primary) 30min 0 req (session 间歇空闲).
  dsv4p_nv 30min 全 caller SR=66.7% (10/15): 10:35-10:50 一波 429×4 (NVCF function 配额周期)
  → 10:55-10:56 自恢复 5×200 → 10:58 1×502(all_tiers_exhausted) → 11:00-11:01 恢复 5×200.
  key2 10×200 (avg_dur 10189, dsv4p 高延迟特性).
  本轮 30min 注入窗口内无 NVStream_IncompleteRead (60min 窗口外 10:06:55 有 1 次, 历史已知偶发, 非新类型).
  错误类型无新增, 与 R268-R332 一致.
  cc2 无流量不受影响, 0 fallback 0 deadline. 0 改动 0 restart.
  **六十六轮一致 R268-R333**.

## R-nvonly 核心铁律 (持续生效)
- 只改 HM2 nv_gw (40006), 不碰 HM1, 不碰 ms_gw 源码.
- ms_gw fallback 已恢复 (`NVU_DISABLE_MS_FALLBACK=0`, `FALLBACK_UPSTREAM=ms_gw:40007`), 不主动禁用.
- 改前有数据, 改后必验证, 写入仓库.

## 本轮关键数据 (30min 实时链路分析注入 ~19:01 CST)

### 1. cc2 (cc4101-primary) 30min 0 req
- 同 R275-R332, session 间歇空闲, 链路空闲健康. 0 fallback 0 deadline.
- buffer/wait 日志 (BUFFER-/WAIT-) 30min 空 (无 buffer 流量).

### 2. dsv4p_nv 30min 全 caller SR=66.7% (10/15)
| caller | model | status | count |
|---|---|---|---|
| hermes | dsv4p_nv | 200 | 9 |
| hermes | dsv4p_nv | 429 | 4 |
| hermes | dsv4p_nv | 502 | 1 |

- per-key (dsv4p): key2 → 10×200 (avg_dur 10189, max 21379, min 5388, avg_ttfb 9865);
  空 key → 4×429 (avg_dur 1450, KEYMGR 阶段即拦, 无 egress) + 1×502 (72.3s).
- per-egress: 203.10.96.139 → 10×100% (key2 成功路径); 空 IP → 5×0 (429/502 路径无 egress).
- 分钟趋势: 10:35-10:50 一波 429×4 (每 5min 1 发, NVCF function 配额周期)
  → 10:55-10:56 恢复 5×200 → 10:58 1×502 → 11:00-11:01 恢复 5×200.
- fallback 0/15. finish_reason: tool_calls×9 + stop×1 (200 路径正常).

### 3. 错误分类 (DB 实测)
- 5 错误 (30min 窗口): 5× all_tiers_exhausted (sub=all_tiers_failed_in_mapped_tier, avg_dur 15619).
  注入数据 "502×1 avg_dur 72299" 为 60min 窗口聚合; 30min 窗口内实际为
  1× all_tiers_exhausted (afb4b9be, 72.3s, key_idx 空, egress 空).
- 本轮 30min 注入窗口内无 NVStream_IncompleteRead.
  60min 窗口外 (10:06:55) 有 1× NVStream_IncompleteRead (08c0d050, key2, egress 203.10.96.139, 34s)
  — 历史已知偶发 mid-stream 软挂单发, 非新错误类型, 与 R325 同源.
- 与 R268-R332 错误类型集合一致.
- tier_attempts 30min 0 行 (429 在 NVCF 侧, 未进入 nv_gw tier 重试).
- buffer/wait 日志空.

### 4. 健康检查 (沿用 R332 实测, 本轮 0 改动 0 restart)
- /health 200, nv_num_keys=5, default glm5_2_nv, pexec_models=[kimi_nv, dsv4p_nv, glm5_2_nv].
- 容器全 Up: nv_gw/cc4101 Up 4-5h, nv_gw_stable Up 17h, ms_gw/logs_db Up 3d+.

## 根因: buffer 对 function 级 429 无保护 (设计盲区, 非代码缺陷, 沿用 R278-R332 分析)

### 现象
- dsv4p_nv 5key (k0-k4) 全绑同一 NVCF function.
- NVCF 429 配额是 function 级: function 配额耗尽时, 5 key 同时收 429.
- buffer 5key 轮转设计假设 "单 key 429 切下一 key 绕过", 对 function 级 429 失效:
  5 key 全打同一 function → 5 key 同时 429 → all_tiers_exhausted.
- 这是设计盲区非 nv_gw 代码缺陷. R-nvonly 5key 5IP 设计针对 key/IP 级隔离, 未覆盖 function 级配额.
- 本轮 10:35-10:50 一波 429×4 → 10:55-11:01 恢复 10×200 证明是 NVCF function 配额周期自恢复, 非 nv_gw 代码缺陷.
- KEYMGR 指数退避 (120→180→480s) 正常工作, 429 后 key 进入冷却, 配额恢复后 ProbeWorker 探测唤醒.

### 结论
- **非 nv_gw 代码缺陷, 无需本轮改码**. NVCF function 级配额是上游硬限制.
- buffer 5key 轮转对 key/IP 级 429 仍有效 (R268-R333 验证), 对 function 级 429 是已知盲区.
- 当前 cc2 流量极低, all_tiers_exhausted 罕见且自恢复, 不达介入阈值.

## 判稳
- **NOP 巡检轮**. cc2 primary 0 req, 链路空闲健康, 0 fallback 0 deadline.
- dsv4p_nv 本轮 SR=66.7% (10/15): 窗口命中 1 波 429×4 后自恢复 10×200, 根因不变 (NVCF function 配额周期).
- 错误类型无新增, 与 R268-R332 一致.
- 六十六轮一致 R268-R333.

## 下一步
- 继续 NOP 巡检, 等 cc2 流量恢复后观察 dsv4p_nv SR.
- 关注是否出现新错误类型 (非 all_tiers_exhausted/NVStream_IncompleteRead) 或 key/IP 级故障, 再决定是否介入.
- 持续观察 NVStream_IncompleteRead 是否从偶发转为频发 (目前 60min 1 次, 仍属偶发).

## 参数快照 (R333, 沿用主仓, 无改动)
- cc4101: FALLBACK_UPSTREAM_URL=http://ms_gw:40007/v1/chat/completions, CC4101_STREAM_TOTAL_DEADLINE_S=470, PRIMARY_HEADER_TIMEOUT=400, PRIMARY_UPSTREAM_MODEL=dsv4p_nv, UPSTREAM_TIMEOUT=130.
- nv_gw: NVU_DISABLE_MS_FALLBACK=0, UPSTREAM_TIMEOUT=90, TIER_TIMEOUT_BUDGET_S=180, TIER_COOLDOWN_S=180, KEY_COOLDOWN_S=30, NVU_BUFFER_MAX_RETRIES=5 (5×90s=450s), NVU_BUFFER_TOTAL_DEADLINE_S=450, NV_INTEGRATE_KEY_COOLDOWN_S=90, NVU_BUFFER_CALLERS=cc4101-primary,openclaw2.
- deadline 链: 90s/buffer-attempt × 5 = 450s buffer < 470s cc4101 < 500s SDK idle (API_TIMEOUT_MS=600000).
