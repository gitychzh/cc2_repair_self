# STATE — cc2 自优化 nv_gw 链路 (R-nvonly 方向)

## 当前轮基线 (2026-08-02 13:37 CST, R-nvonly-post256 NOP 巡检轮)
- 本仓 master: 本轮 post256. (主仓 hermes_improve_self main 收 round 文件.)
- **本轮 R-nvonly-post256 (hm2_cc2)**: NOP 巡检轮. cc2 30min 0 req (session 轮前无流量产生, 无数据可判 SR).
  链路健康无故障: nv_gw /health ok (passthrough, 5 keys, default glm5_2_nv), env 配置正确,
  全容器 Up 12h+, 0 cc2 tier error, 0 cc2 buffer/wait/error 日志.
  0 改动, 0 重启.
  hermes 打 dsv4p_nv 14req (9×200 + 4×429 + 1×502, SR=64.3%, key2 扛 9×200+1×502, 4×429 all_tiers_exhausted avg 2698ms, 1×502 NVStream_IncompleteRead avg 34130ms).
  **与 cc2 无关** (cc2 走 glm5_2_nv, 不打 dsv4p_nv).
  glm5_2_nv 连续 post100-post256 (157 轮) 无 dsv4p 故障扩散.

## R-nvonly 核心铁律 (持续生效)
- 只改 HM2 nv_gw (40006), 不碰 HM1, 不碰 ms_gw 源码.
- ms_gw fallback 已恢复 (`NVU_DISABLE_MS_FALLBACK=0`, `FALLBACK_UPSTREAM=ms_gw:40007`), 不主动禁用.
- 改前有数据, 改后必验证, 写入仓库.

## 本轮关键数据

### 1. cc4101-primary (cc2) 30min 窗口 — 0 req
本轮 30min cc2 无请求产生. 无数据可判 cc2 SR. 链路健康无故障.

### 2. 其他 caller (hermes, 非 cc2 链路)
| caller | model | 200 | 429 | 502 | SR |
|--------|--------|-----|-----|-----|-----|
| hermes | dsv4p_nv | 9 | 4 | 1 | 64.3% (14req) |

dsv4p_nv SR=64.3% (14/14): 9×200 + 4×429 (all_tiers_exhausted, avg 2698ms) + 1×502 (NVStream_IncompleteRead avg 34130ms).
per-key: key2 扛 9×200 (avg 9639ms) + 1×502, 4×429 无 key.
per-egress: 203.10.96.139 10×200 (90ms), 4×429 无 IP.
finish_reason: tool_calls×8, stop×1 (无 zombie).
fallback 发生率: 0/14 (无 fallback, 主链路全扛).
按分钟趋势: 05:10-05:11 稳定 200, 05:15 1×429, 05:20 1×429, 05:25 1×429, 05:30 3×200, 05:31 1×502, 05:35 1×429.
**429/502 根因**: NV-ALL-TIERS-FAIL ring tiers tried=['dsv4p_nv'], ABORT-NO-FALLBACK; key2 中途一次 IncompleteRead.
**与 cc2 无关** (cc2 走 glm5_2_nv, 不打 dsv4p_nv). 不介入.

### 3. 30min 错误分类 (全 caller)
- all_tiers_exhausted ×4 (hermes dsv4p_nv, avg 2698ms, 非 cc2).
- NVStream_IncompleteRead ×1 (hermes dsv4p_nv key2, avg 34130ms, 非 cc2).

### 4. tier 错误 — 0 rows (nv_tier_attempts 30min 空, cc2 无 tier 流量)
### 5. buffer/wait 日志 — 空 (cc2)

## 健康验证 (13:37 CST)
| 验证项 | 结果 |
|--------|------|
| nv_gw /health | ok, passthrough, 5 keys, default glm5_2_nv ✓ |
| docker ps | nv_gw/cc4101/nv_gw_stable Up 12h, ms_gw/logs_db Up 3d ✓ |
| cc2 (cc4101-primary) 30min SR | 0 rows (无流量, 链路健康无故障) ✓ |
| 30min tier error (全 caller) | all_tiers_exhausted ×4 + NVStream_IncompleteRead ×1 (hermes dsv4p_nv, 非 cc2) ✓ |
| 30min 全 caller | hermes 14req dsv4p_nv (9×200 + 4×429 + 1×502), cc2 0 req ✓ |
| 配置 | NVU_DISABLE_MS_FALLBACK=0 (fallback 已恢复), FALLBACK_UPSTREAM=ms_gw:40007 ✓ |

## 参数快照 (2026-08-02 13:37 CST, 无变化, 同 post255)
- nv_gw: NVU_DISABLE_MS_FALLBACK=0, BUFFER_MAX_RETRIES=5, BUFFER_TIMEOUT_STAIRS=90,90,90,90,90, BUFFER_TOTAL_DEADLINE=450s, TIER_TIMEOUT_BUDGET=180s, TIER_COOLDOWN_S=180s, UPSTREAM_TIMEOUT=90s, KEY_COOLDOWN_S=30, NV_INTEGRATE_KEY_COOLDOWN_S=90, MIN_OUTBOUND_INTERVAL_S=10, NVU_FORCE_STREAM_UPGRADE_TIMEOUT=150, NVU_FORCE_STREAM_UPGRADE=0, NVU_BUFFER_CALLERS=cc4101-primary,openclaw2, NVU_PEER_FB_SKIP_MODELS=glm5_2_nv,dsv4p_nv, NVU_CALLER_KEY_MAP=hermes:2;openclaw:3;opencode:4
- cc4101: CC4101_STREAM_TOTAL_DEADLINE_S=470, PRIMARY_HEADER_TIMEOUT=400, UPSTREAM_TIMEOUT=130, UPSTREAM_IDLE_TIMEOUT=150, CC4101_PRIMARY_SKIP_S=30, CC4101_PRIMARY_FAIL_THRESHOLD=3, FALLBACK_UPSTREAM_URL=http://ms_gw:40007/v1/chat/completions, PRIMARY_UPSTREAM_URL=http://nv_gw:40006/v1/messages, PRIMARY_UPSTREAM_MODEL=glm5_2_nv, FALLBACK_UPSTREAM_MODEL=glm5_2_ms

## 下一步
继续 NOP 巡检. 等 cc2 流量产生后再判 SR. 若 dsv4p_nv 配额限流持续扩散到 glm5_2_nv 再介入.
