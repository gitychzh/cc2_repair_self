# STATE — cc2 自优化 nv_gw 链路 (R-nvonly 方向)

## 当前轮基线 (2026-08-02 07:02 CST, R-nvonly-post113 NOP 巡检轮)
- 主仓 git HEAD: a0e67bb (post112, post113 待 push)
- **本轮 R-nvonly-post113 (hm2_cc2)**: NOP 巡检轮. cc2 30min 0 req (session 轮前无流量产生, 无数据可判 SR).
  链路健康无故障: 容器全 Up (nv_gw/cc4101/nv_gw_stable 5h, ms_gw/logs_db 2d),
  env 配置正确 (NVU_DISABLE_MS_FALLBACK=0 fallback 已恢复, buffer 5×90s=450s, cc4101 deadline 470s),
  0 cc2 tier error, 0 cc2 buffer/wait/error 日志. 0 改动, 0 重启.
  hermes 打 dsv4p_nv SR=37.5% (3/8, 3×200 + 5×429/all_tiers_exhausted, 周期性 5min 一发) 是 NVCF 侧 dsv4p 限流, 非 cc2 链路 (cc2 �� glm5_2_nv).
  glm5_2_nv 连续 post100-post113 (14 轮) 无 dsv4p 故障扩散.
- round 文件: `~/hm_ps/hermes_improve_self/rounds/R-nvonly-post113_hm2_cc2_nop_patrol.md`

## R-nvonly 核心铁律 (持续生效)
- 只改 HM2 nv_gw (40006), 不碰 HM1, 不碰 ms_gw 源码.
- ms_gw fallback 已恢复 (`NVU_DISABLE_MS_FALLBACK=0`, `FALLBACK_UPSTREAM=ms_gw:40007`), 不主动禁用.
- 改前有数据, 改后必验证, 写入仓库.

## 本轮关键数据

### 1. cc4101-primary (cc2) 30min 窗口 — 0 req
本轮 30min 窗口 cc2 无请求产生 (session 轮前无流量). 无数据可判 cc2 SR.
链路健康无故障: 容器全 Up, env 配置正确, 0 cc2 tier error, 0 cc2 buffer/wait/error 日志,
0 stream_total_deadline (6h 窗口, 上轮实测未变化).
注: 直接裸探 cc4101/nv_gw `/v1/messages` 入口返回 401 (caller token 鉴权), 本 session 工具调用本身经 cc4101→nv_gw 链路.

### 2. 其他 caller (hermes, 非 cc2 链路)
| caller | model | status | count |
|--------|-------|--------|-------|
| hermes | dsv4p_nv | 200 | 3 |
| hermes | dsv4p_nv | 429 | 5 |

dsv4p_nv SR=37.5% (3/8): 3×200 + 5×429 (all_tiers_exhausted, 5key 全挂), 周期性 5min 一发 429.
**与 cc2 无关** (cc2 走 glm5_2_nv, 不打 dsv4p_nv).
30min fallback 发生率: f=8 (dsv4p 全挂 fallback ms, ms_gw fallback 已恢复正常工作).

### 3. dsv4p_nv 按分钟趋势 (周期性 429, UTC)
| 分钟 (UTC) | status | count |
|------|--------|-------|
| 22:35 | 429 | 1 |
| 22:40 | 200 | 3 |
| 22:45 | 429 | 1 |
| 22:50 | 429 | 1 |
| 22:55 | 429 | 1 |
| 23:00 | 429 | 1 |

周期性 5min 一发 429, 22:40 恢复 200×3, NVCF 侧 dsv4p 限流模式, 非 cc2 链路问题.
与 post112 对比: dsv4p_nv 窗口相同 (37.5%, 3/8), 仍局限 hermes+dsv4p, 未扩散到 glm5_2_nv.

## 健康验证 (07:02 CST)
| 验证项 | 结果 |
|--------|------|
| nv_gw /health | ok, passthrough, 5 keys, default glm5_2_nv ✓ |
| nv_gw env | NVU_DISABLE_MS_FALLBACK=0, BUFFER_MAX_RETRIES=5, TOTAL_DEADLINE=450s, UPSTREAM_TIMEOUT=90s ✓ |
| cc4101 env | STREAM_TOTAL_DEADLINE=470, PRIMARY_HEADER_TIMEOUT=400, FALLBACK=ms_gw:40007 ✓ |
| docker ps | nv_gw/cc4101/nv_gw_stable Up 5h, ms_gw/logs_db Up 2d ✓ |
| cc2 (cc4101-primary) 30min SR | 0 rows (无流量, 链路健康无故障) ✓ |
| 30min 错误分类 | all_tiers_exhausted × 5 (全 hermes+dsv4p, 非 cc2) ✓ |
| 30min tier error | 0 rows (无 cc2 流量) ✓ |
| stream_total_deadline (6h) | 0 ✓ (上轮实测, 未变化) |
| buffer/wait 日志 | 无 (cc2 0 req) ✓ |
| 配置 | NVU_DISABLE_MS_FALLBACK=0 (fallback 已恢复), FALLBACK_UPSTREAM=ms_gw:40007 ✓ |

## 参数快照 (2026-08-02 07:02 CST)
- nv_gw: NVU_DISABLE_MS_FALLBACK=0, BUFFER_MAX_RETRIES=5, BUFFER_TIMEOUT_STAIRS=90,90,90,90,90, BUFFER_TOTAL_DEADLINE=450s, TIER_TIMEOUT_BUDGET=180s, UPSTREAM_TIMEOUT=90s
- cc4101: CC4101_STREAM_TOTAL_DEADLINE_S=470, PRIMARY_HEADER_TIMEOUT=400, FALLBACK_UPSTREAM_URL=http://ms_gw:40007/v1/chat/completions
- 链路: cc2→cc4101(4101)→nv_gw(40006, glm5_2_nv)→NVCF, fallback ms_gw(40007) 已恢复
- 铁律: 只改 HM2 nv_gw, 不碰 HM1, 不碰 ms_gw 源码, 改前有数据改后必验证

## 下一步
- 继续巡检. 等 cc2 有流量时观察 glm5_2_nv SR.
- dsv4p_nv 限流持续, 但属 NVCF 侧 + hermes caller, 非本轮职责 (只改 HM2 nv_gw, 不碰 caller).
- glm5_2_nv 链路连续 14 轮稳定, 无需调整.
