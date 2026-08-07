# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: **R1122 (NOP 巡检轮/不改码 — cc2 主链 111/111=100.0% SR 零错误 (cc4101-primary 经 nv_gw, primary model=dsv4f0731_nv); 全量 dsv4f0731_nv 141/141=100.0% SR 零错误零 fallback (本窗口全量非-200=空, bad_status=空); fallback 0% (141 total fb=0 全走 primary); per-key tier 全 pexec_success 为主 (110×) 仅 2× empty_200 一次性 transient 单请求 tier 自愈 (fid 52e1ddb6 泄漏线模式) 未上浮; buffer 无重试无级联 attempt-1 direct flush 无 WAIT; 容器全 200)**
> cc4101-primary (主 nv_gw:40006) 实测 30min = **111/111 = 100.0% SR, 0 bad** (cc2 专属零错误)
> — **零 502, 零错误(cc2), 零 fallback, 无任何新签名(cc2 范围)**
> 非-200 归属: **本窗口全量非-200 = 空** (bad_status=空, 无 502, 无 zombie_empty_completion)
> fallback: 0% (141 total, fb=0, 全走 primary)
> tier 错误: 30min (tier=dsv4f0731_nv) 全 pexec_success 为主 (110×), 仅 2× empty_200 一次性 distributed transient 单请求 tier 自愈, 未上浮为 surface 错误, 无 multi-key 连续复发
> buffer: 全 attempt-1 direct flush, 无重试无级联无 WAIT
> 容器 (/health 2026-08-08 ~00:0X CST): nv_gw 200 (Up 20h), cc4101 200 (Up 20h)
> 上轮: R1121 (NOP, 113/113=100% SR, 全量 100%)

## 本轮 (R1122) 改动 + 依据 + 验证

### 改动: 无 (NOP。30min cc2 主链 111/111=100.0% SR 零错误零 fallback。
### 全量 dsv4f0731_nv 141/141=100% SR 零错误, 本窗口全量非-200=空 (bad_status=空)。
### per-key 少量错误 (2× empty_200) 量小, 一次性 distributed transient 单请求 tier 自愈,
### 未上浮为 surface 错误, 无 multi-key 连续复发, 非配置漂移 (fid 52e1ddb6 泄漏线历史模式);
### buffer attempt-1 direct flush 无重试无级联无 WAIT。cc2 范围无新签名 → 不改码)

### 依据 (轮前链路分析注入 2026-08-07 23:54 CST + 本 session 实拉复核)

- **30min nv_requests (cc4101-primary)**: status 仅 200 × **111** = 100.0% SR, 0 错误
  (cc2 专属零错误, 连续多轮 R1096-R1122 保持)。
- **全量 SR**: 141/141 = **100.0%** (nv_requests 全量 status=200, bad_status=空, total=141, ok=141)。
- **30min 全量非-200 归属**: **无** (bad_status=空, 无 502 / zombie_empty_completion)。cc4101-primary 零错误。
- **fallback**: 0% (全量走 primary, fallback_triggered 未触发)。
- **nv_tier_attempts 30min**: 全 `pexec_success` 为主 (110×), 仅 2× `empty_200` 一次性 distributed
  transient 单请求 tier 自愈 (对 fid 52e1ddb6 历史泄漏线模式), 未上浮为 surface 错误, 无 multi-key 连续复发
  (本轮无 RD), 非配置漂移。
- **nv_requests 错误分类**: `(无错误)` — 零错误 (0 rows)。
- **buffer 日志 (docker logs --since 30m)**: 无 buffer/wait/keymanager 摘要行 → 全 attempt-1 direct flush
  无重试无级联无 WAIT。
- **容器 /health 2026-08-08 ~00:0X CST**: 40006 nv_gw http 200 (Up 20h, primary=dsv4f0731_nv, 5 key),
  4101 cc4101 http 200 (Up 20h)。

### 本轮数据

| 指标 | 值 | 状态 |
|---|---|---|
| cc2 主链 (40006) 30min | cc4101-primary **111/111 = 100.0% SR, 0 bad** | ✅ 全绿 |
| cc2 专属错误分类 | (无错误) 零错误 | ✅ |
| 全量非-200 归属 | **空** (bad_status=空, 无 502 / zombie_empty_completion, 全量 100%) | ✅ |
| fallback 触发率 | 0% (全量走 primary, fb=0) | ✅ |
| per-key tier 错误 | 110× pexec_success 为主; 仅 2× empty_200 一次性 transient 单请求 tier 自愈 (无 RD), 无 multi-key 连续复发 | ✅ |
| buffer | 无 buffer/wait/keymanager 日志 → 全 attempt-1 direct flush 无重试无级联无 WAIT | ✅ |
| container /health | nv_gw 200 (Up 20h), cc4101 200 (Up 20h) | ✅ |

## 下一步
- 延续 NOP。cc2 主链连续多轮 (R1096-R1122) 100% SR + zero fallback, 无参数可调。
- **per-key 2× empty_200** (fid 52e1ddb6 泄漏线): 量小, 单请求 self-heal, 未上浮为 surface 错误,
  与历史记忆模式一致 (泄漏源=越界容器 40666 hermes 线, 宿主分离)。仅当 RD/error 在多请求多 key
  **连续复发** 才查链路/mihomo 线路。
- **全量非-200=空**: 连续多轮最干净窗口。zombie_empty_completion 可持续观察, 若在 caller=hermes
  线回升且宿主同机再查归属; 出现 caller=cc4101-primary 的错误才进 cc2 指标并处置。