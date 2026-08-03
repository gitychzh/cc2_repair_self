# R662 — NOP 巡检轮 — R661 collect-buffer-retry 改后窗口无流量待验

> 时间: 2026-08-03 16:12 CST
> 上轮: R661 (collect 传输中断→buffer 5key 重试, R651 阈值首次触发后实施)
> 容器: nv_gw Up 6min (R661 restart @16:03), cc4101 Up 54min

## 判稳结论: NOP (不改码)

R661 上一轮刚改码 (handlers.py:1853 插入 NV-ANTH-COLLECT-BUFRETRY 块, 针对非流式 collect 路径传输中断类错误 NVAnthCollect_* 触发 buffer 5key 重试). 本轮改后窗口 (~9min) cc4101-primary 0 请求, 无法验证效果, 但链路无新错误、deadline 健康、配置无漂移 → NOP.

## 基线 (R662 实测)
- cc2 (cc4101-primary/glm5_2_nv) 60min: 16req SR=93.75% (15×200+1×502)
  - 唯一 502: 07:20:50 UTC NVAnthCollect_IncompleteRead 34384ms (改前事件, R661 修复目标)
- 30min 注入数据全是 hermes|dsv4p_nv (SR=90.9%, 配额型, 非本链路)
- tier 60min: pexec_success×12, integrate_success×4, RemoteDisconnected×8+SSL×4 (mark_transport 短惩罚), 429×1
- deadline 6h: stream_total_deadline=0 (健康)
- /health ok, 5keys, 配置无漂移, 无启动错误

## 下一步
- 等下一波 cc4101-primary 流量 + IncompleteRead 再现 → 看 NV-ANTH-COLLECT-BUFRETRY 日志判断 R661 是否生效
- 持续监控: deadline 链健康, dsv4p_nv 配额型 429 (持续, NVCF 侧问题)

## 参数快照 (无变化, 沿用 R661)
- nv_gw: NVU_DISABLE_MS_FALLBACK=1, buffer 5×90s=450s, NVU_BUFFER_CALLERS=cc4101-primary,openclaw2, UPSTREAM_TIMEOUT=90, TIER_COOLDOWN_S=180
- cc4101: PRIMARY=glm5_2_nv→nv_gw:40006, FALLBACK=dsv4p_nv→dsv4p_nv40066:40066, CC4101_STREAM_TOTAL_DEADLINE_S=470, PRIMARY_HEADER_TIMEOUT=400
