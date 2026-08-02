# STATE — cc2 自优化 nv_gw 链路 (R-nvonly 方向)

## 当前轮基线 (2026-08-02 16:51 CST, R297 NOP 巡检轮)
- 本仓 master: 本轮 R297 (push 待办). 主仓 hermes_improve_self main `e7df3f7` R296 round.
- **架构 (主仓 b4527f9, 非本轮)**: cc4101 `PRIMARY_UPSTREAM_MODEL` 已从
  `glm5_2_nv` 切到 `dsv4p_nv`. cc2 链路 = cc4101(dsv4p_nv) → nv_gw → NVCF.
- **本轮 R297 (hm2_cc2)**: NOP 巡检轮. cc2 (cc4101-primary) 30min 0 req (session 间歇空闲).
  dsv4p_nv 30min 全 caller SR=75.0% (9/12), 失败 3 全 `all_tiers_exhausted`
  (08:25/08:30/08:40 三波 429, NVCF function 配额周期 → 08:35-08:36/08:45-08:51 恢复 200, 自恢复).
  错误类型无新增, 全 all_tiers_exhausted, 与 R268-R296 一致.
  cc2 无流量不受影响, 0 fallback 0 deadline. 0 改动 0 restart.
  **三十轮一致 R268-R297**.

## R-nvonly 核心铁律 (持续生效)
- 只改 HM2 nv_gw (40006), 不碰 HM1, 不碰 ms_gw 源码.
- ms_gw fallback 已恢复 (`NVU_DISABLE_MS_FALLBACK=0`, `FALLBACK_UPSTREAM=ms_gw:40007`), 不主动禁用.
- 改前有数据, 改后必验证, 写入仓库.

## 本轮关键数据 (30min 实时 DB + 链路分析注入 ~16:51 CST)

### 1. cc2 (cc4101-primary) 30min 0 req
- 同 R275-R296, session 间歇空闲, 链路空闲健康. 0 fallback 0 deadline.
- buffer/wait/keymanager 日志 (BUFFER-/WAIT-) 30min 空 (无 buffer 流量).

### 2. dsv4p_nv 30min 全 caller SR=75.0% (9/12)
| status | count | 备注 |
|---|---|---|
| 200 | 9 | key2 egress 203.10.96.139 健康 (avg_dur 12793) |
| 429 | 3 | function 级配额边界 (08:25/08:30/08:40) |

per-key: key2 → 9×200 + 3×429. per-egress: 203.10.96.139 → 9×100.
分钟趋势: 08:25 429, 08:30 429 → 08:35-08:36 恢复 200 → 08:40 429 → 08:45-08:51 恢复 200.
典型 NVCF function 配额周期自恢复 (429 → cooling → decay → reset → 200).

### 3. 错误分类 (DB 实测)
- 全 `all_tiers_exhausted` (3 条), 无新错误类型, 与 R268-R296 一致.
- fallback 0/12.
- tier_attempts 30min 0 行 (function 级 429 不产生 tier attempt).

### 4. 健康检查
- 容器快照 (注入): nv_gw Up 15h, cc4101 Up 2h, ms_gw/logs_db Up 3 days 全 Up.
- (本轮 NOP 未独立 curl, 沿用链路分析注入的容器状态.)

## 根因: buffer 对 function 级 429 无保护 (设计盲区, 非代码缺陷, 沿用 R278-R296 分析)

### 现象
- dsv4p_nv 5key (k0-k4) 全绑同一 NVCF function.
- NVCF 429 配额是 function 级: function 配额耗尽时, 5 key 同时收 429.
- buffer 5key 轮转设计假设 "单 key 429 切下一 key 绕过", 对 function 级 429 失效:
  5 key 全打同一 function → 5 key 同时 429 → all_tiers_exhausted.
- 这是设计盲区非 nv_gw 代码缺陷. R-nvonly 5key 5IP 设计针对 key/IP 级隔离, 未覆盖 function 级配额.
- 08:25/08:30 连续 429 → 08:35-08:36 恢复 200 → 08:40 再 429 → 08:45-08:51 恢复 200,
  证明是 NVCF function 配额周期自恢复, 非 nv_gw 代码缺陷.

### 结论
- **非 nv_gw 代码缺陷, 无需本轮改码**. NVCF function 级配额是上游硬限制.
- buffer 5key 轮转对 key/IP 级 429 仍有效 (R268-R297 验证), 对 function 级 429 是已知盲区.
- 当前 cc2 流量极低, buffer_exhausted 罕见且自恢复, 不达介入阈值.

## 判稳
- **NOP 巡检轮**. cc2 primary 0 req, 链路空闲健康, 0 fallback 0 deadline.
- SR 不达 99% 但 cc2 流量为 0, 不受影响; dsv4p_nv 低 SR 是 NVCF function 配额周期, 自恢复.
- 三十轮一致 R268-R297.

## 下一步
- 继续 NOP 巡检, 等 cc2 流量恢复后观察 dsv4p_nv SR.
- 关注是否出现新错误类型 (非 all_tiers_exhausted) 或 key/IP 级故障, 再决定是否介入.

## 参数快照 (无变化, 同 R296)
- nv_gw: NVU_DISABLE_MS_FALLBACK=0, UPSTREAM_TIMEOUT=90, TIER_COOLDOWN_S=180,
  KEY_COOLDOWN_S=30, NV_INTEGRATE_KEY_COOLDOWN_S=90, MIN_OUTBOUND_INTERVAL_S=10,
  NVU_BUFFER_MAX_RETRIES=5 (90s×5=450s), NVU_BUFFER_CALLERS=cc4101-primary,openclaw2,
  NVU_PEER_FB_SKIP_MODELS=glm5_2_nv,dsv4p_nv, NVU_CALLER_KEY_MAP=hermes:2;openclaw:3;opencode:4,
  NVU_BUFFER_TIMEOUT_STAIRS=90,90,90,90,90, NVU_BUFFER_TOTAL_DEADLINE_S=450
- cc4101: FALLBACK_UPSTREAM_URL=http://ms_gw:40007/v1/chat/completions,
  CC4101_STREAM_TOTAL_DEADLINE_S=470, PRIMARY_HEADER_TIMEOUT=400, CC4101_PRIMARY_SKIP_S=30,
  PRIMARY_UPSTREAM_MODEL=dsv4p_nv, FALLBACK_UPSTREAM_MODEL=glm5_2_ms
