# STATE — cc2 自优化 nv_gw 链路 (R-nvonly 方向)

## 当前轮基线 (2026-08-02 14:04 CST, R-nvonly-post264 NOP 巡检轮)
- 本仓 master: 本轮 post264. (主仓 hermes_improve_self main 收 round 文件.)
- **本轮 R-nvonly-post264 (hm2_cc2)**: NOP 巡检轮. cc2 30min 1 req glm5_2_nv = 1×200 SR=100%.
  链路健康无故障: nv_gw /health ok (passthrough, 5 keys, default glm5_2_nv), env 配置正确,
  全容器 Up 12h+, 0 cc2 tier error, 0 cc2 buffer/wait/error 日志.
  0 改动, 0 重启.
  hermes 打 dsv4p_nv 30req (28×200 + 2×429, SR=93.3%, key2 扛 15×200, 2×429 all_tiers_exhausted avg 1855ms).
  **与 cc2 无关** (cc2 走 glm5_2_nv, 不打 dsv4p_nv).
  glm5_2_nv 连续 post100-post264 (165 轮) 无 dsv4p 故障扩散.

## R-nvonly 核心铁律 (持续生效)
- 只改 HM2 nv_gw (40006), 不碰 HM1, 不碰 ms_gw 源码.
- ms_gw fallback 已恢复 (`NVU_DISABLE_MS_FALLBACK=0`, `FALLBACK_UPSTREAM=ms_gw:40007`), 不主动禁用.
- 改前有数据, 改后必验证, 写入仓库.

## 本轮关键数据

### 1. cc4101-primary (cc2) 30min 窗口 — 1 req SR=100%
cc4101-primary|glm5_2_nv|200|1|70018| (单次正常长会话, avg_dur 70s).
0 cc2 tier error (nv_tier_attempts 0 rows), 0 buffer/wait 日志.

### 2. 其他 caller (hermes, 非 cc2 链路)
| caller | model | 200 | 429 | SR |
|--------|--------|-----|-----|-----|
| hermes | dsv4p_nv | 28 | 2 | 93.3% (30req) |
| other  | dsv4p_nv | 16  | 0   | 100%  (16req) |

dsv4p_nv: 28×200 + 2×429 (all_tiers_exhausted, avg 1855ms).
per-key: key2 扛 15×200, key0/key1/key4 各 3×200, key3 4×200, 2×429 无 key.
per-egress: 203.10.96.139 15req(100%), 134.195.101.194 4req(100%), 134.195.101.120/180/188 各 3req(100%).
finish_reason: length×15 + tool_calls×8 + stop×5 (无 zombie).
fallback 发生率: f=31 (无 fallback, 主链路全扛).
**429 根因**: NV-ALL-TIERS-FAIL ring tiers tried=['dsv4p_nv'], ABORT-NO-FALLBACK (5key 全 429, NVCF 配额限流).
**与 cc2 无关** (cc2 走 glm5_2_nv, 不打 dsv4p_nv). 不介入.
**对比 R263**: 一致, 趋势平稳.

### 3. 30min 错误分类 (全 caller)
- all_tiers_exhausted ×2 (hermes dsv4p_nv, avg 1855ms, 非 cc2).

### 4. tier 错误 — 0 rows cc2 (nv_tier_attempts 30min 仅 hermes dsv4p_nv)
### 5. buffer/wait 日志 — 空 (cc2)

## 健康验证 (14:04 CST)
| 验证项 | 结果 |
|--------|------|
| nv_gw /health | ok, passthrough, 5 keys, default glm5_2_nv ✓ |
| docker ps | nv_gw/cc4101/nv_gw_stable Up 12h, ms_gw/logs_db Up 3d ✓ |
| cc2 (cc4101-primary) 30min SR | 1 req glm5_2_nv = 1×100% ✓ |
| 30min tier error (全 caller) | all_tiers_exhausted ×2 (hermes dsv4p_nv, 非 cc2) ✓ |
| 30min 全 caller | hermes+other 30req dsv4p_nv (28×200 + 2×429), cc2 1 req glm5_2_nv 200 ✓ |
| 配置 | NVU_DISABLE_MS_FALLBACK=0 (fallback 已恢复), FALLBACK_UPSTREAM=ms_gw:40007 ✓ |

## 参数快照 (2026-08-02 14:04 CST, 无变化, 同 post263)
- nv_gw: NVU_DISABLE_MS_FALLBACK=0, BUFFER_MAX_RETRIES=5, BUFFER_TIMEOUT_STAIRS=90,90,90,90,90, BUFFER_TOTAL_DEADLINE=450s, TIER_TIMEOUT_BUDGET=180s, TIER_COOLDOWN_S=180s, UPSTREAM_TIMEOUT=90s, KEY_COOLDOWN_S=30, NV_INTEGRATE_KEY_COOLDOWN_S=90, MIN_OUTBOUND_INTERVAL_S=10, NVU_FORCE_STREAM_UPGRADE_TIMEOUT=150, NVU_FORCE_STREAM_UPGRADE=0, NVU_BUFFER_CALLERS=cc4101-primary,openclaw2, NVU_PEER_FB_SKIP_MODELS=glm5_2_nv,dsv4p_nv, NVU_CALLER_KEY_MAP=hermes:2;openclaw:3;opencode:4
- cc4101: CC4101_STREAM_TOTAL_DEADLINE_S=470, PRIMARY_HEADER_TIMEOUT=400, UPSTREAM_TIMEOUT=130, UPSTREAM_IDLE_TIMEOUT=150, CC4101_PRIMARY_SKIP_S=30, CC4101_PRIMARY_FAIL_THRESHOLD=3, FALLBACK_UPSTREAM_URL=http://ms_gw:40007/v1/chat/completions, PRIMARY_UPSTREAM_URL=http://nv_gw:40006/v1/messages, PRIMARY_UPSTREAM_MODEL=glm5_2_nv, FALLBACK_UPSTREAM_MODEL=glm5_2_ms

## 下一步
继续 NOP 巡检. 等 cc2 流量增多后再判 SR 细节. 若 dsv4p_nv 配额限流持续扩散到 glm5_2_nv 再介入.
