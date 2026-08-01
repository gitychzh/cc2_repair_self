# STATE — cc2 自优化 nv_gw 链路 (R-nvonly 方向)

## 当前轮基线 (2026-08-02 03:50 CST, R-nvonly-post43 NOP 巡检轮)
- 主仓 git HEAD: d9821ae (post43 round 已 commit+push)
- **本轮 R-nvonly-post43 (hm2_cc2)**: NOP 巡检轮. cc2 30min 0 req (session 轮前无流量产生, 无数据可判 SR).
  链路健康无故障: 容器全 Up, /health ok (glm5_2_nv, 5 keys), 0 tier error, 0 buffer/wait/error 日志.
  0 改动, 0 重启. post17~post27 连续满分记录保持 (11 连庄, post28-post43 均 0 req 不计入连庄也不打断).
  hermes caller 打 dsv4p_nv SR=0% (0/6, 6×all_tiers_exhausted) 是 NVCF 侧 dsv4p 限流, 非 cc2 链路 (cc2 走 glm5_2_nv).
- round 文件: `~/hm_ps/hermes_improve_self/rounds/R-nvonly-post43_hm2_cc2_nop_patrol.md`

## R-nvonly 核心铁律 (持续生效, 按 prompt 当前指令)
- 只改 HM2 nv_gw (40006), 不碰 HM1, 不碰 ms_gw 源码.
- ms_gw fallback 已恢复 (`NVU_DISABLE_MS_FALLBACK=0`, `FALLBACK_UPSTREAM=ms_gw:40007`), 不主动禁用.
- 改前有数据, 改后必验证, 写入仓库.

## 本轮关键数据

### 1. cc4101-primary (cc2) 30min 窗口 — 0 req
本轮 30min 窗口 cc2 无请求产生 (session 轮前无流量). 无数据可判 cc2 SR.
链路健康无故障: 容器全 Up, /health ok, 0 tier error, 0 buffer/wait/error 日志.

### 2. 其他 caller (hermes, 非 cc2 链路)
| caller | model | status | count |
|--------|-------|--------|-------|
| hermes | dsv4p_nv | 429 | 6 |

dsv4p_nv SR=0% (0/6), top error: all_tiers_exhausted ×6 (5key 全挂, NVCF 侧限流).
**与 cc2 无关** (cc2 走 glm5_2_nv, 不打 dsv4p_nv).
30min 趋势: 19:10-19:35 每隔 5min 1 次 429 → NVCF 侧持续限流.

### 3. 健康验证
| 验证项 | 结果 |
|--------|------|
| nv_gw `/health` | status=ok, nv_default_model=glm5_2_nv, nv_num_keys=5, pexec_models=[kimi_nv,dsv4p_nv,glm5_2_nv] ✓ |
| docker ps | cc4101/nv_gw Up 2h, nv_gw_stable Up 2h, ms_gw/logs_db Up 2d ✓ |
| nv_tier_attempts 30min | 0 rows (0 error) ✓ |
| buffer/wait/error 日志 | 30min 无 (cc2 0 req, 无流量) ✓ |
| 配置 (注入实测) | NVU_DISABLE_MS_FALLBACK=0 (fallback 已恢复), FALLBACK_UPSTREAM=ms_gw:40007 ✓ |

## 三阈值判稳
| 阈值 | 30min 实测 | 判定 |
|------|-----------|------|
| cc2 (cc4101-primary) SR | 0 req (无流量) | — (无数据, 链路健康无故障) |
| 新错误类型 | 无 (0 tier error, 0 buffer/wait 日志) | ✅ |
| transport 层 | 0 错误 (无 cc2 流量) | ✅ |
| buffer 触发 | 无 (cc2 0 req) | ✅ |
→ **NOP 巡检轮**, 不改码, 不重启.

## cc2 SR 走势
| 轮次 | cc2 SR | 错误 | 趋势 |
|------|--------|------|------|
| post17 | 1/1=100% | 0 | ✅ glm5_2_nv 健康, 满分 |
| post18 | 1/1=100% | 0 | ✅ 连续满分 |
| post19 | 2/2=100% | 0 | ✅ 连续满分 |
| post20 | 2/2=100% | 0 | ✅ 连续满分 |
| post21 | 2/2=100% | 0 | ✅ 5 连庄 |
| post22 | 3/3=100% | 0 | ✅ 6 连庄 (含 1 次 ms_gw fallback 兜底) |
| post23 | 2/2=100% | 0 | ✅ 7 连庄 (含 1 次 ms_gw fallback 兜底) |
| post24 | 2/2=100% | 0 | ✅ 8 连庄 (含 1 次 ms_gw fallback 兜底) |
| post25 | 2/2=100% | 0 | ✅ 9 连庄 (含 1 次 ms_gw fallback 兜底) |
| post26 | 1/1=100% | 0 | ✅ 10 连庄 (1 次 ms_gw fallback 兜底) |
| post27 | 1/1=100% | 0 | ✅ 11 连庄 (1 次 ms_gw fallback 兜底) |
| post28-post42 | 0 req | 0 | — (无流量, 链路健康, 不打断) |
| **post43** | **0 req** | **0** | — (无流量, 链路健康, 不打断) |

## 参数快照 (实测 2026-08-02 03:36 注入)
- nv_gw: `NVU_DISABLE_MS_FALLBACK=0`, `NVU_BUFFER_MAX_RETRIES=5`, `TIER_TIMEOUT_BUDGET_S=180`, `UPSTREAM_TIMEOUT=90`, `NVU_PEER_FB_SKIP_MODELS=glm5_2_nv,dsv4p_nv`, `NVU_BUFFER_CALLERS=cc4101-primary,openclaw2`, `MIN_OUTBOUND_INTERVAL_S=10`, `TIER_COOLDOWN_S=180`, `KEY_COOLDOWN_S=30`, `NV_INTEGRATE_KEY_COOLDOWN_S=90`, `NVU_FORCE_STREAM_UPGRADE=0`, `NVU_FORCE_STREAM_UPGRADE_TIMEOUT=150`, `NVU_BUFFER_TIMEOUT_STAIRS=90,90,90,90,90`, `NVU_BUFFER_TOTAL_DEADLINE_S=450`, `NVU_CALLER_KEY_MAP=hermes:2;openclaw:3;opencode:4`
- cc4101: `CC4101_STREAM_TOTAL_DEADLINE_S=470`, `FALLBACK_UPSTREAM=ms_gw:40007`, `FALLBACK_UPSTREAM_MODEL=glm5_2_ms`, `PRIMARY_UPSTREAM_MODEL=glm5_2_nv`, `PRIMARY_UPSTREAM=nv_gw:40006`, `PRIMARY_HEADER_TIMEOUT=400`, `UPSTREAM_TIMEOUT=130`, `CC4101_PRIMARY_FAIL_THRESHOLD=3`, `CC4101_PRIMARY_SKIP_S=30`, `UPSTREAM_IDLE_TIMEOUT=150`
- settings.json: `contextWindow=170000`, `autoCompactWindow=155000`, `API_TIMEOUT_MS=600000`

## 下一步
- 继续 NOP 巡检. 等 cc2 产生流量后再判 SR (本轮 0 req 是 session 轮前无流量, 非链路故障).
- 关注 dsv4p_nv (hermes) 限流是否缓解 (NVCF 侧问题, 非 cc2).
- 若 cc2 出现新错误或 SR<99% (排除 fallback 兜底), 再找根因小步改.
