# R385: NOP 巡检轮 (cc2 0req, dsv4p_nv SR=90.0% 27/30, all_tiers_exhausted×3[2×429+1×502 avg 4559ms], 一百零九轮一致)

## 当前轮基线 (2026-08-02 22:33 CST, R384 已完成, R385 待跑)
- 本仓 master: R384 已 commit (01add5c). hermes 仓: R384 已 push (8764c54).
- **架构**: cc4101 `PRIMARY_UPSTREAM_MODEL=dsv4p_nv`. cc2 链路 = cc4101(dsv4p_nv) → nv_gw → NVCF.
- **本轮 R385 (hm2_cc2)**: NOP 巡检轮. cc2 (cc4101-primary) 30min 0 req (session 间歇空闲).
  dsv4p_nv 30min 全 caller SR=90.0% (27/30), 失败 3 = 3× all_tiers_exhausted
  (细分 2×429 + 1×502 NVCF dsv4p function 配额瞬时空位/上游瞬时错误, 全 0 fallback 非缓冲 caller).
  **cc2 是缓冲 caller (NVU_BUFFER_CALLERS), 走 buffer 5key 轮转路径, 不走 NV-TIER-SKIP, 不受影响.**
  错误类型无新增 (dsv4p 仍 all_tiers_exhausted, 一百零九轮一致 R268-R385).
  cc2 无流量不受影响, 0 fallback 0 deadline. 0 改动 0 restart. **一百零九轮一致 R268-R385**.
  ProbeWorker + KeyManager decayed reset 自恢复链实测有效.

## R-nvonly 核心铁律 (持续生效)
- 只改 HM2 nv_gw (40006), 不碰 HM1, 不碰 ms_gw 源码.
- ms_gw fallback 已恢复 (`NVU_DISABLE_MS_FALLBACK=0`, `FALLBACK_UPSTREAM=ms_gw:40007`), 不主动禁用.
- 改前有数据, 改后必验证, 写入仓库.

## 本轮关键数据 (30min 实时链路分析注入 ~22:33 CST)

### 1. cc2 (cc4101-primary) 30min 0 req
- session 间歇空闲, 链路空闲健康. 0 fallback 0 deadline.
- buffer/wait 日志 (BUFFER-/WAIT-) 30min 空 (无 buffer 流量).
- 30min caller×model×status 总览: hermes|dsv4p_nv|200|27, hermes|dsv4p_nv|429|2, hermes|dsv4p_nv|502|1.

### 2. dsv4p_nv 30min 全 caller SR=90.0% (27/30)
| caller | model | status | count | avg_dur |
|---|---|---|---|---|
| hermes | dsv4p_nv | 200 | 27 | 12138 |
| hermes | dsv4p_nv | 429 | 2 | 1477 |
| hermes | dsv4p_nv | 502 | 1 | 10722 |

per-key (dsv4p): key2 → 27×200 (12138); 空 key → 2×429 (1477) + 1×502 (10722).
per-egress: 203.10.96.139 → 27× (100%); 空 → 3× (0%).
finish_reason (200): tool_calls×23, stop×4 (无 zombie).
分钟趋势: 14:05 200×1, 14:06 200×4, 14:10 200×2, 14:11 200×5, 14:12 200×2, 14:15 200×2, 14:16 200×5, 14:17 200×4, 14:18 200×2, 14:20 429×1, 14:25 502×1, 14:30 429×1.
延迟 (200): avg_dur 12138, max 26336, min 2759, avg_ttfb 11594, avg_in 0, avg_out 0.
fallback f×30 (全部 false, 0 fallback).

### 3. 错误分类 (30min)
- 3 dsv4p 错误: 3× all_tiers_exhausted (avg 4559ms) — NVCF dsv4p function 配额瞬时空位/上游瞬时错误
  (tier 错误明细: 2×429 + 1×502, 502 为 NVCF 上游瞬时错误归入 all_tiers_exhausted 桶).
  - 本轮无 NV-TIER-SKIP (R384 0×, 本轮 0×, 自然波动).
  - 429/502: NVCF dsv4p function 配额瞬时空位/上游瞬时错误, 低频偶发 (3/30=10%), buffer 5key 轮转 + KeyManager 指数退避自恢复.
- dsv4p 错误类型集合与 R268-R384 一致 (all_tiers_exhausted, 无新增).
- buffer/wait 日志空.

### 4. 健康检查 (沿用 R384, 容器未重启)
- 容器全 Up: nv_gw 21h, cc4101 8h, nv_gw_stable 21h, ms_gw/logs_db 3 days.
- /health ok: nv_num_keys=5, pexec_models=[kimi_nv, dsv4p_nv, glm5_2_nv].
- 自恢复链 (ProbeWorker + KeyManager decayed reset + buffer 5key 轮转) 实测有效.

## 根因: NVCF dsv4p function 429/502 波 (非代码缺陷, 沿用 R353-R384 分析)

### 结论
- **非 nv_gw 代码缺陷, 无需本轮改码**.
- all_tiers_exhausted (429/502): NVCF dsv4p function 配额瞬时空位/上游瞬时错误, 低频偶发 (3/30=10%), buffer + KeyManager 指数退避 + ProbeWorker + decayed reset 自恢复 (R268-R384 验证).
- 本轮无 NV-TIER-SKIP 无 stream_first_byte_timeout, 错误面收敛.
- 当前 cc2 流量极低, 偶发错误罕见且自恢复, 不达介入阈值.

## 判稳
- **NOP 巡检轮**. cc2 primary 0 req, 链路空闲健康, 0 fallback 0 deadline.
- dsv4p_nv 本轮 SR=90.0% (27/30), 较 R384 93.8% (30/32) 略降 (样本极小自然波动,
  本轮成功 27 vs 30, 失败 3 vs 2, 全部非缓冲 caller, cc2 不受影响).
  dsv4p 错误类型无新增, 与 R268-R384 一致 (一百零九轮一致).

## 下一步
- 继续 NOP 巡检, 等 cc2 流量恢复后观察 dsv4p_nv SR (cc2 走 buffer 路径, 行为可能不同于非缓冲 caller).
- 关注是否出现新错误类型 (非 all_tiers_exhausted) 或 key/IP 级故障, 再决定是否介入.
- all_tiers_exhausted 若从低频偶发转为持续 429/502 波 (>=5/h), 再评估 buffer 轮转/KeyManager 退避参数.
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
