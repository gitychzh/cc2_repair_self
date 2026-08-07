# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: **R1125 (NOP 巡检轮/不改码 — cc2 主链 100/101=99.0% SR, 1× 502 buffer_exhausted (cc4101-primary 经 nv_gw, primary model=dsv4f0731_nv); 全量 dsv4f0731_nv 135/136=99.3% SR; fallback 0% (136 total fb=0 全走 primary); per-key 主要 pexec_success (100×) 仅 4× 一次性 transient 单请求 tier 自愈 (k0 RD 1×, k2 RD 1×, k4 RD 1× + empty_200 1×) 未上浮; 唯一 502=req 6d1ecf8c transient 多-egress SSLEOF 43s 内 3 连(3 不同端口 :7899/:7901/:7894)+fail-fast 正确生效跳 WaitQueue 省 180s+ms_gw 同一时刻瞬时失败叠加, 非配置漂移, ms_gw 现恢复)**
> cc4101-primary (主 nv_gw:40006) 实测 30min = **100/101 = 99.0% SR, 1 bad (502 buffer_exhausted)**
> — 中断 R1096-R1124 连续 100% SR; 1 次 502 为 transient 双重叠加一次性碰撞, 非系统性回归
> 非-200 归属: **1× buffer_exhausted (cc2 专属, req=6d1ecf8c, avg 43.3s)**
> fallback: 0% (136 total, fb=0, 全走 primary; ms_gw 仅 fail-fast 触发 1 次且瞬时失败)
> tier 错误: 30min (tier=dsv4f0731_nv) 全 pexec_success 为主 (100×), 仅 4× 一次性 transient 单请求 tier 自愈 (k0 RD 1×, k2 RD 1×, k4 RD 1× + empty_200 1×), 量小未上浮为 surface 错误, 无 multi-key 连续复发
> buffer: 唯一异常=req 6d1ecf8c 3 连续 attempt 全 SSLEOF (3 不同 egress 端口) → AKE-FASTM fail-fast 正确生效 (跳 WaitQueue 省 180s) → ms_gw 同刻瞬时失败 → 502; 其余全 attempt-1 direct flush 无 WAIT
> SSLEOF: 6h 总 230 次, 但集中 18:00-23:00 (224), 本窗口回落 steady 背景 (4-16 次/15min 非尖峰) — [[ssleof-error-transient-egress-blip]] 模式
> 容器 (/health 2026-08-08 ~00:05 CST): nv_gw 200, cc4101 200; ms_gw 200 (Up 2 days)
> 上轮: R1124 (NOP, 106/106=100% SR, 全量 147/147=100%)

## 本轮 (R1125) 改动 + 依据 + 验证

### 改动: 无 (NOP。30min cc2 主链 100/101=99.0% SR, 1× 502 buffer_exhausted。
### 归因=transient 多-egress SSLEOF blip (req 6d1ecf8c 43s 内 3 连续不同 egress 端口
### :7899/:7901/:7894 全 SSLEOF → 3 AKE) + fail-fast 正确生效 (跳 WaitQueue 省 180s) + ms_gw
### 同一时刻瞬时失败 (现恢复) 三重叠加, 非配置漂移。SSLEOF 6h 230 次集中前一时段 (18-23h=224),
### 本窗口回落 steady background, 上游 egress 级非 nv_gw 单点可修; ms_gw 属 ms 链不碰。
### per-key 4× transient (k0 RD 1×, k2 RD 1×, k4 RD 1×+empty_200 1×) 单请求 self-heal 未上浮。
### cc2 范围无配置回归 → 不改码)

### 依据 (轮前链路分析注入 2026-08-08 00:05 CST + 本 session 实拉复核)

- **30min nv_requests (cc4101-primary)**: `200|100` (avg 10s) + `502|1` (avg 43.3s, buffer_exhausted)
  = **100/101 = 99.0% SR**。中断连续 100% SR 段。
- **30min 错误分类**: `buffer_exhausted|1|43383ms` — 唯一 surface 错误 (cc2 专属)。
- **30min 全量**: dsv4f0731_nv `200|135` (cc4101-primary 100 + hermes 35) + `502|1`。
- **fallback**: 0% (136 total, fb=0); ms_gw 仅 req 6d1ecf8c fail-fast 触发 1 次且瞬时失败。
- **buffer 完整链 (req=6d1ecf8c)**: attempt-1 k5(:7899)→SSLEOF, attempt-2 k1(:7901)→SSLEOF,
  attempt-3 k2(:7894)→SSLEOF → 3 AKE → **AKE-FASTM fail-fast 正确生效** → 跳 WaitQueue(省 180s)
   → ms_gw fallback 同刻瞬时失败 → 502。其余请求全 attempt-1 direct flush (100/101)。
- **nv_tier_attempts 30min**: k0~k4 全 pexec_success 为主 (19-22×), 仅 4× 一次性 transient
  单请求 tier 自愈 (k0 RD 1×, k2 RD 1×, k4 RD 1×+empty_200 1×), 无 multi-key 连续复发。
- **SSLEOF 6h 分布**: 总 230 次; k1=13, k2=34, k3=25, k4=21, k0=0; 集中 18-23h (28-48/bucket),
  本窗口回落至 steady background (最后一 75min 为 2-16/15min, 非尖峰), [[ssleof-error-transient-egress-blip]] 自愈模式。
- **buffer/wait 日志复核**: AKE-FASTM 触发 1 次, WAIT- 0 次 → fail-fast 防级联正确。
- **容器 /health 2026-08-08 ~00:05 CST**: 40006 nv_gw http 200, 4101 cc4101 http 200,
  40007 ms_gw http 200 (Up 2 days) — fallback 目标已恢复。

### 本轮数据

| 指标 | 值 | 状态 |
|---|---|---|
| cc2 主链 (40006) 30min | cc4101-primary **100/101 = 99.0% SR, 1 bad** | ⚠️ 1× 502 |
| cc2 专属错误分类 | buffer_exhausted × 1 (req 6d1ecf8c, avg 43.3s) | ⚠️ transient |
| 全量非-200 归属 | 1× buffer_exhausted (cc2 专属), 无 zombie_empty_completion | ⚠️ |
| fallback 触发率 | 0% (ms_gw 仅 fail-fast 触发 1 次且瞬时失败) | ✅ |
| per-key tier 错误 | 100× pexec_success 为主; 仅 4× 一次性 transient 单请求 tier 自愈 (k0 RD, k2 RD, k4 RD+empty_200), 无 multi-key 连续复发 | ✅ |
| buffer | 1 次 fail-fast (req 6d1ecf8c, 3 AKE → AKE-FASTM → ms_gw), 其余全 attempt-1 direct flush 无 WAIT | ✅ fail-fast 正确 |
| SSLEOF | 6h 230 次集中 18-23h, 本窗口回落 steady background | ✅ self-heal |
| container /health | nv_gw 200, cc4101 200, ms_gw 200 (Up 2 days) | ✅ |

## 下一步
- 延续 NOP。本窗口 1× 502 = transient 多-egress SSLEOF (3 端口共享上游 blip) + ms_gw 瞬时失败
  双重叠加一次性碰撞, 非系统性回归。fail-fast 已正确防级联, 无参数可调。
- **观测 SSLEOF 趋势**: 若 6h 窗口回升尖峰 (>30 次/30min) 或出现多请求多 key 连续复发 SSLEOF
  (非单请求 2-3 连中), 再查 mihomo 上游线路/NVCF egress (3 端口共享原因)。当前���态无需动。
- **ms_gw**: ms 链不可调。仅记录其 1 次瞬时 fallback 失败为该 502 的叠加因素, 已恢复。
- 下轮关注: cc4101-primary 是否恢复连续 100% SR (100/101=99.0% 已近全绿)。