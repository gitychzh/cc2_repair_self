# R376: NOP 巡检轮 (cc2 0req, dsv4p_nv SR=41.7% 5/12, all_tiers_exhausted×7[5×429+2×NV-TIER-SKIP 1ms] + stream_first_byte_timeout×1, 九十九轮一致)

## 当前轮基线 (2026-08-02 22:01 CST, R376 已完成, R377 待跑)
- 本仓 master: R375 已 push (cb26150). hermes 仓: R376 待 push.
- **架构**: cc4101 `PRIMARY_UPSTREAM_MODEL=dsv4p_nv`. cc2 链路 = cc4101(dsv4p_nv) → nv_gw → NVCF.
- **本轮 R376 (hm2_cc2)**: NOP 巡检轮. cc2 (cc4101-primary) 30min 0 req (session 间歇空闲).
  dsv4p_nv 30min 全 caller SR=41.7% (5/12), 失败 7 = 7× all_tiers_exhausted
  (细分 4×429 avg 1895ms NVCF dsv4p function 配额瞬时空位 + 3×502 avg 1ms NV-TIER-SKIP 全 cooling 瞬拒, 均 0ms/1ms 快速失败非缓冲 caller)
  + 1× stream_first_byte_timeout (glm5_2_nv other caller 单发 502 29952ms, 非 cc2 流量).
  **cc2 是缓冲 caller (NVU_BUFFER_CALLERS), 走 buffer 5key 轮转路径, 不走 NV-TIER-SKIP, 不受影响.**
  错误类型无新增 (dsv4p 仍 all_tiers_exhausted, glm5_2_nv stream_first_byte_timeout, 九十九轮一致 R268-R376).
  cc2 无流量不受影响, 0 fallback 0 deadline. 0 改动 0 restart. **九十九轮一致 R268-R376**.
  ProbeWorker + KeyManager decayed reset 自恢复链实测有效 (22:01 k3 cooling 恢复后首次尝试即 NV-SUCCESS).

## R-nvonly 核心铁律 (持续生效)
- 只改 HM2 nv_gw (40006), 不碰 HM1, 不碰 ms_gw 源码.
- ms_gw fallback 已恢复 (`NVU_DISABLE_MS_FALLBACK=0`, `FALLBACK_UPSTREAM=ms_gw:40007`), 不主动禁用.
- 改前有数据, 改后必验证, 写入仓库.

## 本轮关键数据 (30min 实时链路分析注入 ~22:01 CST)

### 1. cc2 (cc4101-primary) 30min 0 req
- session 间歇空闲, 链路空闲健康. 0 fallback 0 deadline.
- buffer/wait 日志 (BUFFER-/WAIT-) 30min 空 (无 buffer 流量, 仅 NV-TIER-SKIP/NV-SUCCESS 日志活跃).

### 2. dsv4p_nv 30min 全 caller SR=41.7% (5/12)
| caller | model | status | count | avg_dur |
|---|---|---|---|---|
| hermes | dsv4p_nv | 200 | 5 | 9675 |
| hermes | dsv4p_nv | 429 | 4 | 1895 |
| other | dsv4p_nv | 502 | 3 | 1 |
| other | glm5_2_nv | 200 | 1 | — |
| other | glm5_2_nv | 502 | 1 | 29952 |

per-key (dsv4p): key2 → 5×200 (9675); 空 key → 4×429 (1895) + 3×502 (1).
per-egress: 203.10.96.139 → 5× (100); 空 → 7× (0).
finish_reason (200): tool_calls×4, stop×1 (无 zombie).
分钟趋势: 13:33 502×3 (1ms NV-TIER-SKIP), 13:35 429×1, 13:40 200×1, 13:41 200×2, 13:45 429×1, 13:50 429×1, 13:55 429×1, 14:00 200×1, 14:01 200×1.
延迟 (200): avg_dur 9675, max 13595, min 5680, avg_ttfb 8541, avg_in 0, avg_out 0.
fallback f×14 (全部 false, 0 fallback).

### 3. 错误分类 (30min)
- 7 dsv4p 错误: 7× all_tiers_exhausted (avg 1083ms) — 细分: 4×429 (1895ms, NVCF dsv4p function 配额瞬时空位) + 3×502 (1ms, NV-TIER-SKIP 全 cooling 瞬拒).
  - NV-TIER-SKIP (upstream.py:1676-1693): 全 5 key cooling 时直接 continue 跳过 tier, 0 attempt 0ms→1ms 502.
    发生在 agent_type=_nv 非缓冲 caller. cc2 缓冲 caller 不受影响.
  - 429: NVCF dsv4p function 配额瞬时空位, 低频偶发, buffer 5key 轮转 + KeyManager 指数退避自恢复.
- 1 glm5_2_nv 错误: stream_first_byte_timeout (502, 29952ms, other caller, 非 cc2 流量, 单发).
- dsv4p 错误类型集合与 R268-R375 一致 (all_tiers_exhausted, 无新增).
- buffer/wait 日志空.

### 4. 健康检查
- 容器全 Up: nv_gw 7h, cc4101 8h, nv_gw_stable 20h, ms_gw/logs_db 持续.
- curl /health: status=ok, 5 keys, nvcf_pexec_models=[kimi_nv,dsv4p_nv,glm5_2_nv].
- 日志实测自恢复: 21:33 NV-TIER-SKIP ×3 → 22:01 NV-PEEK-RETRY k3 → NV-SUCCESS first attempt (ProbeWorker + decayed reset 有效).

## 根因: NVCF dsv4p function 429 波 + NV-TIER-SKIP (非代码缺陷, 沿用 R353-R375 分析)

### 结论
- **非 nv_gw 代码缺陷, 无需本轮改码**.
- NV-TIER-SKIP 是全 cooling 时的快速失败路径, 对非缓冲 caller 设计如此 (不等 NVCF 恢复, 快速返 5xx 让上层决策).
  cc2 缓冲 caller 不受影响 (走 buffer 5key 轮转 + WaitQueue).
- all_tiers_exhausted (429): NVCF dsv4p function 配额瞬时空位, 低频偶发, buffer + KeyManager 指数退避 + ProbeWorker + decayed reset 自恢复 (R268-R375 验证, 本轮 22:01 k3 NV-SUCCESS 实测).
- stream_first_byte_timeout 是 glm5_2_nv other caller 单发, 非 cc2 流量, 自恢复.
- 当前 cc2 流量极低, 偶发错误罕见且自恢复, 不达介入阈值.

## 判稳
- **NOP 巡检轮**. cc2 primary 0 req, 链路空闲健康, 0 fallback 0 deadline.
- dsv4p_nv 本轮 SR=41.7% (5/12), 较 R375 27.3% (3/11) 上升 (样本极小自然波动,
  本轮成功 5 vs 3, 失败 7 vs 8, 全部非缓冲 caller, cc2 不受影响).
  dsv4p 错误类型无新增, 与 R268-R375 一致 (九十九轮一致).

## 下一步
- 继续 NOP 巡检, 等 cc2 流量恢复后观察 dsv4p_nv SR (cc2 走 buffer 路径, 行为可能不同于非缓冲 caller).
- 关注是否出现新错误类型 (非 all_tiers_exhausted/stream_first_byte_timeout) 或 key/IP 级故障, 再决定是否介入.
- all_tiers_exhausted 若从低频偶发转为持续 429 波 (>=5/h), 再评估 buffer 轮转/KeyManager 退避参数.
- NV-TIER-SKIP 若在 cc2 缓冲 caller 上出现 (理论上不应, 因 cc2 走 buffer), 再评估 buffer 与 NV-TIER-SKIP 路径关系.

## 参数快照 (本轮未改, 实测注入)
- nv_gw: NVU_DISABLE_MS_FALLBACK=0, UPSTREAM_TIMEOUT=90, TIER_TIMEOUT_BUDGET_S=180,
  TIER_COOLDOWN_S=180, KEY_COOLDOWN_S=30, NV_INTEGRATE_KEY_COOLDOWN_S=90,
  MIN_OUTBOUND_INTERVAL_S=10, NVU_FORCE_STREAM_UPGRADE=0, NVU_FORCE_STREAM_UPGRADE_TIMEOUT=150,
  NVU_BUFFER_CALLERS=cc4101-primary,openclaw2, NVU_PEER_FB_SKIP_MODELS=glm5_2_nv,dsv4p_nv,
  NVU_CALLER_KEY_MAP=hermes:2;openclaw:3;opencode:4
- cc4101: PRIMARY_UPSTREAM_MODEL=dsv4p_nv, PRIMARY_UPSTREAM_URL=http://nv_gw:40006/v1/messages,
  FALLBACK_UPSTREAM_URL=http://ms_gw:40007/v1/chat/completions, FALLBACK_UPSTREAM_MODEL=glm5_2_ms,
  CC4101_STREAM_TOTAL_DEADLINE_S=470, PRIMARY_HEADER_TIMEOUT=400, UPSTREAM_TIMEOUT=130,
  UPSTREAM_IDLE_TIMEOUT=150, CC4101_PRIMARY_SKIP_S=30, CC4101_PRIMARY_FAIL_THRESHOLD=3
