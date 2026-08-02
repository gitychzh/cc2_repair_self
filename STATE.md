# STATE — cc2 自优化 nv_gw 链路 (R-nvonly 方向)

## 当前轮基线 (2026-08-02 17:57 CST, R315 NOP 巡检轮)
- 本仓 master: 上轮 R314 (1e48554) 已 push. 本轮 R315 NOP 巡检, 不改码.
- **架构 (主仓 1e48554)**: cc4101 `PRIMARY_UPSTREAM_MODEL=dsv4p_nv`.
  cc2 链路 = cc4101(dsv4p_nv) → nv_gw → NVCF.
- **本轮 R315 (hm2_cc2)**: NOP 巡检轮. cc2 (cc4101-primary) 30min 0 req (session 间歇空闲).
  dsv4p_nv 30min 全 caller SR=73.3% (11/15), 失败 4 全 all_tiers_exhausted
  (09:30+09:35+09:45+09:50 四波 429 NVCF function 配额周期, 5key 同时挂, 自恢复).
  错误类型无新增 (全 all_tiers_exhausted), 与 R268-R314 一致.
  cc2 无流量不受影响, 0 fallback 0 deadline. 0 改动 0 restart.
  **四十八轮一致 R268-R315**.

## R-nvonly 核心铁律 (持续生效)
- 只改 HM2 nv_gw (40006), 不碰 HM1, 不碰 ms_gw 源码.
- ms_gw fallback 已恢复 (`NVU_DISABLE_MS_FALLBACK=0`, `FALLBACK_UPSTREAM=ms_gw:40007`), 不主动禁用.
- 改前有数据, 改后必验证, 写入仓库.

## 本轮关键数据 (30min 实时链路分析注入 ~17:57 CST)

### 1. cc2 (cc4101-primary) 30min 0 req
- 同 R275-R314, session 间歇空闲, 链路空闲健康. 0 fallback 0 deadline.
- buffer/wait 日志 (BUFFER-/WAIT-) 30min 空 (无 buffer 流量).

### 2. dsv4p_nv 30min 全 caller SR=73.3% (11/15)
| caller | model | status | count |
|---|---|---|---|
| hermes | dsv4p_nv | 200 | 11 |
| hermes | dsv4p_nv | 429 | 4 |

per-key (dsv4p): key2 → 11×200 (avg_dur 11554), 空 key → 4×429 (1675).
per-egress: 203.10.96.139 → 11×100, 空 IP → 4×0 (429).
finish_reason: tool_calls×9, stop×2 (无 zombie).
分钟趋势: 09:30/09:35/09:45/09:50 四波 429, 09:40-09:41 恢复 8×200 + 09:55-09:56 恢复 3×200 (配额周期自恢复).
延迟 (200): avg_dur 11554, max 32671, min 4669, avg_ttfb 10904.
fallback 0/15.

### 3. 错误分类 (DB 实测)
- 4 错误: 全 all_tiers_exhausted (avg_dur 1675, sub=all_tiers_failed_in_mapped_tier).
- 09:30+09:35+09:45+09:50 四波 429 → 5key 同 function 同时挂 → all_tiers_exhausted.
- 与 R268-R314 错误类型集合一致 (all_tiers_exhausted 历史仍存在).
- tier_attempts 30min 0 行 (429 在 NVCF 侧, 未进入 nv_gw tier 重试).
- buffer/wait 日志空.

### 4. 健康检查
- /health 200, nv_num_keys=5, default glm5_2_nv, pexec_models=[kimi_nv, dsv4p_nv, glm5_2_nv].
- 容器: nv_gw, cc4101, ms_gw, logs_db 全部 Up.
- env 实测: NVU_DISABLE_MS_FALLBACK=0, UPSTREAM_TIMEOUT=90, NVU_BUFFER_MAX_RETRIES=5,
  TIER_COOLDOWN_S=180, KEY_COOLDOWN_S=30.

## 根因: buffer 对 function 级 429 无保护 (设计盲区, 非代码缺陷, 沿用 R278-R314 分析)

### 现象
- dsv4p_nv 5key (k0-k4) 全绑同一 NVCF function.
- NVCF 429 配额是 function 级: function 配额耗尽时, 5 key 同时收 429.
- buffer 5key 轮转设计假设 "单 key 429 切下一 key 绕过", 对 function 级 429 失效:
  5 key 全打同一 function → 5 key 同时 429 → all_tiers_exhausted.
- 这是设计盲区非 nv_gw 代码缺陷. R-nvonly 5key 5IP 设计针对 key/IP 级隔离, 未覆盖 function 级配额.
- 本轮 09:30+09:35+09:45+09:50 四波 429 证明是 NVCF function 配额周期自恢复, 非 nv_gw 代码缺陷.
- KEYMGR 指数退避 (120→180→480s) 正常工作, 429 后 key 进入冷却, 配额恢复后 ProbeWorker 探测唤醒.

### 结论
- **非 nv_gw 代码缺陷, 无需本轮改码**. NVCF function 级配额是上游硬限制.
- buffer 5key 轮转对 key/IP 级 429 仍有效 (R268-R315 验证), 对 function 级 429 是已知盲区.
- 当前 cc2 流量极低, all_tiers_exhausted 罕见且自恢复, 不达介入阈值.

## 判稳
- **NOP 巡检轮**. cc2 primary 0 req, 链路空闲健康, 0 fallback 0 deadline.
- dsv4p_nv 本轮 SR=73.3% (11/15) (窗口命中四波 429, NVCF function 配额周期; 总 req 15 少, 故 SR 数值偏低但根因不变).
- 错误类型无新增 (全 all_tiers_exhausted), 与 R268-R314 一致.
- 四十八轮一致 R268-R315.

## 下一步
- 继续 NOP 巡检, 等 cc2 流量恢复后观察 dsv4p_nv SR.
- 关注是否出现新错误类型 (非 all_tiers_exhausted) 或 key/IP 级故障, 再决定是否介入.

## 参数快照 (无变化, 同 R314)
- nv_gw: NVU_DISABLE_MS_FALLBACK=0, UPSTREAM_TIMEOUT=90, TIER_COOLDOWN_S=180,
  KEY_COOLDOWN_S=30, NV_INTEGRATE_KEY_COOLDOWN_S=90, MIN_OUTBOUND_INTERVAL_S=10,
  NVU_BUFFER_MAX_RETRIES=5 (90s×5=450s), NVU_BUFFER_CALLERS=cc4101-primary,openclaw2,
  NVU_PEER_FB_SKIP_MODELS=glm5_2_nv,dsv4p_nv, NVU_CALLER_KEY_MAP=hermes:2;openclaw:3;opencode:4,
  NVU_BUFFER_TIMEOUT_STAIRS=90,90,90,90,90, NVU_BUFFER_TOTAL_DEADLINE_S=450,
  NVU_FORCE_STREAM_UPGRADE=0, NVU_FORCE_STREAM_UPGRADE_TIMEOUT=150, TIER_TIMEOUT_BUDGET_S=180.
- cc4101: FALLBACK_UPSTREAM_URL=http://ms_gw:40007/v1/chat/completions, PRIMARY_HEADER_TIMEOUT=400,
  CC4101_STREAM_TOTAL_DEADLINE_S=470, PRIMARY_UPSTREAM_MODEL=dsv4p_nv, UPSTREAM_TIMEOUT=130,
  CC4101_PRIMARY_SKIP_S=30, CC4101_PRIMARY_FAIL_THRESHOLD=3.
