# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: **R1130 (NOP 巡检轮/不改码 — 6d1ecf8c blip 正式闭合; 30min 全 caller 零表面错误
> (0 行非-200), 达成 R1129 关闭判定; cc2 主链最近独立 10min 37/37=100% SR 零非-200 连续全绿自愈;
> tier 错误 8× RD + 2× empty_200 全单请求分布式一次性 self-heal 未上浮; fallback 0% (0/113);
> buffer 新窗口全 attempt-1 direct flush 无 WAIT/无新 exhaust)**
> cc4101-primary (主 nv_gw:40006) 实测 30min = **0 行非-200** — 6d1ecf8c (ts 16:03:47 UTC) 正式出窗
> — 最近独立 10min **37/37 = 100% SR, 零非-200** → 主链连续全绿自愈
> 非-200 归属: **无 (0 行, 全 caller)** — R1125~R1129 唯一 transient 6d1ecf8c 已闭合
> fallback: 0% (30min 0/113 fallback_triggered, 未走 ms_gw)
> tier 错误: 30min 8× NVCFPexecRemoteDisconnected + 2× empty_200, 各 key/time 分散单点
> (k0×3, k1×1+empty, k2×1+empty, k3×1, k4×2), 全单请求一次性 self-heal 未上浮
> buffer: 新窗口全 attempt-1 direct flush success (830d702c=16s / e99e0e67=4s / 18cbdaa6=18s) 无 WAIT/无新 exhaust
> SSLEOF/RD: 延续 [[ssleof-error-transient-egress-blip]] 模式, 全分布式单点, steady background
> 容器 (/health 实测 2026-08-08 ~16:33 UTC): nv_gw 200, cc4101 200, dsv4p40066 200 (Up 21h/21h/3d)
> 上轮: R1129 (NOP, 确认 6d1ecf8c 第 5 轮同一条, 设关闭判定)

## 本轮 (R1130) 改动 + 依据 + 验证

### 改动: 无 (NOP。30min 全 caller 零非-200 — 唯一 transient req 6d1ecf8c (ts 16:03:47 UTC,
### R1125~R1129 已完整归因 multi-egress SSLEOF blip) 正式老化出 30min 窗口, 达成 R1129 关闭判定。
### 最近独立 10min 37/37 =100% SR 零非-200, 主链连续全绿自愈。cc2 范围无配置回归 → 不改码)

### 依据 (本 session 实拉 2026-08-08 ~16:33 UTC)

- **30min nv_requests 非-200 (所有 caller)**: **0 行** — 表面错误为零, 6d1ecf8c 正式出窗,
  达成 R1129「下轮若窗口内零表面错误, 正式标记闭合」关闭条件。
- **最近独立 10min (cc4101-primary)**: `200|37` = **100% SR, 零非-200** → 主链连续全绿自愈。
- **30min 错误分类 (cc4101-primary)**: 唯一 buffer_exhausted = req 6d1ecf8c (ts 16:03:47 UTC,
  duration_ms=43383) = R1125~R1129 已完整归因同一条, 现已出窗 (0 行)。
- **30min nv_tier_attempts 非-success**: 8× NVCFPexecRemoteDisconnected (k0×3, k1×1, k3×1, k4×2)
  + empty_200×2 (k1×1, k2×1), 各 key/time 分散单点自 self-heal, 无 multi-key 连续复发, 未上浮 surface。
- **buffer 日志 (最近 30min)**: 全 attempt-1 direct flush success (830d702c=16s / e99e0e67=4s /
  18cbdaa6=18s, verdict=success_tool_call), 无 WAIT、无新 exhaust。
- **fallback (30min cc_requests)**: `fallback_triggered` = 0 / 113 total — fallback 0%, 未走 ms_gw。
- **容器 /health 实测 2026-08-08 ~16:33 UTC**: nv_gw 200 (5 key, pexec 全模型 200), cc4101 200
  (primary dsv4f0731_nv), dsv4p40066 200 — 全链路健康 (Up 21h/21h/3d)。

### 本轮数据

| 指标 | 值 | 状态 |
|---|---|---|
| cc2 主链 (40006) 30min | **0 行非-200 (全 caller)** — 6d1ecf8c 正式出窗 | ✅ **关闭判定达成** |
| 最近独立 10min | **37/37 = 100% SR, 零非-200** | ✅ 主链连续全绿自愈 |
| cc2 专属错误分类 | 空 (0 行) — 6d1ecf8c blip 正式闭合 | ✅ transient 已老化出窗 |
| fallback 触发率 | 0% (30min 0/113 fallback, 未走 ms_gw) | ✅ |
| per-key tier 错误 | 8× RD + 2× empty_200, 全单请求分布式一次性 self-heal 未上浮 | ✅ |
| buffer | 全 attempt-1 direct flush success (4~18s), 无 WAIT/无新 exhaust | ✅ |
| container /health | nv_gw 200, cc4101 200, dsv4p40066 200 (Up 21h/21h/3d) | ✅ |

## 下一步
- 延续 NOP。6d1ecf8c blip (R1125 归因 multi-egress SSLEOF) 已 6 轮确认同一 req, 本轮正式闭合。
  主链最近独立 10min 37/37 全绿, 滚动 30min 零表面错误, 无参数可调。
- **观测 RD/SSLEOF 趋势**: 本轮 tier RD 8× 较上轮持平 (8×), 全分布式单点 steady background。
  若回升尖峰 (>30 次/30min) 或同 key 多请求连续复发 RD, 再查该 key 对应 mihomo 端口线路。
- **ms_gw**: ms 链不可调, fallback 0% 未触发, 无需动作。
