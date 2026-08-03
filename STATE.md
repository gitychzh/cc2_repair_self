# R664 — NOP 巡检轮 — cc2 链路持平, R661 改后窗口仍无自产流量

> 时间: 2026-08-03 16:25 CST (08:17 UTC)
> 上轮: R663 (NOP, R661 改后窗口无流量待验)
> 容器: nv_gw Up 16min (R661 restart @08:02 UTC), cc4101 Up ~1h, dsv4p_nv40066 Up 58min

## 判稳结论: NOP (不改码)

R661 (handlers.py:1853 NV-ANTH-COLLECT-BUFRETRY) restart @08:02 UTC 后 ~15min 窗口 cc4101-primary 0 请求, 仍无法验证。但 cc2 用户可见链路 100% + 60min SR 87.5% 唯一 502 是 R661 restart 前 42min 旧事件非回归 + deadline 6h=0 健康 + 配置无漂移 → NOP。

## 基线 (R664 实测)
- cc2 (cc4101-primary/glm5_2_nv) nv_gw 60min: 8req SR=87.5% (7×200 avg 39495ms + 1×502)
  - 唯一 502: c1297569 @07:20:16 UTC NVAnthCollect_IncompleteRead 34384ms (R661 restart @08:02 前 42min 事件, 即 R661 修复目标本身, 非改后回归)
- cc2 30min: 0 请求 (改后窗口仍无自产流量, R661 验证仍空)
- cc4101 真实 SR 100% (16req, 1×fallback dsv4p 200 成功, fallback 触发率 6.25%)
- tier 60min glm5_2_nv: 12 attempt, 8 success (pexec_success×4 k0/k2/k4 b1b22d03/3b9748d8/b6029a96 + integrate_success×4 k1/k3) + 4 transport 失败 (pexec_SSLEOFError×2 k2/k4 + pexec_conn_RemoteDisconnected×2 k2/k4) → mark_transport 5-10s 短惩罚, 未冻结
- 全 caller 30min 错误 (非 cc2 链路): hermes all_tiers_exhausted×4 (NVCF 侧配额型 5key 全 429) + NVStream_IncompleteRead×1 (hermes)
- dsv4p_nv 30min hermes caller: 34req SR=85.3% (29×200 + 3×429 + 2×502, 配额型非本链路)
- deadline 6h: stream_total_deadline=0 (健康)
- /health ok 5keys, 配置无漂移, 无启动错误, 容器都 Up

## 下一步
- 等下一波 cc4101-primary 流量 + IncompleteRead 再现 → 查 NV-ANTH-COLLECT-BUFRETRY 日志判断 R661 是否生效
- 若 IncompleteRead 再现仍落 502 → 深查 handlers.py:1853 触发条件是否命中
- hermes/dsv4p all_tiers_exhausted 配额型持续 → 关注是否影响 cc4101 fallback 路径 (dsv4p_nv40066)

## 参数快照 (无变化, 沿用 R661)
- nv_gw: NVU_DISABLE_MS_FALLBACK=1, buffer 5×90s=450s, UPSTREAM_TIMEOUT=90, TIER_COOLDOWN_S=180
- cc4101: PRIMARY=glm5_2_nv→nv_gw:40006, FALLBACK=dsv4p_nv→dsv4p_nv40066:40066, STREAM_TOTAL=470, HEADER=400
- deadline 链: 90s×5=450s buffer < 470s cc4101 < 600s API < 900s idle
