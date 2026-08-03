# R665 — NOP 巡检轮 — cc2 链路 100% 持续, R661 修复窗口 2.5h 仍无 IncompleteRead 再现

> 时间: 2026-08-03 16:30 CST (08:30 UTC)
> 上轮: R664 (NOP, R661 改后窗口无流量待验)
> 容器: nv_gw Up ~1h, cc4101 Up ~1h, dsv4p_nv40066 Up ~1h

## 判稳结论: NOP (不改码)

R661 (handlers.py:1853 NV-ANTH-COLLECT-BUFRETRY) restart @08:02 UTC 后 ~2.5h 窗口:
- cc2 (cc4101-primary/glm5_2_nv) 60min: 5×200 SR=100%, 0 error
- cc4101 真实 SR 60min=100% (5/5, fb=0), 6h=100% (16/16, fb=6.25%)
- R661 修复目标 (IncompleteRead→502) 窗口仍无再现事件
- deadline 6h stream_total_deadline=0 (健康)
- /health ok 5keys, 配置无漂移 → NOP

## 基线 (R665 实测)
- cc2 (cc4101-primary/glm5_2_nv) nv_gw 60min: 5req SR=100% (5×200 avg 12-101s)
- cc4101 真实 SR 60min=100% (5/5, 0 fallback), 6h=100% (16/16, fb=6.25%)
- tier 60min glm5_2_nv: success×5 (k0 pexec b1b22d03×2 + k1 integrate×1 + k3 integrate×2) + transport_fail×4 (k2/k4 SSLEOF×2 + RemoteDisconnected×2) — buffer 重试覆盖后用户仍 200
- 全 caller 错误: 注入的 30min dsv4p_nv SR=84.4% + all_tiers_exhausted×5 是 hermes caller 配额型 (NVCF 侧 dsv4p_nv 5key 全 429), 非 cc2 链路
- deadline 6h: stream_total_deadline=0 (健康)
- /health ok 5keys, 配置无漂移, 无启动错误, 容器都 Up

## 下一步
- 等下一波 cc4101-primary 流量 + IncompleteRead 再现 → 查 NV-ANTH-COLLECT-BUFRETRY 日志判断 R661 是否生效
- 若 IncompleteRead 再现仍落 502 → 深查 handlers.py:1853 触发条件是否命中
- hermes/dsv4p all_tiers_exhausted 配额型持续 → 关注 dsv4p_nv40066 fallback 路径可用性

## 参数快照 (无变化, 沿用 R661)
- nv_gw: NVU_DISABLE_MS_FALLBACK=1, buffer 5×90s=450s, UPSTREAM_TIMEOUT=90, TIER_COOLDOWN_S=180
  - per-key FID bind: NV_GLM52_KEY_FID_BIND=0:0;2:1;4:2 (k0/k2/k4 pexec fid1/2/3)
  - per-key mode bind: NV_GLM52_KEY_MODE_BIND=0:pexec_us_rr;1:integrate_us_rr;2:pexec_us_rr;3:integrate_us_rr;4:pexec_us_rr
- cc4101: PRIMARY=glm5_2_nv→nv_gw:40006, FALLBACK=dsv4p_nv→dsv4p_nv40066:40066, STREAM_TOTAL=470, HEADER=400, UPSTREAM_IDLE=150
- deadline 链: 90s×5=450s buffer < 470s cc4101 < 600s API < 900s idle
