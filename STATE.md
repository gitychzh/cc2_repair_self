# R389: NOP 巡检轮 (cc2 0req, dsv4p_nv SR=14.3% 1/7, all_tiers_exhausted×6[5×429+1×502 avg 3286ms], 一百一十三轮一致)

## 当前轮基线 (2026-08-02 22:50 CST, R388 已完成, R389 待跑)
- 本仓 master: R388 已 commit (338abc8). hermes 仓: R388 已 push (ad8ba10).
- **架构**: cc4101 `PRIMARY_UPSTREAM_MODEL=dsv4p_nv`. cc2 链路 = cc4101(dsv4p_nv) → nv_gw → NVCF.
- **本轮 R389 (hm2_cc2)**: NOP 巡检轮. cc2 (cc4101-primary) 30min 0 req (session 间歇空闲).
  dsv4p_nv 30min 全 caller SR=14.3% (1/7), 失败 6 = 6× all_tiers_exhausted
  (细分 5×429 + 1×502 NVCF dsv4p function 本窗口配额紧张/上游瞬时错误, 全 0 fallback 非缓冲 caller).
  **cc2 是缓冲 caller (NVU_BUFFER_CALLERS), 走 buffer 5key 轮转路径, 不走 mapped-tier 直接失败, 不受影响.**
  错误类型无新增 (dsv4p 仍 all_tiers_exhausted, 一百一十三轮一致 R268-R389).
  cc2 无流量不受影响, 0 fallback 0 deadline. 0 改动 0 restart. **一百一十三轮一致 R268-R389**.
  ProbeWorker + KeyManager decayed reset 自恢复链实测有效.

## R-nvonly 核心铁律 (持续生效)
- 只改 HM2 nv_gw (40006), 不碰 HM1, 不碰 ms_gw 源码.
- ms_gw fallback 已恢复 (`NVU_DISABLE_MS_FALLBACK=0`, `FALLBACK_UPSTREAM=ms_gw:40007`), 不主动禁用.
- 改前有数据, 改后必验证, 写入仓库.

## 本轮关键数据 (30min 实时链路分析注入 ~22:48 CST)

### 1. cc2 (cc4101-primary) 30min 0 req
- session 间歇空闲, 链路空闲健康. 0 fallback 0 deadline.
- buffer/wait 日志 (BUFFER-/WAIT-) 30min 空 (无 buffer 流量).

### 2. dsv4p_nv 30min 全 caller SR=14.3% (1/7)
| caller | model | status | count | avg_dur |
|---|---|---|---|---|
| hermes | dsv4p_nv | 200 | 1 | 18082 |
| hermes | dsv4p_nv | 429 | 5 | 1799 |
| hermes | dsv4p_nv | 502 | 1 | 10722 |

per-key (dsv4p): key2 → 1×200 (18082); 空 key → 5×429 (1799) + 1×502 (10722).
  (hermes mapped to key2, mapped tier 直接失败时 key 字段为空, 设计行为.)
per-egress: 203.10.96.139 → 1× (100%); 空 → 6× (0%).
分钟趋势: 14:20 429×1, 14:25 502×1, 14:30 429×1, 14:35 429×1, 14:40 429×1, 14:45 429×1
  (零星分散 6× 失败, 仅 1× 成功在早期, NVCF dsv4p function 本窗口配额紧张.)
延迟 (200): avg_dur 18082 (单样本).
fallback f×7 (全部 false, 0 fallback).

### 3. 错误分类 (30min)
- 6 dsv4p 错误: 6× all_tiers_exhausted (sub=`all_tiers_failed_in_mapped_tier`, avg 3286ms)
  — NVCF dsv4p function 配额瞬时空位/上游瞬时错误.
  - 本轮无 NV-TIER-SKIP (R388 0×, 本轮 0×, 自然波动).
  - 429/502: NVCF dsv4p function 配额瞬时空位/上游瞬时错误, 低频偶发 (6/7=86% 本窗口占比高
    但绝对数量 6 仍属低频, 非缓冲 caller mapped-tier 直接失败无轮转保护, 设计行为).
- nv_tier_attempts per-key 错误分布空 — mapped tier 直接失败无实际 tier attempt.
- dsv4p 错误类型集合与 R268-R388 一致 (all_tiers_exhausted, 无新增).
- buffer/wait 日志空.

### 4. 健康检查 (沿用 R388, 容器未重启)
- 容器全 Up: nv_gw 8h, cc4101 8h, nv_gw_stable 21h, ms_gw/logs_db 3 days.
- /health ok: nv_num_keys=5, pexec_models=[kimi_nv, dsv4p_nv, glm5_2_nv].
- 自恢复链 (ProbeWorker + KeyManager decayed reset + buffer 5key 轮转) 实测有效.

## 根因: NVCF dsv4p function 429/502 波 (非代码缺陷, 沿用 R353-R388 分析)
- **非 nv_gw 代码缺陷, 无需本轮改码**.
- all_tiers_exhausted (429/502): NVCF dsv4p function 配额瞬时空位/上游瞬时错误, 低频偶发,
  buffer + KeyManager 指数退避 + ProbeWorker + decayed reset 自恢复 (R268-R388 验证).
- 本轮无 NV-TIER-SKIP 无 stream_first_byte_timeout, 错误面收敛.
- 当前 cc2 流量极低, 偶发错误罕见且自恢复, 不达介入阈值.
- 本窗口 dsv4p SR 骤降 (1/7) 是 NVCF 侧配额紧张 + 样本极小 (7 req) 叠加, 非链路退化;
  非缓冲 caller (hermes) mapped-tier 无轮转保护故 SR 直接反映 NVCF 瞬时状态,
  cc2 缓冲 caller 走 buffer 5key 轮转故 SR 不受同影响.

## 判稳
- **NOP 巡检轮**. cc2 primary 0 req, 链路空闲健康, 0 fallback 0 deadline.
- dsv4p_nv 本轮 SR=14.3% (1/7), 较 R388 72.2% (13/18) 骤降 (样本极小 + NVCF 本窗口配额紧张,
  全部非缓冲 caller, cc2 不受影响). dsv4p 错误类型无新增, 与 R268-R388 一致 (一百一十三轮一致).

## 下一步
- 继续 NOP 巡检, 等 cc2 流量恢复后观察 dsv4p_nv SR (cc2 走 buffer 路径, 行为可能不同于非缓冲 caller).
- 关注是否出现新错误类型 (非 all_tiers_exhausted) 或 key/IP 级故障, 再决定是否介入.
- all_tiers_exhausted 若从低频偶发转为持续 429/502 波 (>=5/h 持续), 再评估 buffer 轮转/KeyManager 退避参数.
- 本轮 6/7=86% 占比高但绝对数 6 仍低且全非缓冲 caller, 下一轮观察是否回归 R384-R388 的正常区间.

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
