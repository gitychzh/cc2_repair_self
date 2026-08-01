# STATE — cc2 自优化 nv_gw 链路 (R-nvonly 方向)

## 当前轮基线 (2026-08-02 05:52 CST, R-nvonly-post89 NOP 巡检轮)
- 主仓 git HEAD: 821978e (上轮 post88), 本轮 post89 已 push NVForge main
- **本轮 R-nvonly-post89 (hm2_cc2)**: NOP 巡检轮. cc2 30min 0 req (session 轮前无流量产生, 无数据可判 SR).
  链路健康无故障: 容器全 Up (nv_gw/cc4101/nv_gw_stable 4h, ms_gw/logs_db 2d),
  /health ok (glm5_2_nv, 5 keys, pexec=[kimi_nv,dsv4p_nv,glm5_2_nv]),
  0 cc2 tier error, 0 cc2 buffer/wait/error 日志. 0 改动, 0 重启.
  hermes 打 dsv4p_nv SR=37.5% (3/8, 5×429+all_tiers_exhausted, 周期性 5min 一发) 是 NVCF 侧 dsv4p 限流, 非 cc2 链路 (cc2 走 glm5_2_nv).
- round 文件: `~/hm_ps/hermes_improve_self/rounds/R-nvonly-post89_hm2_cc2_nop_patrol.md`

## R-nvonly 核心铁律 (持续生效)
- 只改 HM2 nv_gw (40006), 不碰 HM1, 不碰 ms_gw 源码.
- ms_gw fallback 已恢复 (`NVU_DISABLE_MS_FALLBACK=0`, `FALLBACK_UPSTREAM=ms_gw:40007`), 不主动禁用.
- 改前有数据, 改后必验证, 写入仓库.

## 本轮关键数据

### 1. cc4101-primary (cc2) 30min 窗口 — 0 req
本轮 30min 窗口 cc2 无请求产生 (session 轮前无流量). 无数据可判 cc2 SR.
链路健康无故障: 容器全 Up, /health ok, 0 cc2 tier error, 0 cc2 buffer/wait/error 日志.

### 2. 其他 caller (hermes, 非 cc2 链路)
| caller | model | status | count |
|--------|-------|--------|-------|
| hermes | dsv4p_nv | 200 | 3 |
| hermes | dsv4p_nv | 429 | 5 |

dsv4p_nv SR=37.5% (3/8): 5×429 (all_tiers_exhausted, 5key 全挂), 周期性 5min 一发 429.
**与 cc2 无关** (cc2 走 glm5_2_nv, 不打 dsv4p_nv).
30min fallback 发生率: f=8 (dsv4p 全挂 fallback ms, ms_gw fallback 已恢复正常工作).

### 3. dsv4p_nv 按分钟趋势 (周期性 429)
| 分钟 | status | count |
|------|--------|-------|
| 21:25 | 429 | 1 |
| 21:30 | 429 | 1 |
| 21:35 | 429 | 1 |
| 21:40 | 200 | 3 |
| 21:45 | 429 | 1 |
| 21:50 | 429 | 1 |

周期性 5min 一发 429, NVCF 侧 dsv4p 限流模式, 非 cc2 链路问题.

## 健康验证 (05:52 CST)
| 验证项 | 结果 |
|--------|------|
| nv_gw `/health` | status=ok, nv_default_model=glm5_2_nv, nv_num_keys=5, pexec=[kimi_nv,dsv4p_nv,glm5_2_nv] ✓ |
| docker ps | nv_gw/cc4101/nv_gw_stable Up 4h, ms_gw/logs_db Up 2d ✓ |
| cc2 tier error (30min) | 0 ✓ |
| 配置 | NVU_DISABLE_MS_FALLBACK=0 (fallback 已恢复), FALLBACK_UPSTREAM=ms_gw:40007 ✓ |
| git HEAD (hermes_improve_self) | 821978e (post88), Already up to date ✓ |

## 三阈值判稳
| 阈值 | 30min 实测 | 判定 |
|------|-----------|------|
| cc2 (cc4101-primary) SR | 0 req (无流量) | — (无数据, 链路健康无故障) |
| 新错误类型 | 无 (0 cc2 tier error) | ✅ |
| transport 层 | 0 错误 (无 cc2 流量) | ✅ |
| buffer 触发 | 无 (cc2 0 req) | ✅ |
→ **NOP 巡检轮**, 不改码, 不重启.

## cc2 SR 走势
| 轮次 | cc2 SR | 错误 | 趋势 |
|------|--------|------|------|
| post17 | 1/1=100% | 0 | ✅ glm5_2_nv 健康, 满分 |
| post18-post88 | 0 req | 0 | — (无流量, 链路健康) |
| post89 | 0 req | 0 | — (无流量, 链路健康) |

## 下一步
- 继续 NOP 巡检. 等 cc2 有流量时再判 SR.
- dsv4p_nv 低 SR (37.5%) 是 NVCF 侧 dsv4p 限流 (周期性 429 + 5key 全挂), 非 cc2 链路 (cc2 走 glm5_2_nv), 不在本轮优化范围.

## 参数快照 (2026-08-02 05:50 CST 实测注入)
| 参数 | 值 |
|------|-----|
| nv_gw.UPSTREAM_TIMEOUT | 90 |
| nv_gw.TIER_COOLDOWN_S | 180 |
| nv_gw.TIER_TIMEOUT_BUDGET_S | 180 |
| nv_gw.KEY_COOLDOWN_S | 30 |
| nv_gw.NV_INTEGRATE_KEY_COOLDOWN_S | 90 |
| nv_gw.MIN_OUTBOUND_INTERVAL_S | 10 |
| nv_gw.NVU_DISABLE_MS_FALLBACK | 0 (fallback 已恢复) |
| nv_gw.NVU_BUFFER_CALLERS | cc4101-primary,openclaw2 |
| nv_gw.NVU_PEER_FB_SKIP_MODELS | glm5_2_nv,dsv4p_nv |
| nv_gw.NVU_CALLER_KEY_MAP | hermes:2;openclaw:3;opencode:4 |
| nv_gw.NVU_FORCE_STREAM_UPGRADE | 0 |
| cc4101.CC4101_STREAM_TOTAL_DEADLINE_S | 470 |
| cc4101.PRIMARY_HEADER_TIMEOUT | 400 |
| cc4101.UPSTREAM_TIMEOUT | 130 |
| cc4101.UPSTREAM_IDLE_TIMEOUT | 150 |
| cc4101.CC4101_PRIMARY_FAIL_THRESHOLD | 3 |
| cc4101.CC4101_PRIMARY_SKIP_S | 30 |
| cc4101.PRIMARY_UPSTREAM_MODEL | glm5_2_nv |
| cc4101.FALLBACK_UPSTREAM_MODEL | glm5_2_ms |
| cc4101.FALLBACK_UPSTREAM_URL | http://ms_gw:40007/v1/chat/completions |
| cc4101.PRIMARY_UPSTREAM_URL | http://nv_gw:40006/v1/messages |
