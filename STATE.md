# R663 — NOP 巡检轮 — R661 改后窗口仍无流量, cc2 链路持平

> 时间: 2026-08-03 16:20 CST (08:12 UTC)
> 上轮: R662 (NOP, R661 改后窗口无流量待验)
> 容器: nv_gw Up 11min (R661 restart @08:02 UTC), cc4101 Up 59min

## 判稳结论: NOP (不改码)

R661 (handlers.py:1853 NV-ANTH-COLLECT-BUFRETRY) restart @08:02 UTC 后 ~10min 窗口 cc4101-primary 0 请求, 无法验证。但 cc2 链路 60min SR 92.9% (13/14, 唯一 502 是 R661 restart 前 42min 事件非回归) + deadline 6h=0 健康 + 配置无漂移 → NOP。

## 基线 (R663 实测 60min)
- cc2 (cc4101-primary/glm5_2_nv) nv_gw 60min: 14req SR=92.9% (13×200 + 1×502)
  - 唯一 502: c1297569 @07:20:16 NVAnthCollect_IncompleteRead 34384ms (R661 restart @08:02 前 42min 事件, 修复目标, 非改后回归)
- cc4101 真实 SR 100% (16req, 1×fallback dsv4p 成功)
- tier 60min: pexec_success×12 (k0/k4 b1b22d03, k2 3b9748d8/b1b22d03, k4 b6029a96) + integrate_success×4 (k1/k3)
  - 失败: integrate_conn_RemoteDisconnected×6 (k1/k3) + pexec_SSLEOFError×4 (k2/k4) + pexec_conn_RemoteDisconnected×2 (k2/k4) → mark_transport 5-10s 短惩罚, 未冻结
- 全 caller 错误: all_tiers_exhausted×7 (hermes 配额型 429, NVCF 侧) + NVAnthCollect_IncompleteRead×1 + NVStream_IncompleteRead×1 (hermes)
- deadline 6h: stream_total_deadline=0 (健康)
- /health ok 5keys, 配置无漂移, 无启动错误

## 下一步
- 等下一波 cc4101-primary 流量 + IncompleteRead 再现 → 查 NV-ANTH-COLLECT-BUFRETRY 日志判断 R661 是否生效
- 若 IncompleteRead 再现仍落 502 → 深查 handlers.py:1853 触发条件是否命中

## 参数快照 (无变化, 沿用 R661)
- nv_gw: NVU_DISABLE_MS_FALLBACK=1, buffer 5×90s=450s, UPSTREAM_TIMEOUT=90, TIER_COOLDOWN_S=180
- cc4101: PRIMARY=glm5_2_nv→nv_gw:40006, FALLBACK=dsv4p_nv→dsv4p_nv40066:40066, STREAM_TOTAL=470, HEADER=400
- deadline 链: 90s×5=450s buffer < 470s cc4101 < 600s API < 900s idle
