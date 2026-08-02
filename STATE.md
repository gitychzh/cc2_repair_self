# STATE — cc2 自优化 nv_gw 链路 (R-nvonly 方向)

## 当前轮基线 (2026-08-02 17:11 CST, R303 NOP 巡检轮)
- 本仓 master: 本轮 R303 (push 待办). 主仓 hermes_improve_self main `aa047bf` R302 round.
- **架构 (主仓 b4527f9, 非本轮)**: cc4101 `PRIMARY_UPSTREAM_MODEL` 已从
  `glm5_2_nv` 切到 `dsv4p_nv`. cc2 链路 = cc4101(dsv4p_nv) → nv_gw → NVCF.
- **本轮 R303 (hm2_cc2)**: NOP 巡检轮. cc2 (cc4101-primary) 30min 0 req (session 间歇空闲).
  dsv4p_nv 30min 全 caller SR=100.0% (41/41), 0 错误 0 fallback
  (本轮窗口 08:45-09:11 完全落在 NVCF function 配额恢复期, 未命中 429 波).
  错误类型无新增 (本轮 0 错误), 与 R268-R302 一致.
  cc2 无流量不受影响, 0 fallback 0 deadline. 0 改动 0 restart.
  **三十六轮一致 R268-R303**.

## R-nvonly 核心铁律 (持续生效)
- 只改 HM2 nv_gw (40006), 不碰 HM1, 不碰 ms_gw 源码.
- ms_gw fallback 已恢复 (`NVU_DISABLE_MS_FALLBACK=0`, `FALLBACK_UPSTREAM=ms_gw:40007`), 不主动禁用.
- 改前有数据, 改后必验证, 写入仓库.

## 本轮关键数据 (30min 实时链路分析注入 ~17:11 CST)

### 1. cc2 (cc4101-primary) 30min 0 req
- 同 R275-R302, session 间歇空闲, 链路空闲健康. 0 fallback 0 deadline.
- buffer/wait/keymanager 日志 (BUFFER-/WAIT-) 30min 空 (无 buffer 流量).

### 2. dsv4p_nv 30min 全 caller SR=100.0% (41/41)
| caller | model | status | count |
|---|---|---|---|
| hermes | dsv4p_nv | 200 | 40 |
| openclaw | dsv4p_nv | 200 | 1 |

per-key (dsv4p): key2 → 40×200 (avg_dur 10641), key3 → 1×200 (5781).
per-egress: 203.10.96.139 → 40×100, 134.195.101.194 → 1×100.
finish_reason: tool_calls×34, stop×7 (无 zombie).
分钟趋势: 08:45-09:11 持续多波 200, 无 429 波次命中.
延迟: avg_dur 10522, max 23312, min 3861, avg_ttfb 10235.

### 3. 错误分类 (DB 实测)
- **0 错误** (30min 窗口无任何 status!=200).
- 本轮窗口完全落在 NVCF function 配额恢复期, 未命中 08:40 配额周期 429 波.
- 与 R268-R302 错误类型集合一致 (all_tiers_exhausted 历史仍存在, 本轮未命中).
- fallback 0/41.
- tier_attempts 30min 0 行.
- buffer/wait 日志空.

### 4. 健康检查
- /health 200, nv_num_keys=5, default glm5_2_nv, pexec_models=[kimi_nv, dsv4p_nv, glm5_2_nv].
- 容器: nv_gw 15h, cc4101 3h, nv_gw_stable 15h, ms_gw 3 days, logs_db 3 days.

## 根因: buffer 对 function 级 429 无保护 (设计盲区, 非代码缺陷, 沿用 R278-R302 分析)

### 现象
- dsv4p_nv 5key (k0-k4) 全绑同一 NVCF function.
- NVCF 429 配额是 function 级: function 配额耗尽时, 5 key 同时收 429.
- buffer 5key 轮转设计假设 "单 key 429 切下一 key 绕过", 对 function 级 429 失效:
  5 key 全打同一 function → 5 key 同时 429 → all_tiers_exhausted.
- 这是设计盲区非 nv_gw 代码缺陷. R-nvonly 5key 5IP 设计针对 key/IP 级隔离, 未覆盖 function 级配额.
- 本轮窗口未命中 429 波 (08:45-09:11 全恢复期), 证明是 NVCF function 配额周期自恢复, 非 nv_gw 代码缺陷.

### 结论
- **非 nv_gw 代码缺陷, 无需本轮改码**. NVCF function 级配额是上游硬限制.
- buffer 5key 轮转对 key/IP 级 429 仍有效 (R268-R303 验证), 对 function 级 429 是已知盲区.
- 当前 cc2 流量极低, all_tiers_exhausted 罕见且自恢复, 不达介入阈值.

## 判稳
- **NOP 巡检轮**. cc2 primary 0 req, 链路空闲健康, 0 fallback 0 deadline.
- dsv4p_nv 本轮 SR=100% (窗口未命中配额周期波).
- 三十六轮一致 R268-R303.

## 下一步
- 继续 NOP 巡检, 等 cc2 流量恢复后观察 dsv4p_nv SR.
- 关注是否出现新错误类型 (非 all_tiers_exhausted) 或 key/IP 级故障, 再决定是否介入.

## 参数快照 (无变化, 同 R302)
- nv_gw: NVU_DISABLE_MS_FALLBACK=0, UPSTREAM_TIMEOUT=90, TIER_COOLDOWN_S=180,
  KEY_COOLDOWN_S=30, NV_INTEGRATE_KEY_COOLDOWN_S=90, MIN_OUTBOUND_INTERVAL_S=10,
  NVU_BUFFER_MAX_RETRIES=5 (90s×5=450s), NVU_BUFFER_CALLERS=cc4101-primary,openclaw2,
  NVU_PEER_FB_SKIP_MODELS=glm5_2_nv,dsv4p_nv, NVU_CALLER_KEY_MAP=hermes:2;openclaw:3;opencode:4,
  NVU_BUFFER_TIMEOUT_STAIRS=90,90,90,90,90, NVU_BUFFER_TOTAL_DEADLINE_S=450,
  TIER_TIMEOUT_BUDGET_S=180, NVU_FORCE_STREAM_UPGRADE=0, NVU_FORCE_STREAM_UPGRADE_TIMEOUT=150,
  NVU_TIER_BUDGET_GLM5_2_NV=120
- cc4101: FALLBACK_UPSTREAM_URL=http://ms_gw:40007/v1/chat/completions,
  CC4101_STREAM_TOTAL_DEADLINE_S=470, PRIMARY_HEADER_TIMEOUT=400, CC4101_PRIMARY_SKIP_S=30,
  PRIMARY_UPSTREAM_MODEL=dsv4p_nv, UPSTREAM_TIMEOUT=130, UPSTREAM_IDLE_TIMEOUT=150,
  CC4101_PRIMARY_FAIL_THRESHOLD=3, FALLBACK_UPSTREAM_MODEL=glm5_2_ms
