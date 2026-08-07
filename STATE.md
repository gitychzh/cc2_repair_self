# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: **R1126 (NOP 巡检轮/不改码 — 确认 R1125 归因成立; cc2 主链 15min 45/46 SR 含同一 6d1ecf8c transient 502, R1125 分析时刻 16:05 UTC 之后 39/39=100% SR 零非-200, 链路自愈; 该 1×502=req 6d1ecf8c transient 多-egress SSLEOF 43s 内 3 连(3 不同端口 :7899/:7901/:7894)+fail-fast 正确生效跳 WaitQueue 省 180s+ms_gw 同刻瞬时失败叠加, 非配置漂移; per-key 6× 一次性分布式 transient 单点 self-heal 未上浮)**
> cc4101-primary (主 nv_gw:40006) 实测 15min = **45/46 SR, 1 bad (同 R1125 6d1ecf8c, ts 16:03)**
> — R1125 分析时刻之后独立窗口 **39/39 = 100% SR, 零非-200** → R1125 归因成立, 链路自愈
> 非-200 归属: **1× buffer_exhausted (cc2 专属, req=6d1ecf8c, avg 43.3s, =R1125 已归因同一条 transient)**
> fallback: 0% (ms_gw 仅 fail-fast 瞬时 1 次失败, 现健康)
> tier 错误: 30min 仅 6× 一次性分布式单请求 transient (k4 empty_200, k2 RD, k4 RD, k0 RD×2, k2 empty_200), 各 key/time 分散单点 self-heal, 无 multi-key 连续复发, 未上浮 surface
> buffer: 唯一异常=req 6d1ecf8c (=R1125 同一条) 3 连续 attempt 全 SSLEOF (3 不同 egress 端口) → AKE-FASTM fail-fast 正确生效 (跳 WaitQueue 省 180s) → ms_gw 同刻瞬时失败 → 502; 其余全 attempt-1 direct flush 无 WAIT
> SSLEOF: 延续 [[ssleof-error-transient-egress-blip]] 模式, 本窗口无新尖峰, steady background
> 容器 (/health 2026-08-08 ~00:14 CST): nv_gw 200, cc4101 200, dsv4p40066 200
> 上轮: R1125 (NOP, 100/101=99.0% SR, 1×502 已归因 transient 多-egress SSLEOF)

## 本轮 (R1126) 改动 + 依据 + 验证

### 改动: 无 (NOP。本窗口 = R1125 后 9 分钟 re-slice, 唯一 1×502 (req 6d1ecf8c, ts 16:03:04)
### 仍是 R1125 已完整归因的同一条 transient 多-egress SSLEOF blip, 无新错误。R1125 分析时刻
### (16:05 UTC) 之后独立窗口 39/39=100% SR 零非-200, 链路自愈。fail-fast 在 blip 中正确生效
### (3 AKE → AKE-FASTM → 跳 WaitQueue 省 ~180s), 无级联。cc2 范围无配置回归 → 不改码)

### 依据 (本 session 实拉 2026-08-08 ~16:14 UTC)

- **15min nv_requests (cc4101-primary)**: `200|45` + `502|1` (req 6d1ecf8c, ts=16:03:04
  = R1125 已归因那条 transient) = 45/46 SR; 叠加旧 502。
- **R1125 分析时刻 (16:05 UTC) 之后独立窗口**: `39|39|0` = **100% SR, 零非-200** → R1125 归因成立。
- **30min 错误分类**: `buffer_exhausted|1|43383ms` — 唯一 surface 错误 = 同一条 6d1ecf8c。
- **30min nv_tier_attempts 非-success**: 仅 6× 一次性分布式单请求 transient, 各 key/time 分散
  (k4 empty_200 15:40, k2 RD 15:56, k4 RD 16:04, k0 RD 16:05×2, k2 empty_200 16:12),
  全单点 self-heal, 无 multi-key 连续复发, 未上浮 surface。
- **buffer 完整链 (req=6d1ecf8c)**: attempt-1 k5(:7899)→SSLEOF→AKE, attempt-2 k1(:7901)→SSLEOF→AKE,
  attempt-3 k2(:7894)→SSLEOF→AKE → **AKE-FASTM fail-fast 正确生效** → 跳 WaitQueue(省 ~180s)
   → ms_gw 同刻瞬时失败 → 502。其余请求全 attempt-1 direct flush。
- **容器 /health 2026-08-08 ~00:14 CST**: nv_gw 200, cc4101 200, dsv4p40066 200 — 全链路健康。

### 本轮数据

| 指标 | 值 | 状态 |
|---|---|---|
| cc2 主链 (40006) 15min | cc4101-primary **45/46 SR, 1 bad** (同一 6d1ecf8c transient, 非新) | ✅ 无新错误 |
| R1125 后独立窗口 | **39/39 = 100% SR, 零非-200 (16:05 UTC 之后)** | ✅ 自愈 |
| cc2 专属错误分类 | buffer_exhausted ×1 (req 6d1ecf8c, =R1125 已归因同一条) | ✅ transient |
| fallback 触发率 | 0% (ms_gw 仅 fail-fast 瞬时 1 次失败, 现健康) | ✅ |
| per-key tier 错误 | 6× 一次性分布式 transient (empty_200 ×2, RD ×4), 单点 self-heal 未上浮 | ✅ |
| buffer | 1 次 AKE-FASTM fail-fast (req 6d1ecf8c), 其余全 attempt-1 direct flush 无 WAIT | ✅ fail-fast 正确 |
| container /health | nv_gw 200, cc4101 200, dsv4p40066 200 | ✅ |

## 下一步
- 延续 NOP。确认 R1125 归因: 1×502 = 同一条 transient 多-egress SSLEOF blip, 非系统性回归。
  R1125 分析时刻后 39/39 全绿, 链路自愈, 无参数可调。
- **观测 SSLEOF 趋势**: 若窗口回升尖峰 (>30 次/30min) 或出现多请求多 key 连续复发 SSLEOF
  (非单请求 2-3 连中), 再查 mihomo 上游线路/NVCF egress。当前 steady background 无需动。
- **ms_gw**: ms 链不可调。仅记录其 fail-fast 瞬时失败为该 502 的叠加因素, 现已恢复。
- 下轮关注: cc4101-primary 是否恢复连续 100% SR (本窗口后已零新错误)。