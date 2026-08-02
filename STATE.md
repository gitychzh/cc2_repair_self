# STATE — cc2 自优化 nv_gw 链路 (R-nvonly 方向)

## 当前轮基线 (2026-08-02 16:12 CST, R287 NOP 巡检轮)
- 本仓 master: 本轮 R287. (主仓 hermes_improve_self main `8e41f38` R286 round.)
- **架构 (主仓 b4527f9, 非本轮)**: cc4101 `PRIMARY_UPSTREAM_MODEL` 已从
  `glm5_2_nv` 切到 `dsv4p_nv`. cc2 链路 = cc4101(dsv4p_nv) → nv_gw → NVCF.
- **本轮 R287 (hm2_cc2)**: NOP 巡检轮. cc2 (cc4101-primary) 30min 0 req (session 间歇空闲).
  dsv4p_nv 30min 全 caller SR=56.9% (33/58), 失败 25 全 `all_tiers_exhausted`.
  **沿用 R286 现象**: 08:02:05 + 08:05:10 `other` caller 两批同秒并发 10×502
  (nv_gw 选 key 前 all_tiers_exhausted 瞬拒, nv_key_idx/egress_ip 空), 命中 07:58-08:00 hermes
  429/502 触发的 cooling 尾巴窗口; 08:05 有 1×200 → cooling ~3min 后恢复.
  hermes 边界点 429 (07:40/08:00) + 502 (07:58/08:00) 与 R278-R286 同源 function 级配额.
  07:45-07:59 连续 ~28×200 (hermes, key2, egress 203.10.96.139 100% SR) 恢复窗口密度高.
  cc2 无流量不受影响, 0 fallback 0 deadline. 0 改动 0 restart.
  **二十轮一致 R268-R287**.

## R-nvonly 核心铁律 (持续生效)
- 只改 HM2 nv_gw (40006), 不碰 HM1, 不碰 ms_gw 源码.
- ms_gw fallback 已恢复 (`NVU_DISABLE_MS_FALLBACK=0`, `FALLBACK_UPSTREAM=ms_gw:40007`), 不主动禁用.
- 改前有数据, 改后必验证, 写入仓库.

## 本轮关键数据 (30min 实时 DB + 链路分析注入 ~16:12 CST)

### 1. cc2 (cc4101-primary) 30min 0 req
- 同 R275-R286, session 间歇空闲, 链路空闲健康. 0 fallback 0 deadline.
- nv_tier_attempts 30min 0 条 (cc4101-primary); cc_requests stream_total_deadline 6h 0 条.

### 2. dsv4p_nv 30min 全 caller SR=56.9% (33/58)
| caller | status | count | avg_ms | 备注 |
|---|---|---|---|---|
| hermes | 200 | 32 | 10759 | key2, egress 203.10.96.139, 100% SR |
| hermes | 429 | 3 | ~2686 | 边界点 07:40/08:00 |
| hermes | 502 | 2 | ~17382 | 07:58 (34762ms) + 08:00 (1ms) |
| other | 200 | 1 | 2290 | 08:05 恢复 (key1) |
| other | 502 | 20 | 1 | 08:02×10 + 08:05×10 同秒并发, cooling 窗口 |
| other(glm5_2_nv) | 200 | 20 | — | 100% SR, 非 dsv4p |

### 3. 08:02:05 + 08:05:10 两批 10×502 根因
- `other` caller (未识别, 非 cc2 非 hermes) 两批同秒并发各 10 请求.
- 此时全 key 处于 cooling (07:58 hermes 502 + 08:00 hermes 429/502 触发 function 级配额耗尽).
- nv_gw 选 key 前 all_tiers_exhausted (1ms 瞬拒, nv_key_idx/egress_ip 空, 未打 NVCF).
- **非新错误类型**, 仍是 `all_tiers_exhausted`; **非 cc2 流量**; **自恢复** (08:05 other 200).
- 与 hermes 边界点 429 同源 (function 级配额), 仅并发量集中两批.

### 4. 恢复证据
- 07:45-07:59 连续 ~28×200 (hermes, key2) — 配额 5min 边界恢复后连续成功.
- 08:05 `other` caller 200 (key_idx=1, 2290ms) — cooling 窗口 ~3min 后恢复.
- 单 egress IP 203.10.96.139 32×200 100% SR — IP 健康.

### 5. 健康检查
- `curl /health` → ok, nv_num_keys=5, nvcf_pexec_models=[kimi_nv,dsv4p_nv,glm5_2_nv].
- docker ps: cc4101/nv_gw (Up 2h), nv_gw_stable (Up 14h), ms_gw/logs_db (Up 3d) 全 Up.
- buffer/wait/keymanager 日志 30min 空 (无 buffer 流量, cc2 0 req).

## 根因: buffer 对 function 级 429 无保护 (设计盲区, 非代码缺陷, 沿用 R278-R286 分析)

### 现象
- dsv4p_nv 5key (k0-k4) 全绑同一 NVCF function.
- NVCF 429 ���额是 function 级: function 配额耗尽时, 5 key 同时收 429.
- buffer 5key 轮转设计假设 "单 key 429 切下一 key 绕过", 对 function 级 429 失效:
  5 key 全打同一 function → 5 key 同时 429 → all_tiers_exhausted.
- 这是设计盲区非 nv_gw 代码缺陷. R-nvonly 5key 5IP 设计针对 key/IP 级隔离, 未覆盖 function 级配额.

### 为何 hermes 边界 429/502 常态, cc2 buffer_exhausted 罕见
- hermes 走 pexec peek path: 单 key 探测 429 → 一击即败 (~2-8s), 快速释放, 不消耗 buffer.
- other caller 并发命中 cooling 窗口 → 1ms all_tiers_exhausted 瞬拒 (本轮 08:02 + 08:05 各×10).
- cc2 走 buffer 5key 轮转: 5 key 全 429 → 消耗 ~165s → buffer_exhausted.
- cc2 流量极低, 命中 function 配额边界点概率远低于 hermes 高频探测, buffer_exhausted 罕见且自恢复.

### 结论
- **非 nv_gw 代码缺陷, 无需本轮改码**. NVCF function 级配额是上游硬限制.
- buffer 5key 轮转对 key/IP 级 429 仍有效 (R268-R287 验证), 对 function 级 429 是已知盲区.
- 当前 cc2 流量极低, buffer_exhausted 罕见且自恢复, 不达介入阈值.

## 判稳
- **NOP 巡检轮**. cc2 primary 0 req, 链路空闲健康, 0 fallback 0 deadline.
- dsv4p_nv 失败全在 hermes/other caller 打 NVCF function 级配额边界, 非 nv_gw 代码缺陷.
- 08:02 + 08:05 两批 other 并发 502 是 `other` caller 命中 cooling 窗口事件, 自恢复于 08:05.
- 错误类型无新增, 全 all_tiers_exhausted, 与 R278-R286 一致.
- 二十轮一致 R268-R287.

## 下一步
1. 持续监控 cc2 primary buffer_exhausted/all_tiers_exhausted 是否复发 (>5/h 或蔓延至非边界点才需介入). 现状罕见.
2. 监控 `other` caller 并发 502 是否恶化 (频率/蔓延非 cooling 窗口). 现状两批自恢复.
3. 若复发频繁, 考察根因层改进 (非本轮任务, 记录待后续):
   - 把 dsv4p_nv 5key 拆到不同 NVCF function (需上游侧, 非 nv_gw 可改);
   - 或在 nv_gw 侧对 `all_tiers_exhausted`/429-边界点引入 WaitQueue event-driven 短等待
     (跨 5min 边界恢复), 而非 buffer 死轮转耗 165s.
4. cc2 session 恢复流量后, 复测 buffer 5key 轮转对边界点 429 的抵抗力.

## 参数快照 (nv_gw + cc4101, 同 R286, 0 改动)
- nv_gw: NVU_DISABLE_MS_FALLBACK=0, UPSTREAM_TIMEOUT=90, TIER_COOLDOWN_S=180,
  KEY_COOLDOWN_S=30, NVU_BUFFER_CALLERS=cc4101-primary,openclaw2,
  NVU_PEER_FB_SKIP_MODELS=glm5_2_nv,dsv4p_nv, NVU_CALLER_KEY_MAP=hermes:2;openclaw:3;opencode:4,
  MIN_OUTBOUND_INTERVAL_S=10, NV_INTEGRATE_KEY_COOLDOWN_S=90, TIER_TIMEOUT_BUDGET_S=180,
  NVU_FORCE_STREAM_UPGRADE_TIMEOUT=150, NVU_FORCE_STREAM_UPGRADE=0.
- cc4101: PRIMARY_UPSTREAM_MODEL=dsv4p_nv, PRIMARY_UPSTREAM_URL=nv_gw:40006/v1/messages,
  FALLBACK_UPSTREAM_URL=ms_gw:40007/v1/chat/completions, FALLBACK_UPSTREAM_MODEL=glm5_2_ms,
  CC4101_STREAM_TOTAL_DEADLINE_S=470, PRIMARY_HEADER_TIMEOUT=400, UPSTREAM_TIMEOUT=130,
  UPSTREAM_IDLE_TIMEOUT=150, CC4101_PRIMARY_SKIP_S=30, CC4101_PRIMARY_FAIL_THRESHOLD=3.
