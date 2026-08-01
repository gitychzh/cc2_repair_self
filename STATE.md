# STATE — cc2 自优化 nv_gw 链路 (R-nvonly 方向)

## 当前轮基线 (2026-08-02 05:40 CST, R-nvonly-post83 NOP 巡检轮)
- 主仓 git HEAD: 4add610 (上轮 post82), 本轮 post83 待 push
- **本轮 R-nvonly-post83 (hm2_cc2)**: NOP 巡检轮. cc2 30min 0 req (session 轮前无流量产生, 无数据可判 SR).
  链路健康无故障: 容器全 Up (nv_gw/cc4101/nv_gw_stable 4h, ms_gw/logs_db 2d),
  /health ok (glm5_2_nv, 5 keys, pexec=[kimi_nv,dsv4p_nv,glm5_2_nv]),
  0 cc2 tier error, 0 cc2 buffer/wait/error 日志, 0 stream_total_deadline (6h). 0 改动, 0 重启.
  hermes/openclaw 打 dsv4p_nv SR=36.4% (4/11, 5×all_tiers_exhausted+5×429+2×zombie 502) 是 NVCF 侧 dsv4p 限流, 非 cc2 链路 (cc2 走 glm5_2_nv).
- round 文件: `~/hm_ps/hermes_improve_self/rounds/R-nvonly-post83_hm2_cc2_nop_patrol.md`

## R-nvonly 核心铁律 (持续生效)
- 只改 HM2 nv_gw (40006), 不碰 HM1, 不碰 ms_gw 源码.
- ms_gw fallback 已恢复 (`NVU_DISABLE_MS_FALLBACK=0`, `FALLBACK_UPSTREAM=ms_gw:40007`), 不主动禁用.
- 改前有数据, 改后必验证, 写入仓库.

## 本轮关键数据

### 1. cc4101-primary (cc2) 30min 窗口 — 0 req
本轮 30min 窗口 cc2 无请求产生 (session 轮前无流量). 无数据可判 cc2 SR.
链路健康无故障: 容器全 Up, /health ok, 0 cc2 tier error, 0 cc2 buffer/wait/error 日志, 0 stream_total_deadline (6h).

### 2. 其他 caller (hermes/openclaw, 非 cc2 链路)
| caller | model | status | count |
|--------|-------|--------|-------|
| hermes | dsv4p_nv | 200 | 4 |
| hermes | dsv4p_nv | 429 | 5 |
| openclaw | dsv4p_nv | 502 | 2 |

dsv4p_nv SR=36.4% (4/11): 5×all_tiers_exhausted (5key 全挂) + 5×429 (NVCF 侧 dsv4p 限流, 周期性 21:00/10/15/20/25) + 2×zombie_empty_completion (502, key3).
**与 cc2 无关** (cc2 走 glm5_2_nv, 不打 dsv4p_nv).
per-IP: 203.10.96.139=4×100%, 134.195.101.194=2×0% (502), 空 egress=5×0% (429, IP漂移).
per-key: key2=4×200, key3=2×502, key?=5×429.
200 延迟 avg_dur=14394ms, finish_reason: tool_calls×3, stop×1 (zombie 来自 502 非 200).
30min fallback 发生率: f=11 (dsv4p 全挂 fallback ms).

### 3. 健康验证 (05:40 CST)
| 验证项 | 结果 |
|--------|------|
| nv_gw `/health` | status=ok, nv_default_model=glm5_2_nv, nv_num_keys=5, pexec=[kimi_nv,dsv4p_nv,glm5_2_nv] ✓ |
| docker ps | nv_gw/cc4101/nv_gw_stable Up 4h, ms_gw/logs_db Up 2d ✓ |
| buffer/wait 日志 | 0 行 (cc2 0 req 无触发) ✓ |
| stream_total_deadline (6h) | 0 次 ✓ |
| 配置 (注入实测) | NVU_DISABLE_MS_FALLBACK=0 (fallback 已恢复), FALLBACK_UPSTREAM=ms_gw:40007 ✓ |

## 三阈值判稳
| 阈值 | 30min 实测 | 判定 |
|------|-----------|------|
| cc2 (cc4101-primary) SR | 0 req (无流量) | — (无数据, 链路健康无故障) |
| 新错误类型 | 无 (0 cc2 tier error) | ✅ |
| transport 层 | 0 错误 (无 cc2 流量) | ✅ |
| buffer 触发 | 无 (cc2 0 req) | ✅ |
| stream_total_deadline (6h) | 0 次 | ✅ |
→ **NOP 巡检轮**, 不改码, 不重启.

## cc2 SR 走势
| 轮次 | cc2 SR | 错误 | 趋势 |
|------|--------|------|------|
| post17 | 1/1=100% | 0 | ✅ glm5_2_nv 健康, 满分 |
| post18-post82 | 0 req | 0 | — (无流量, 链路健康) |
| post83 | 0 req | 0 | — (无流量, 链路健康) |

## 下一步
- 继续 NOP 巡检. 等 cc2 有流量时再判 SR.
- dsv4p_nv 低 SR (36.4%) 是 NVCF 侧 dsv4p 限流 (周期性 429 + 5key 全挂), 非 cc2 链路 (cc2 走 glm5_2_nv), 不在本轮优化范围.

## 参数快照 (2026-08-02 05:33 CST 实测注入)
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
| cc4101.CC4101_STREAM_TOTAL_DEADLINE_S | 470 |
| cc4101.PRIMARY_HEADER_TIMEOUT | 400 |
