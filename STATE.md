# STATE — cc2 自优化 nv_gw 链路 (R-nvonly 方向)

## 当前轮基线 (2026-08-02 16:44 CST, R295 NOP 巡检轮)
- 本仓 master: 本轮 R295 (push 待办). 主仓 hermes_improve_self main `f5921f4` R294 round.
- **架构 (主仓 b4527f9, 非本轮)**: cc4101 `PRIMARY_UPSTREAM_MODEL` 已从
  `glm5_2_nv` 切到 `dsv4p_nv`. cc2 链路 = cc4101(dsv4p_nv) → nv_gw → NVCF.
- **本轮 R295 (hm2_cc2)**: NOP 巡检轮. cc2 (cc4101-primary) 30min 0 req (session 间歇空闲).
  dsv4p_nv 30min 全 caller SR=37.5% (3/8), 失败 5 全 `all_tiers_exhausted`
  (08:15-08:30 连续 4×429 NVCF function 配额耗尽 → 08:35-08:36 恢复 3×200 → 08:40 再 1×429 周期自恢复).
  错误类型无新增, 全 all_tiers_exhausted, 与 R268-R294 一致.
  cc2 无流量不受影响, 0 fallback 0 deadline. 0 改动 0 restart.
  **二十八轮一致 R268-R295**.

## R-nvonly 核心铁律 (持续生效)
- 只改 HM2 nv_gw (40006), 不碰 HM1, 不碰 ms_gw 源码.
- ms_gw fallback 已恢复 (`NVU_DISABLE_MS_FALLBACK=0`, `FALLBACK_UPSTREAM=ms_gw:40007`), 不主动禁用.
- 改前有数据, 改后必验证, 写入仓库.

## 本轮关键数据 (30min 实时 DB + 链路分析注入 ~16:44 CST)

### 1. cc2 (cc4101-primary) 30min 0 req
- 同 R275-R294, session 间歇空闲, 链路空闲健康. 0 fallback 0 deadline.
- buffer/wait/keymanager 日志 30min 空 (无 buffer 流量).

### 2. dsv4p_nv 30min 全 caller SR=37.5% (3/8)
| status | count | 备注 |
|---|---|---|
| 200 | 3 | key2 egress 203.10.96.139 健康 (avg_dur 16032) |
| 429 | 5 | function 级配额边界 (08:15-08:40 间歇) |

caller 分布: hermes → 3×200 + 5×429. (cc4101-primary 0 req, 不受影响)

按分钟趋势 (NVCF function 配额周期自恢复):
- 08:15/08:20/08:25/08:30 → 4×429 (NVCF function 配额耗尽窗口)
- 08:35 → 1×200, 08:36 → 2×200 (配额恢复, 自恢复)
- 08:40 → 1×429 (配额再次触底, 周期性)

per-key: key2 → 3×200 + 5×429. per-egress: 203.10.96.139 → 3×100.

### 3. 错误分类 (DB 实测)
- 全 `all_tiers_exhausted` (5 条, avg_dur 1949ms), 无新错误类型, 与 R268-R294 一致.
- fallback 0/8.
- tier_attempts 30min 0 行 (function 级 429 不产生 tier attempt).

### 4. 健康检查
- `curl /health` → ok, nv_num_keys=5, nvcf_pexec_models=[kimi_nv,dsv4p_nv,glm5_2_nv].
- docker ps: cc4101/nv_gw (Up 2h), nv_gw_stable (Up 15h), ms_gw/logs_db (Up 3 days) 全 Up.

## 根因: buffer 对 function 级 429 无保护 (设计盲区, 非代码缺陷, 沿用 R278-R294 分析)

### 现象
- dsv4p_nv 5key (k0-k4) 全绑同一 NVCF function.
- NVCF 429 配额是 function 级: function 配额耗尽时, 5 key 同时收 429.
- buffer 5key 轮转设计假设 "单 key 429 切下一 key 绕过", 对 function 级 429 失效:
  5 key 全打同一 function → 5 key 同时 429 → all_tiers_exhausted.
- 这是设计盲区非 nv_gw 代码缺陷. R-nvonly 5key 5IP 设计针对 key/IP 级隔离, 未覆盖 function 级配额.
- 08:15-08:30 连续 429 → 08:35-08:36 恢复 200 → 08:40 再 429, 证明是 NVCF function 配额周期自恢复, 非 nv_gw 代码缺陷.

### 结论
- **非 nv_gw 代码缺陷, 无需本轮改码**. NVCF function 级配额是上游硬限制.
- buffer 5key 轮转对 key/IP 级 429 仍有效 (R268-R295 验证), 对 function 级 429 是已知盲区.
- 当前 cc2 流量极低, buffer_exhausted 罕见且自恢复, 不达介入阈值.

## 判稳
- **NOP 巡检轮**. cc2 primary 0 req, 链路空闲健康, 0 fallback 0 deadline.
- SR 不达 99% 但 cc2 流量为 0, 不受影响; dsv4p_nv 低 SR 是 NVCF function 配额周期, 自恢复.
- 二十八轮一致 R268-R295.

## 下一步
- 继续 NOP 巡检, 等 cc2 流量恢复后观察 dsv4p_nv SR.
- 关注是否出现新错误类型 (非 all_tiers_exhausted) 或 key/IP 级故障, 再决定是否介入.

## 参数快照 (无变化, 同 R294)
- nv_gw: NVU_DISABLE_MS_FALLBACK=0, UPSTREAM_TIMEOUT=90, TIER_COOLDOWN_S=180,
  KEY_COOLDOWN_S=30, NV_INTEGRATE_KEY_COOLDOWN_S=90, MIN_OUTBOUND_INTERVAL_S=10,
  NVU_BUFFER_MAX_RETRIES=5 (90s×5=450s), NVU_BUFFER_CALLERS=cc4101-primary,openclaw2,
  NVU_PEER_FB_SKIP_MODELS=glm5_2_nv,dsv4p_nv, NVU_CALLER_KEY_MAP=hermes:2;openclaw:3;opencode:4,
  NVU_BUFFER_TIMEOUT_STAIRS=90,90,90,90,90, NVU_BUFFER_TOTAL_DEADLINE_S=450
- cc4101: FALLBACK_UPSTREAM_URL=http://ms_gw:40007/v1/chat/completions,
  CC4101_STREAM_TOTAL_DEADLINE_S=470, PRIMARY_HEADER_TIMEOUT=400, CC4101_PRIMARY_SKIP_S=30,
  PRIMARY_UPSTREAM_MODEL=dsv4p_nv, PRIMARY_UPSTREAM_URL=http://nv_gw:40006/v1/messages,
  FALLBACK_UPSTREAM_MODEL=glm5_2_ms, UPSTREAM_TIMEOUT=130, UPSTREAM_IDLE_TIMEOUT=150,
  CC4101_PRIMARY_FAIL_THRESHOLD=3
- settings.json: contextWindow=170000, autoCompactWindow=155000, API_TIMEOUT_MS=600000
