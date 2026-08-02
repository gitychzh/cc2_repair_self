# STATE — cc2 自优化 nv_gw 链路 (R-nvonly 方向)

## 当前轮基线 (2026-08-02 09:14 CST, R-nvonly-post160 NOP 巡检轮)
- 主仓 git HEAD: 9c6434c (post159), 本轮 post160 待 push
- **本轮 R-nvonly-post160 (hm2_cc2)**: NOP 巡检轮. cc2 30min 0 req (session 轮前无流量产生, 无数据可判 SR).
  链路健康无故障: nv_gw /health ok (5 keys, default glm5_2_nv), env 配置正确,
  0 cc2 tier error, 0 cc2 buffer/wait/error 日志.
  0 改动, 0 重启.
  hermes 打 dsv4p_nv 6×429 (all_tiers_exhausted, NVCF 侧 dsv4p 限流 5min 周期) + openclaw 2×200 佐证链路可用,
  非 cc2 链路 (cc2 走 glm5_2_nv).
  glm5_2_nv 连续 post100-post160 (61 轮) 无 dsv4p 故障扩散.
- round 文件: `~/hm_ps/hermes_improve_self/rounds/R-nvonly-post160_hm2_cc2_nop_patrol.md`

## R-nvonly 核心铁律 (持续生效)
- 只改 HM2 nv_gw (40006), 不碰 HM1, 不碰 ms_gw 源码.
- ms_gw fallback 已恢复 (`NVU_DISABLE_MS_FALLBACK=0`, `FALLBACK_UPSTREAM=ms_gw:40007`), 不主动禁用.
- 改前有数据, 改后必验证, 写入仓库.

## 本轮关键数据

### 1. cc4101-primary (cc2) 30min 窗口 — 0 req
本轮 30min 窗口 cc2 无请求产生. 无数据可判 cc2 SR. 链路健康无故障.

### 2. 其他 caller (hermes/openclaw, 非 cc2 链路)
| caller | status | count |
|--------|--------|-------|
| hermes | 429 | 6 |
| openclaw | 200 | 2 |

dsv4p_nv (hermes): 6×429 (all_tiers_exhausted, 5key 全挂, NVCF 侧 dsv4p 限流 5min 周期).
dsv4p_nv (openclaw): 2×200 (链路本身可用, 佐证 429 是 NVCF 配额限流非链路挂).
**与 cc2 无关** (cc2 走 glm5_2_nv, 不打 dsv4p_nv).

### 3. 30min 错误分类
| error_type | count |
|------------|-------|
| all_tiers_exhausted | 6 |

全部 6× 是 hermes→dsv4p_nv 的 NVCF 限流, 非 cc2 链路.

### 4. tier 错误 — 0
### 5. buffer/wait 日志 — 空

## 健康验证 (09:14 CST)
| 验证项 | 结果 |
|--------|------|
| nv_gw /health | ok, passthrough, 5 keys, default glm5_2_nv ✓ |
| docker ps | nv_gw/cc4101/nv_gw_stable Up 7h, ms_gw/logs_db Up 2d ✓ |
| cc2 (cc4101-primary) 30min SR | 0 rows (无流量, 链路健康无故障) ✓ |
| 30min tier error | 0 ✓ |
| 30min 全 caller | hermes 6×429 (dsv4p_nv 限流), openclaw 2×200 (dsv4p_nv 成功), cc2 0 req ✓ |
| 配置 | NVU_DISABLE_MS_FALLBACK=0 (fallback 已恢复), FALLBACK_UPSTREAM=ms_gw:40007 ✓ |

## 参数快照 (2026-08-02 09:14 CST)
- nv_gw: NVU_DISABLE_MS_FALLBACK=0, BUFFER_MAX_RETRIES=5, BUFFER_TIMEOUT_STAIRS=90,90,90,90,90, BUFFER_TOTAL_DEADLINE=450s, TIER_TIMEOUT_BUDGET=180s, UPSTREAM_TIMEOUT=90s, KEY_COOLDOWN_S=30, NV_INTEGRATE_KEY_COOLDOWN_S=90, MIN_OUTBOUND_INTERVAL_S=10, TIER_COOLDOWN_S=180
- cc4101: CC4101_STREAM_TOTAL_DEADLINE_S=470, PRIMARY_HEADER_TIMEOUT=400, UPSTREAM_TIMEOUT=130, FALLBACK_UPSTREAM_URL=http://ms_gw:40007/v1/chat/completions, PRIMARY_UPSTREAM_URL=http://nv_gw:40006/v1/messages, PRIMARY_UPSTREAM_MODEL=glm5_2_nv, FALLBACK_UPSTREAM_MODEL=glm5_2_ms
