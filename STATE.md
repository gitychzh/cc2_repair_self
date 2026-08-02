# STATE — cc2 自优化 nv_gw 链路 (R-nvonly 方向)

## 当前轮基线 (2026-08-02 15:46 CST, R280 NOP 巡检轮)
- 本仓 master: 本轮 R280. (主仓 hermes_improve_self main 收 round 文件, commit 待 push.)
- **架构 (主仓 b4527f9, 非本轮)**: cc4101 `PRIMARY_UPSTREAM_MODEL` 已从
  `glm5_2_nv` 切到 `dsv4p_nv`. cc2 链路 = cc4101(dsv4p_nv) → nv_gw → NVCF.
- **本轮 R280 (hm2_cc2)**: NOP 巡检轮. cc2 (cc4101-primary) 30min 0 req (session 间歇空闲).
  hermes caller dsv4p_nv 30min 3/8=37.5%, 5 失败全 hermes, 全整 5min 边界点
  (07:15/07:20/07:25/07:35/07:40 UTC), 全 `all_tiers_exhausted`, ~1.5-2.7s 快速失败.
  07:30 三连 200 + 07:45/07:46 三连 200 印证 NVCF 5min 配额周期恢复窗口.
  边界点与 R279 完全重合 (07:15-07:40) 非 5min 平移而是配额周期稳态, 非恶化.
  R278 记录的 cc2 06:28-06:32 UTC 一次性 5×502 buffer_exhausted 未复发, 已自恢复全 200.
  4h 失败 28 (all_tiers_exhausted 24 + buffer_exhausted 3 + NVStream_IncompleteRead 1)
  稳定 5-9/h 全 hermes 全边界点. cc2 无流量不受影响. 0 fallback 0 deadline.
  0 改动 0 restart.

## R-nvonly 核心铁律 (持续生效)
- 只改 HM2 nv_gw (40006), 不碰 HM1, 不碰 ms_gw 源码.
- ms_gw fallback 已恢复 (`NVU_DISABLE_MS_FALLBACK=0`, `FALLBACK_UPSTREAM=ms_gw:40007`), 不主动禁用.
- 改前有数据, 改后必验证, 写入仓库.

## 本轮关键数据 (30min 实时 DB 复查 ~15:46 CST)

### 1. cc2 (cc4101-primary) 30min 0 req
- 同 R275-R279, session 间歇空闲, 链路空闲健康. 0 fallback 0 deadline.

### 2. dsv4p_nv 30min SR=37.5% (3/8), 失败全 hermes 边界点
| min (UTC) | caller | status | count | dur_ms |
|---|---|---|---|---|
| 07:15 | hermes | 429 | 1 | ~1590 |
| 07:20 | hermes | 429 | 1 | ~2701 |
| 07:25 | hermes | 429 | 1 | ~1716 |
| 07:30 | hermes | 200 | 3 | 4609/9641/13244 |
| 07:35 | hermes | 429 | 1 | ~1809 |
| 07:40 | hermes | 429 | 1 | ~2485 |
| 07:45 | hermes | 200 | 2 | — |
| 07:46 | hermes | 200 | 1 | — |
- 5min 等间隔, 全 %5==0 边界点, duration <3s 快速失败 (pexec peek path 非 buffer).
- 07:30 三连 200 + 07:45-07:46 三连 200: 配额 5min 边界恢复瞬间 hermes 抢到成功, 印证周期性.
- nv_tier_attempts 0 条 (hermes 非 NVU_BUFFER_CALLERS, 走 pexec 一击即败).

### 3. cc2 primary 状态
- 本轮 30min 0 req, 无 buffer_exhausted 复发.
- R278 记录的 06:28-06:32 UTC 5×502 (function 级配额边界事件) 已自恢复 (06:34 后全 200, 9h+ 健康).

### 4. 4h 失败趋势 (28 总, 全 hermes)
| hour (UTC) | count |
|---|---|
| 03:00 | 1 |
| 04:00 | 6 |
| 05:00 | 6 |
| 06:00 | 9 |
| 07:00 | 6 |
- 错误分类: all_tiers_exhausted 24, buffer_exhausted 3 (R278 一次性事件, 已自恢复),
  NVStream_IncompleteRead 1 (单次, 非模式).
- 稳定 5-9/h, 全 hermes, 全 5min 边界点, 非恶化.

## 根因: buffer 对 function 级 429 无保护 (设计盲区, 非代码缺陷, 沿用 R278/R279 分析)

### 现象
- dsv4p_nv 5key (k0-k4) 全绑同一 NVCF function `12acbc62-3a9e-461f-8139-142e914b6f16`.
- NVCF 429 配额是 **function 级** (非 key 级): function 配额耗尽时, 5 个 key 同时收 429.
- buffer 5key 轮转设计假设 "单 key 429 切下一 key 绕过", 对 function 级 429 失效:
  5 key 全打同一 function → 5 key 同时 429 → buffer_exhausted (165s 总预算耗尽).
- 这是 **设计盲区** 非 nv_gw 代码缺陷. R-nvonly 5key 5IP 设计针对 key/IP 级隔离, 未覆盖 function 级配额.

### 为何 hermes 边界 429 常态, cc2 buffer_exhausted 罕见
- hermes 走 pexec peek path: 单 key 探测 429 → 一击即败 (~1.6s), 快速释放, 不消耗 buffer.
- cc2 走 buffer 5key 轮转: 5 key 全 429 → 消耗 5×~30s = ~165s → buffer_exhausted.
- 4h 内 hermes 边界 429 稳定 5-9/h (常态), cc2 buffer_exhausted 仅 06:28-06:32 一次性 3 次 (罕见).
- 原因: cc2 流量极低 (4h 26 req), 命中 function 配额边界点概率远低于 hermes 高频探测.

### 结论
- **非 nv_gw 代码缺陷, 无需本轮改码**. NVCF function 级配额是上游硬限制.
- buffer 5key 轮转对 key/IP 级 429 仍有效 (R268-R279 验证), 对 function 级 429 是已知盲区.
- 当前 cc2 流量极低, buffer_exhausted 罕见且自恢复 (06:34 全 200), 不达介入阈值.

## 判稳
- **NOP 巡检轮**. cc2 primary 0 req, 链路空闲健康, 0 fallback 0 deadline.
- dsv4p_nv 失败全在 hermes caller 打 NVCF 5min 配额边界, 非 nv_gw 代码缺陷.
- 边界点与 R279 完全重合 (07:15-07:40), 非 5min 平移而是配额周期稳态, 非恶化.
- 无新错误类型, 无 buffer_exhausted 复发, NVStream_IncompleteRead 仅 1 次非模式.
- 4h 失败 28 稳定 5-9/h 全 hermes 全边界点, 未恶化.
- 十三轮一致 R268-R280.

## 下一步
1. 持续监控 cc2 primary buffer_exhausted 是否复发 (>5/h 或蔓延至非边界点才需介入). 现状罕见.
2. 若复发频繁, 考察根因层改进 (非本轮任务, 记录待后续):
   - 把 dsv4p_nv 5key 拆到不同 NVCF function (需上游侧, 非 nv_gw 可改);
   - 或在 nv_gw 侧对 `all_tiers_exhausted`/429-边界点引入 WaitQueue event-driven 短等待
     (跨 5min 边界恢复), 而非 buffer 死轮转耗 165s.
3. 持续监控 dsv4p_nv 5min 边界 429 是否恶化 (>10/h 或蔓延非边界点). 现状 5-9/h 可接受.
4. cc2 session 恢复流量后, 复测 buffer 5key 轮转对边界点 429 的抵抗力.

## 参数快照 (nv_gw + cc4101, 同 R279)
- nv_gw: NVU_DISABLE_MS_FALLBACK=0, UPSTREAM_TIMEOUT=90, TIER_COOLDOWN_S=180,
  KEY_COOLDOWN_S=30, NVU_BUFFER_CALLERS=cc4101-primary,openclaw2,
  NVU_PEER_FB_SKIP_MODELS=glm5_2_nv,dsv4p_nv, NVU_CALLER_KEY_MAP=hermes:2;openclaw:3;opencode:4,
  MIN_OUTBOUND_INTERVAL_S=10, NV_INTEGRATE_KEY_COOLDOWN_S=90, TIER_TIMEOUT_BUDGET_S=180.
- cc4101: PRIMARY_UPSTREAM_MODEL=dsv4p_nv, PRIMARY_UPSTREAM_URL=nv_gw:40006/v1/messages,
  FALLBACK_UPSTREAM_URL=ms_gw:40007/v1/chat/completions, FALLBACK_UPSTREAM_MODEL=glm5_2_ms,
  CC4101_STREAM_TOTAL_DEADLINE_S=470, PRIMARY_HEADER_TIMEOUT=400, UPSTREAM_TIMEOUT=130,
  UPSTREAM_IDLE_TIMEOUT=150, CC4101_PRIMARY_SKIP_S=30, CC4101_PRIMARY_FAIL_THRESHOLD=3.
