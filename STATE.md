# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: **R1121 (NOP 巡检轮/不改码 — cc2 主链 113/113=100.0% SR 零错误 (cc4101-primary 经 nv_gw, primary model=dsv4f0731_nv); 全量 dsv4f0731_nv 146/146=100.0% SR 零错误零 fallback (本窗口全量非-200=空); fallback 0% (146 total fb=0 全走 primary); per-key 全 pexec_success (fid 281478d0: k0=21 k1=23 k2=21 k3=23 k4=25) 仅 fid 52e1ddb6 泄漏线的 k1 1× empty_200 + k4 1× empty_200 一次性 distributed transient 单请求 tier 自愈 (本轮无 RD) 无 multi-key 连续复发; buffer 无重试无级联 attempt-1 direct flush 无 WAIT; 容器全 200)**
> cc4101-primary (主 nv_gw:40006) 实测 30min = **113/113 = 100.0% SR, 0 bad** (cc2 专属零错误)
> — **零 502, 零错误(cc2), 零 fallback, 无任何新签名(cc2 范围)**
> 非-200 归属: **本窗口全量非-200 = 空** (无 502, 无 zombie_empty_completion)
> fallback: 0% (146 total, fb=0, 全走 primary)
> tier 错误: 30min (tier=dsv4f0731_nv) 全 pexec_success 为主 (fid 281478d0), 仅 fid 52e1ddb6 泄漏线的 k1 1× empty_200 + k4 1× empty_200 一次性 distributed transient 单请求 tier 自愈, 未上浮为 surface 错误, 无 multi-key 连续复发
> buffer: 全 attempt-1 direct flush (elapsed 3.7-7.9s success_tool_call), 无重试无级联无 WAIT
> 容器 (/health 2026-08-07 ~23:51 CST): nv_gw 200 (Up 20h), cc4101 200 (Up 20h)
> 上轮: R1120 (NOP, 102/102=100% SR, 全量 100%)

## 本轮 (R1121) 改动 + 依据 + 验证

### 改动: 无 (NOP。30min cc2 主链 113/113=100.0% SR 零错误零 fallback。
### 全量 dsv4f0731_nv 146/146=100% SR 零错误, 本窗口全量非-200=空。
### per-key 少量错误 (fid 52e1ddb6) 量小 (总 2x: k1 1× empty_200 + k4 1× empty_200, 本轮无 RD)
### 一次性 distributed transient 单请求 tier 自愈, 未上浮为 surface 错误, 无 multi-key 连续复发,
### 非配置漂移; buffer attempt-1 direct flush 无重试无级联无 WAIT。cc2 范围无新签名 → 不改码)

### 依据 (轮前链路分析注入 2026-08-07 23:51 CST)

- **30min nv_requests (cc4101-primary)**: status 仅 200 × **113** = 100.0% SR, 0 错误
  (cc2 专属零错误, 连续多轮 R1096-R1121 保持)。
- **dsv4f0731_nv 全量 SR**: 146/146 = **100.0%** (cc4101-primary 113 + hermes 33)。
  本窗口全量非-200 = 空, 零 bad。
- **30min 全量非-200 归属**: **无** (无 502 / zombie_empty_completion)。cc4101-primary 零错误。
- **fallback**: 0% (146 total, fallback_triggered=0, 全走 primary)。
- **nv_tier_attempts 30min**: tier=dsv4f0731_nv, 全 `pexec_success` 为主 (fid 281478d0:
  k0=21 k1=23 k2=21 k3=23 k4=25)；仅 fid **52e1ddb6** (历史记忆坏 fid — 越界容器 40666 hermes 线
  泄漏源) 的 k1 1× `empty_200` + k4 1× `empty_200` 一次性 distributed transient 单请求 tier 自愈,
  未上浮为 surface 错误, 无 multi-key 连续复发 (本轮无 RD, 比上轮更干净), 非配置漂移。
- **nv_requests 错误分类**: `(无错误)` — 零错误。
- **buffer 日志 (docker logs --since 30m)**: 全 attempt-1 direct flush (如 req deefa372 elapsed
  7.9s, req 472ce03f elapsed 3.7s, verdict=success_tool_call), 无重试无级联无 buffer_exhausted 无 WAIT。
- **容器 /health 2026-08-07 ~23:51 CST**: 40006 nv_gw http 200 (Up 20h, primary=dsv4f0731_nv, 5 key),
  4101 cc4101 http 200 (Up 20h)。

### 本轮数据

| 指标 | 值 | 状态 |
|---|---|---|
| cc2 主链 (40006) 30min | cc4101-primary **113/113 = 100.0% SR, 0 bad** | ✅ 全绿 |
| cc2 专属错误分类 | (无错误) 零错误 | ✅ |
| 全量非-200 归属 | **空** (无 502 / zombie_empty_completion, 全量 100%) | ✅ |
| fallback 触发率 | 0% (146 total, fb=0, 全走 primary) | ✅ |
| per-key tier 错误 | 全 pexec_success (fid 281478d0); 仅 fid 52e1ddb6 的 k1 1× empty_200 + k4 1× empty_200 一次性 transient 单请求 tier 自愈 (无 RD), 无 multi-key 连续复发 | ✅ |
| buffer | 全 attempt-1 direct flush (elapsed 3.7-7.9s success_tool_call), 无重试无级联无 WAIT | ✅ |
| container /health | nv_gw 200 (Up 20h), cc4101 200 (Up 20h) | ✅ |

## 下一步
- 延续 NOP。cc2 主链连续多轮 (R1096-R1121) 100% SR + zero fallback, 无参数可调。
- **k1/k4 错误** (fid 52e1ddb6): 量小 (本轮仅 2x empty_200, 无 RD), 单请求 self-heal, 未上浮为
  surface 错误, 与历史记忆模式一致 (泄漏源=越界容器 40666 hermes 线, 宿主分离)。仅当 RD/error
  在多请求多 key **连续复发** 才查链路/mihomo 线路。
- **全量非-200=空**: 连续多轮最干净窗口。zombie_empty_completion 可持续观察, 若在 caller=hermes
  线回升且宿主同机再查归属; 出现 caller=cc4101-primary 的错误才进 cc2 指标并处置。