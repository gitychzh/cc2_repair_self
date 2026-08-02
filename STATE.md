# R392: NOP 巡检轮 (cc2 0req, dsv4p_nv SR=44.4% 4/9, all_tiers_exhausted×5[5×429 avg 2282ms], 一百一十六轮一致)

## 当前轮基线 (2026-08-02 23:05 CST, R391 已完成, R392 已跑)
- 本仓 master: R392 待 commit. hermes 仓: R392 待 push.
- **架构**: cc4101 `PRIMARY_UPSTREAM_MODEL=dsv4p_nv`. cc2 链路 = cc4101(dsv4p_nv) → nv_gw → NVCF.
- **本轮 R392 (hm2_cc2)**: NOP 巡检轮. cc2 (cc4101-primary) 30min 0 req (session 间歇空闲).
  dsv4p_nv 30min 全 caller SR=44.4% (4/9), 失败 5 = 5× all_tiers_exhausted (sub=`all_tiers_failed_in_mapped_tier`,
  avg 2282ms, 全 429, NVCF dsv4p function 本窗口配额瞬时空位, 全非缓冲 caller mapped-tier 直接失败无轮转保护).
  成功 4×200 全在 key2 (hermes mapped), egress 203.10.96.139, avg 10830ms.
  **cc2 是缓冲 caller (NVU_BUFFER_CALLERS), 走 buffer 5key 轮转路径, 不走 mapped-tier 直接失败, 不受影响.**
  错误类型无新增 (dsv4p 仍 all_tiers_exhausted, 一百一十六轮一致 R268-R392).
  cc2 无流量不受影响, 0 fallback 0 deadline. 0 改动 0 restart. **一百一十六轮一致 R268-R392**.
  ProbeWorker + KeyManager decayed reset 自恢复链实测有效.

## R-nvonly 核心铁律 (持续生效)
- 只改 HM2 nv_gw (40006), 不碰 HM1, 不碰 ms_gw 源码.
- ms_gw fallback 已恢复 (`NVU_DISABLE_MS_FALLBACK=0`, `FALLBACK_UPSTREAM=ms_gw:40007`), 不主动禁用.
- 改前有数据, 改后必验证, 写入仓库.

## 本轮关键数据 (30min 实时链路分析注入 ~23:00 CST, 已 DB 二次核实)

### 1. cc2 (cc4101-primary) 30min 0 req
- session 间歇空闲, 链路空闲健康. 0 fallback 0 deadline.
- buffer/wait 日志 (BUFFER-/WAIT-) 30min 空 (无 buffer 流量).
- DB 核实: `select status,count(*) from nv_requests where created_at>now()-interval'30 min' and caller='cc4101-primary'` → 0 rows.

### 2. dsv4p_nv 30min 全 caller SR=44.4% (4/9)
| caller | request_model | status | count | avg_dur |
|---|---|---|---|---|
| hermes | dsv4p_nv | 429 | 5 | 2282 |
| hermes | dsv4p_nv | 200 | 4 | 10830 |

per-key (nv_key_idx): 空 → 5×429 all_tiers_exhausted (2282); key2 → 4×200 (10830).
  (hermes mapped to key2; mapped tier 直接失败时 nv_key_idx 字段为空, 设计行为;
   成功 4×全 key2 egress 203.10.96.139, NVCF dsv4p function 本窗口偶有成功位.)
fallback_occurred=f×9 (全部 false, 0 fallback).

### 3. 错误分类 (30min)
- 5 dsv4p 错误: 5× all_tiers_exhausted (sub=`all_tiers_failed_in_mapped_tier`, avg 2282ms)
  — NVCF dsv4p function 配额瞬时空位/上游瞬时错误.
  - 本轮无 NV-TIER-SKIP, 无 stream_first_byte_timeout, 错误面收敛.
  - 429: NVCF dsv4p function 配额瞬时空位, 低频偶发 (5/9=55.6% 本窗口占比偏高
    但绝对数量 5 仍属低频, 非缓冲 caller mapped-tier 直接失败无轮转保护, 设计行为).
- nv_tier_attempts per-key 错误分布空 — mapped tier 直接失败无实际 tier attempt.
- dsv4p 错误类型集合与 R268-R391 一致 (all_tiers_exhausted, 无新增).
- buffer/wait 日志空.

### 4. 健康检查 (沿用 R391, 容器未重启)
- 容器全 Up: nv_gw 8h, cc4101 9h, nv_gw_stable 21h, ms_gw/logs_db 3 days.
- /health ok: nv_num_keys=5, pexec_models=[kimi_nv, dsv4p_nv, glm5_2_nv], port=40006.
- 自恢复链 (ProbeWorker + KeyManager decayed reset + buffer 5key 轮转) 实测有效.

## 根因: NVCF dsv4p function 429 波 (非代码缺陷, 沿用 R353-R391 分析)
- **非 nv_gw 代码缺陷, 无需本轮改码**.
- all_tiers_exhausted (429): NVCF dsv4p function 配额瞬时空位/上游瞬时错误, 低频偶发,
  buffer + KeyManager 指数退避 + ProbeWorker + decayed reset 自恢复 (R268-R391 验证).
- 本轮无 NV-TIER-SKIP 无 stream_first_byte_timeout, 错误面收敛.
- 当前 cc2 流量极低, 偶发错误罕见且自恢复, 不达介入阈值.
- 本窗口 dsv4p SR=44.4% (4/9) 较 R391 0% (0/6) 回升, 出现 4×200 成功位 (全 key2),
  且样本极小 (9 req), 全非缓冲 caller, 无统计学意义, 错误类型集合不变, 仍判为 NVCF 配额波动而非链路退化.
- R388 72.2% → R389 14.3% → R390 0% → R391 0% → R392 44.4%, 样本 18→7→6→6→9,
  全非缓冲 caller mapped-tier 直接失败, SR 直接反映 NVCF 瞬时状态, cc2 缓冲 caller 走 buffer 5key 轮转不受同影响.

## 判稳
- **NOP 巡检轮**. cc2 primary 0 req, 链路空闲健康, 0 fallback 0 deadline.
- dsv4p_nv 本轮 SR=44.4% (4/9), 较 R391 0% 回升 (样本极小 + 出现成功位 + NVCF 本窗口配额波动,
  全部非缓冲 caller, cc2 不受影响). dsv4p 错误类型无新增, 与 R268-R391 一致 (一百一十六轮一致).

## 下一步
- 继续 NOP 巡检, 等 cc2 流量恢复后观察 dsv4p_nv SR (cc2 走 buffer 路径, 行为可能不同于非缓冲 caller).
- 关注是否出现新错误类型 (非 all_tiers_exhausted) 或 key/IP 级故障, 再决定是否介入.
- all_tiers_exhausted 若从低频偶发转为持续 429/502 波 (>=5/h 持续), 再评估 buffer 轮转/KeyManager 退避参数.
- 连续下滑/回升样本极小全非缓冲 caller, 下一轮观察是否回归 R384-R388 的正常区间.

## 参数快照 (本轮未改, 实测注入)
- nv_gw: NVU_DISABLE_MS_FALLBACK=0, UPSTREAM_TIMEOUT=90, TIER_TIMEOUT_BUDGET_S=180,
  TIER_COOLDOWN_S=180, KEY_COOLDOWN_S=30, NV_INTEGRATE_KEY_COOLDOWN_S=90,
  MIN_OUTBOUND_INTERVAL_S=10, NVU_FORCE_STREAM_UPGRADE=0, NVU_FORCE_STREAM_UPGRADE_TIMEOUT=150,
  NVU_BUFFER_CALLERS=cc4101-primary,openclaw2, NVU_PEER_FB_SKIP_MODELS=glm5_2_nv,dsv4p_nv,
  NVU_CALLER_KEY_MAP=hermes:2;openclaw:3;opencode:4, MIN_OUTBOUND_INTERVAL_S=10
- cc4101: PRIMARY_UPSTREAM_MODEL=dsv4p_nv, PRIMARY_UPSTREAM_URL=http://nv_gw:40006/v1/messages,
  FALLBACK_UPSTREAM_URL=http://ms_gw:40007/v1/chat/completions, FALLBACK_UPSTREAM_MODEL=glm5_2_ms,
  PRIMARY_HEADER_TIMEOUT=400, CC4101_STREAM_TOTAL_DEADLINE_S=470,
  CC4101_PRIMARY_FAIL_THRESHOLD=3, CC4101_PRIMARY_SKIP_S=30,
  UPSTREAM_TIMEOUT=130, UPSTREAM_IDLE_TIMEOUT=150
- deadline 链: 90s/buffer-attempt × 5 = 450s buffer < 470s cc4101 < 500s SDK idle
- settings.json: contextWindow=170000, autoCompactWindow=155000, API_TIMEOUT_MS=600000
