# STATE — cc2 自优化 nv_gw 链路 (R-nvonly 方向)

## 当前轮基线 (2026-08-02 16:26 CST, R290 NOP 巡检轮)
- 本仓 master: 本轮 R290. (主仓 hermes_improve_self main `2b11cc4` R290 round.)
- **架构 (主仓 b4527f9, 非本轮)**: cc4101 `PRIMARY_UPSTREAM_MODEL` 已从
  `glm5_2_nv` 切到 `dsv4p_nv`. cc2 链路 = cc4101(dsv4p_nv) → nv_gw → NVCF.
- **本轮 R290 (hm2_cc2)**: NOP 巡检轮. cc2 (cc4101-primary) 30min 0 req (session 间歇空闲).
  dsv4p_nv 30min 全 caller SR=58.2% (39/67), 失败 28 全 `all_tiers_exhausted`.
  错误类型无新增, 全 all_tiers_exhausted, 与 R268-R289 一致.
  cc2 无流量不受影响, 0 fallback 0 deadline. 0 改动 0 restart.
  **二十三轮一致 R268-R290**.

## R-nvonly 核心铁律 (持续生效)
- 只改 HM2 nv_gw (40006), 不碰 HM1, 不碰 ms_gw 源码.
- ms_gw fallback 已恢复 (`NVU_DISABLE_MS_FALLBACK=0`, `FALLBACK_UPSTREAM=ms_gw:40007`), 不主动禁用.
- 改前有数据, 改后必验证, 写入仓库.

## 本轮关键数据 (30min 实时 DB + 链路分析注入 ~16:25 CST)

### 1. cc2 (cc4101-primary) 30min 0 req
- 同 R275-R289, session 间歇空闲, 链路空闲健康. 0 fallback 0 deadline.
- nv_tier_attempts 30min 0 条 (cc4101-primary); cc_requests stream_total_deadline 6h 0 条 (DB 实测确认).

### 2. dsv4p_nv 30min 全 caller SR=58.2% (39/67)
| status | count | 备注 |
|---|---|---|
| 200 | 39 | hermes + other |
| 502 | 22 | all_tiers_exhausted (cooling 窗口瞬拒) |
| 429 | 6 | 边界点配额 |

### 3. 错误分类
- 全 `all_tiers_exhausted` (28), 无新错误类型, 与 R268-R289 一致.
- nv_tier_attempts 30min 0 条 (无 buffer 流量打 NVCF tier).

### 4. 健康检查
- `curl /health` → ok, nv_num_keys=5, nvcf_pexec_models=[kimi_nv,dsv4p_nv,glm5_2_nv].
- docker ps: cc4101/nv_gw (Up 2h), nv_gw_stable (Up 14h), ms_gw/logs_db (Up 3 days) 全 Up.
- buffer/wait/keymanager 日志 30min 空 (无 buffer 流量).

## 根因: buffer 对 function 级 429 无保护 (设计盲区, 非代码缺陷, 沿用 R278-R289 分析)

### 现象
- dsv4p_nv 5key (k0-k4) 全绑同一 NVCF function.
- NVCF 429 配额是 function 级: function 配额耗尽时, 5 key 同时收 429.
- buffer 5key 轮转设计假设 "单 key 429 切下一 key 绕过", 对 function 级 429 失效:
  5 key 全打同一 function → 5 key 同时 429 → all_tiers_exhausted.
- 这是设计盲区非 nv_gw 代码缺陷. R-nvonly 5key 5IP 设计针对 key/IP 级隔离, 未覆盖 function 级配额.

### 为何 hermes 边界 429/502 常态, cc2 buffer_exhausted 罕见
- hermes 走 pexec peek path: 单 key 探测 429 → 一击即败 (~2-8s), 快速释放, 不消耗 buffer.
- other caller 并发命中 cooling 窗口 → 1ms all_tiers_exhausted 瞬拒.
- cc2 走 buffer 5key 轮转: 5 key 全 429 → 消耗 ~165s → buffer_exhausted.
- cc2 流量极低, 命中 function 配额边界点概率远低于 hermes 高频探测, buffer_exhausted 罕见且自恢复.

### 结论
- **非 nv_gw 代码缺陷, 无需本轮改码**. NVCF function 级配额是上游硬限制.
- buffer 5key 轮转对 key/IP 级 429 仍有效 (R268-R290 验证), 对 function 级 429 是已知盲区.
- 当前 cc2 流量极低, buffer_exhausted 罕见且自恢复, 不达介入阈值.

## 判稳
- **NOP 巡检轮**. cc2 primary 0 req, 链路空闲健康, 0 fallback 0 deadline.
- dsv4p_nv 失败全在 hermes/other caller 打 NVCF function 级配额边界, 非 nv_gw 代码缺陷.
- 错误类型无新增, 全 all_tiers_exhausted, 与 R268-R289 一致.
- 二十三轮一致 R268-R290.

## 下一步
- 继续 NOP 巡检. 关注: (1) cc2 流量恢复后 buffer_exhausted 是否复发; (2) dsv4p_nv function 级配额是否有新边界点; (3) 是否出现新错误类型.
- 若 cc2 流量恢复且 buffer_exhausted 复发高频, 再考虑介入 (如 function 级配额检测/等待策略).

## 参数快照 (沿用 R289, 无变更)
- nv_gw: NVU_DISABLE_MS_FALLBACK=0, UPSTREAM_TIMEOUT=90, TIER_COOLDOWN_S=180, KEY_COOLDOWN_S=30, NV_INTEGRATE_KEY_COOLDOWN_S=90, TIER_TIMEOUT_BUDGET_S=180, NVU_BUFFER_MAX_RETRIES=5 (90s×5=450s), NVU_BUFFER_CALLERS=cc4101-primary,openclaw2, NVU_PEER_FB_SKIP_MODELS=glm5_2_nv,dsv4p_nv, NVU_FORCE_STREAM_UPGRADE=0, MIN_OUTBOUND_INTERVAL_S=10
- cc4101: FALLBACK_UPSTREAM_URL=http://ms_gw:40007/v1/chat/completions, CC4101_STREAM_TOTAL_DEADLINE_S=470, PRIMARY_HEADER_TIMEOUT=400, PRIMARY_UPSTREAM_MODEL=dsv4p_nv, UPSTREAM_TIMEOUT=130, UPSTREAM_IDLE_TIMEOUT=150, CC4101_PRIMARY_SKIP_S=30, CC4101_PRIMARY_FAIL_THRESHOLD=3, FALLBACK_UPSTREAM_MODEL=glm5_2_ms
- settings.json: API_TIMEOUT_MS=600000, contextWindow=170000, autoCompactWindow=155000
