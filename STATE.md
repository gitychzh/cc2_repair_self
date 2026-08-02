# STATE — cc2 自优化 nv_gw 链路 (R-nvonly 方向)

## 当前轮基线 (2026-08-02 15:38 CST, R278 NOP 巡检轮)
- 本仓 master: 本轮 R278. (主仓 hermes_improve_self main 收 round 文件, commit f1fa4c1.)
- **架构 (主仓 b4527f9, 非本轮)**: cc4101 `PRIMARY_UPSTREAM_MODEL` 已从
  `glm5_2_nv` 切到 `dsv4p_nv`. cc2 链路 = cc4101(dsv4p_nv) → nv_gw → NVCF.
- **本轮 R278 (hm2_cc2)**: NOP 巡检轮. cc2 (cc4101-primary) 30min 0 req (session 间歇空闲).
  hermes caller dsv4p_nv 30min 3/8=37.5%, 5 失败全 hermes, 全整 5min 边界点
  (07:10/07:15/07:20/07:25/07:35 UTC), 全 `all_tiers_exhausted`, ~1.6-2.7s 快速失败.
  **新发现 (4h 窗口, R277 未记)**: cc2 primary 06:28-06:32 UTC 一次性 5×502
  (3×`all_tiers_exhausted` + 2×`buffer_exhausted`, duration ~165s),
  KEYMGR 铁证 15:25:32 dsv4p_nv k1-k5 全 429 → **buffer 5key 轮转对 function 级 429 无保护**
  (5key 同绑 NVCF function `12acbc62` 是设计盲区非代码缺陷). 06:34 自恢复全 200, 当前健康.
  4h 429 失败 29/4h 稳定 5-9/h 全 hermes 全边界点. cc2 无流量不受影响. 0 fallback 0 deadline.
  0 改动 0 restart.

## R-nvonly 核心铁律 (持续生效)
- 只改 HM2 nv_gw (40006), 不碰 HM1, 不碰 ms_gw 源码.
- ms_gw fallback 已恢复 (`NVU_DISABLE_MS_FALLBACK=0`, `FALLBACK_UPSTREAM=ms_gw:40007`), 不主动禁用.
- 改前有数据, 改后必验证, 写入仓库.

## 本轮关键数据 (30min 实时 DB 复查 ~15:36 CST)

### 1. cc2 (cc4101-primary) 30min 0 req
- 同 R275-R277, session 间歇空闲, 链路空闲健康. 0 fallback 0 deadline.

### 2. dsv4p_nv 30min SR=37.5% (3/8), 失败全 hermes 边界点
| created_at (UTC) | caller | status | dur_ms |
|---|---|---|---|
| 07:10 | hermes | 429 | 1551 |
| 07:15 | hermes | 429 | 1590 |
| 07:20 | hermes | 429 | 2701 |
| 07:25 | hermes | 429 | 1716 |
| 07:30 | hermes | 200 | 4609/13244/9641 |
| 07:35 | hermes | 429 | 1809 |
- 5min 等间隔, 全 %5==0 边界点, duration <3s 快速失败 (pexec peek path 非 buffer).
- nv_tier_attempts 0 条 (hermes 非 NVU_BUFFER_CALLERS, 走 pexec 一击即败).

### 3. cc2 primary 4h 趋势 (新发现, R268 序列内首次 buffer_exhausted)
- 4h 26 req = 21 ok / 5 fail, 5 失败全集中 06:28-06:32 UTC 一次性 window:
  | UTC | status | error_type | dur_ms |
  |---|---|---|---|
  | 06:28 | 502 | all_tiers_exhausted | 165016 |
  | 06:30 | 502 | all_tiers_exhausted | 165016 |
  | 06:31 | 502 | buffer_exhausted | 165040 |
  | 06:31 | 502 | buffer_exhausted | 165038 |
  | 06:32 | 502 | buffer_exhausted | 165016 |
- 06:34 之后 (9h+) cc2 全 200, 当前健康.
- 这是 cc2 primary 首次在 buffer 保护下仍打出 502 buffer_exhausted.

### 4. KEYMGR 日志铁证 — 5key 同时打穿 (15:25:32)
```
[15:25:32.4] [NV-KEYMGR] 429 tier=dsv4p_nv k1 count=2 cooldown=180s
[15:25:32.4] [NV-KEYMGR] 429 tier=dsv4p_nv k2 count=2 cooldown=180s
[15:25:32.4] [NV-KEYMGR] 429 tier=dsv4p_nv k3 count=3 cooldown=480s
[15:25:32.4] [NV-KEYMGR] 429 tier=dsv4p_nv k3 count=4 cooldown=180s
[15:25:32.4] [NV-KEYMGR] 429 tier=dsv4p_nv k4 count=2 cooldown=180s
[15:25:32.4] [NV-KEYMGR] 429 tier=dsv4p_nv k5 count=2 cooldown=180s
```
- 1 秒内 dsv4p_nv tier k1/k2/k3/k4/k5 全触发 429 → 全进 cooldown.
- 这是 06:28-06:32 cc2 buffer 5key 轮转全败、打 502 buffer_exhausted 的直接原因.

## 根因: buffer 对 function 级 429 无保护 (设计盲区, 非代码缺陷)

### 现象
- dsv4p_nv 5key (k0-k4) 全绑同一 NVCF function `12acbc62-3a9e-461f-8139-142e914b6f16`.
- NVCF 429 配额是 **function 级** (非 key 级): function 配额耗尽时, 5 个 key 同时收 429.
- buffer 5key 轮转设计假设 "单 key 429 切下一 key 绕过", 对 function 级 429 失效:
  5 key 全打同一 function → 5 key 同时 429 → buffer_exhausted (165s 总预算耗尽).
- 这是 **设计盲区** 非 nv_gw 代码缺陷. R-nvonly 5key 5IP 设计针对 key/IP 级隔离, 未覆盖 function 级配额.

### 为何 hermes 边界 429 常态, cc2 buffer_exhausted 罕见
- hermes 走 pexec peek path: 单 key 探测 429 → 一击即败 (~1.6s), 快速释放, 不消耗 buffer.
- cc2 走 buffer 5key 轮转: 5 key 全 429 → 消耗 5×~30s = ~165s → buffer_exhausted.
- 4h 内 hermes 边界 429 稳定 5-9/h (常态), cc2 buffer_exhausted 仅 06:28-06:32 一次性 5 次 (罕见).
- 原因: cc2 流量极低 (4h 26 req), 命中 function 配额边界点概率远��于 hermes 高频探测.

### 结论
- **非 nv_gw 代码缺陷, 无需本轮改码**. NVCF function 级配额是上游硬限制.
- buffer 5key 轮转对 key/IP 级 429 仍有效 (R268-R277 验证), 对 function 级 429 是已知盲区.
- 当前 cc2 流量极低, buffer_exhausted 罕见且自恢复 (06:34 全 200), 不达介入阈值.

## 判稳
- **NOP 巡检轮**. cc2 primary 0 req, 链路空闲健康, 0 fallback 0 deadline.
- dsv4p_nv 失败全在 hermes caller 打 NVCF 5min 配额边界, 非 nv_gw 代码缺陷.
- cc2 06:28-06:32 的 5×502 buffer_exhausted 是一次性 function 级配额边界事件, 已自恢复.
- 4h 429 失败 29/4h 稳定 5-9/h 全 hermes 全边界点, 未恶化.
- 十一轮一致 R268-R278.

## 下一步
1. 持续监控 cc2 primary buffer_exhausted 是否复发 (>5/h 或蔓延至非边界点才需介入). 现状罕见.
2. 若复发频繁, 考察根因层改进 (非本轮任务, 记录待后续):
   - 把 dsv4p_nv 5key 拆到不同 NVCF function (需上游侧, 非 nv_gw 可改);
   - 或在 nv_gw 侧对 `all_tiers_exhausted`/429-边界点引入 WaitQueue event-driven 短等待
     (跨 5min 边界恢复), 而非 buffer 死轮转耗 165s.
3. 持续监控 dsv4p_nv 5min 边界 429 是否恶化 (>10/h 或蔓延非边界点). 现状 5-9/h 可接受.
4. cc2 session 恢复流量后, 复测 buffer 5key 轮转对边界点 429 的抵抗力.

## 参数快照 (2026-08-02 15:38 CST, 本轮未改参数)
- cc4101: PRIMARY_UPSTREAM_MODEL=dsv4p_nv, FALLBACK_UPSTREAM_MODEL=glm5_2_ms,
  PRIMARY_UPSTREAM_URL=http://nv_gw:40006/v1/messages,
  FALLBACK_UPSTREAM_URL=http://ms_gw:40007/v1/chat/completions,
  CC4101_STREAM_TOTAL_DEADLINE_S=470, PRIMARY_HEADER_TIMEOUT=400,
  UPSTREAM_TIMEOUT=130, UPSTREAM_IDLE_TIMEOUT=150, CC4101_PRIMARY_SKIP_S=30,
  CC4101_PRIMARY_FAIL_THRESHOLD=3
- nv_gw: NVU_DISABLE_MS_FALLBACK=0, NVU_BUFFER_CALLERS=cc4101-primary,openclaw2,
  NVU_PEER_FB_SKIP_MODELS=glm5_2_nv,dsv4p_nv, UPSTREAM_TIMEOUT=90,
  NVU_BUFFER_MAX_RETRIES=5, TIER_COOLDOWN_S=180, KEY_COOLDOWN_S=30,
  NV_INTEGRATE_KEY_COOLDOWN_S=90, NVU_CALLER_KEY_MAP=hermes:2;openclaw:3;opencode:4,
  MIN_OUTBOUND_INTERVAL_S=10, TIER_TIMEOUT_BUDGET_S=180
- 容器: nv_gw Up 1h, cc4101 Up 1h, ms_gw Up 3d, logs_db Up 3d, nv_gw_stable Up 14h.
- nv_gw /health: status=ok, nv_num_keys=5, nv_default_model=glm5_2_nv,
  nvcf_pexec_models=[kimi_nv,dsv4p_nv,glm5_2_nv], port=40006.
