# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: **R1129 (NOP 巡检轮/不改码 — 5 轮连续确认同一 6d1ecf8c transient 归宿; cc2 主链 30min
> 唯一 1×502 = 同一 req 6d1ecf8c (ts 16:03:04 UTC, R1125/26/27/28 已归因 multi-egress SSLEOF blip, 非新,
> 仍在窗口仅因 UTC 边界采样点 16:03), 最近独立 10min 40/40=100% SR 零非-200 主链连续全绿自愈;
> tier 错误 8× RD + 1× empty_200 全单请求分布式一次性 self-heal 未上浮; fallback 0%;
> buffer 新窗口全 attempt-1 direct flush 无 WAIT/无新 exhaust)**
> cc4101-primary (主 nv_gw:40006) 实测 30min = **唯一 1 bad (同一 6d1ecf8c, ts 16:03:04, 非新)**
> — 最近独立 10min **40/40 = 100% SR, 零非-200** → 主链连续全绿自愈
> 非-200 归属: **1× buffer_exhausted (cc2 专属, req=6d1ecf8c, avg 43.3s, =R1125/26/27/28 已归因同一条)**
> fallback: 0% (30min 0/110 fallback_triggered, 未走 ms_gw)
> tier 错误: 30min 8× NVCFPexecRemoteDisconnected + 1× empty_200, 各 key/time 分散单点
> (k0×3, k1×1, k2×1, k3×1, k4×2), 全单请求一次性 self-heal 未上浮
> buffer: 新窗口全 attempt-1 direct flush success 无 WAIT/无新 exhaust (8c735fdc/d7db93b3/adb5a5d8 等)
> SSLEOF/RD: 延续 [[ssleof-error-transient-egress-blip]] 模式, 全分布式单点, steady background
> 容器 (/health 注入 2026-08-08 ~00:28 CST): nv_gw 200, cc4101 200, dsv4p40066 200 (Up 26h/21h/5d)
> 上轮: R1128 (NOP, 确认 R1127 归因成立; 主链 43/43 100% SR)

## 本轮 (R1129) 改动 + 依据 + 验证

### 改动: 无 (NOP。30min 唯一 1×502 (req 6d1ecf8c, ts 16:03:04 UTC) 是 R1125~R1128 已完整归因的
### 同一条 transient 多-egress SSLEOF blip — 现已第 5 轮连续确认同一 req id, 仍在窗口仅因 UTC
### 边界采样点在 16:03 (非新发生)。最近独立 10min 40/40 =100% SR 零非-200, 主链连续全绿自愈。
### cc2 范围无配置回归 → 不改码)

### 依据 (本 session 实拉 2026-08-08 ~00:45 CST / 16:45 UTC)

- **30min nv_requests (cc4101-primary, 含 request_id)**: `200|107` + `502|1`; 唯一 502 =
  req **6d1ecf8c, ts 16:03:04 UTC, duration_ms=43383, error=buffer_exhausted** — 与 R1125/1126/1127/1128
  完全同一 req id (第 5 轮确认), 窗口内仅此 1 条非-200。
- **最近独立 10min (cc4101-primary)**: `200|40` = **100% SR, 零非-200** → 主链连续全绿自愈。
- **30min 错误分类 (cc4101-primary)**: `buffer_exhausted|1` (avg 43.3s) = 同一条 6d1ecf8c。
- **30min nv_tier_attempts 非-success**: 8× NVCFPexecRemoteDisconnected + 1× empty_200,
  各 key/time 分散单点 (k0×3, k1×1, k2×1, k3×1, k4×2), 全单请求一次性 self-heal
  (后续 attempt 成功), 无 multi-key 连续复发, 未上浮 surface。
- **buffer 日志 (最近 30min)**: 新窗口全 attempt-1 direct flush success (8c735fdc / d7db93b3 /
  adb5a5d8, verdict=success_tool_call, elapsed 7~12s), 无 WAIT/无新 exhaust。
- **fallback (30min cc_requests)**: `fallback_triggered` = 0 / 110 total — fallback 0%, 未走 ms_gw。
- **容器 /health 注入 2026-08-08 ~00:28 CST**: nv_gw 200 (5 key, pexec 全模型 200), cc4101 200
  (primary dsv4f0731_nv), dsv4p40066 200 — 全链路健康。

### 本轮数据

| 指标 | 值 | 状态 |
|---|---|---|
| cc2 主链 (40006) 30min | cc4101-primary 唯一 1×502 = 同一 6d1ecf8c transient, 无新错误 | ✅ 5 轮确认同一条 |
| 最近独立 10min | **40/40 = 100% SR, 零非-200** | ✅ 主链连续全绿自愈 |
| cc2 专属错误分类 | buffer_exhausted ×1 (req 6d1ecf8c, ts 16:03:04, =R1125~28 同一条) | ✅ transient 老化中 |
| fallback 触发率 | 0% (30min 0/110 fallback, 未走 ms_gw) | ✅ |
| per-key tier 错误 | 8× RD + 1× empty_200, 全单请求分布式一次性 self-heal 未上浮 | ✅ |
| buffer | 新窗口全 attempt-1 direct flush success, 无 WAIT/无新 exhaust | ✅ |
| container /health | nv_gw 200, cc4101 200, dsv4p40066 200 (Up 26h/21h/5d) | ✅ |

## 下一步
- 延续 NOP。6d1ecf8c 已第 5 轮确认同一 transient (multi-egress SSLEOF, R1125 已完整归因),
  纵使滚动窗口采样仍偶现 (UTC 边界 16:03), 主链最近独立 10min 40/40 全绿自愈, 无参数可调。
- **关闭判定 (正式)**: 该 blip ts=16:03 UTC 距今已 >45min 未再发生任何同 req / 同 pattern 复发。
  下轮若窗口内零表面错误 (6d1ecf8c 彻底老化出窗口), 正式标记闭合。
- **观测 SSLEOF/RD 趋势**: 若回升尖峰 (>30 次/30min) 或出现同 key 多请求连续复发 RD
  (非单请求瞬时), 再查该 key 对应 mihomo 端口线路。当前 8× RD 全分布式单点, steady background 无需动。
- **ms_gw**: ms 链不可调, fallback 0% 未触发, 无需动作。