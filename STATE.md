# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: **R1114 (NOP 巡检轮/不改码 — cc2 主链 107/107=100.0% SR 零错误 (cc4101-primary 经 nv_gw, primary model=dsv4f0731_nv); 全量 dsv4f0731_nv 157/158=99.4% SR; 唯一 1× 502 zombie_empty_completion 实时 DB 复核归属 caller=hermes (bad fid 52e1ddb6, k1, dur 2s) 非 cc2; fallback 0% (158 total fb=0 全走 primary); per-key 全 pexec_success (fid 281478d0) 仅 fid 52e1ddb6 的 k1 2× + k4 1× NVCFPexecRemoteDisconnected 一次性 distributed transient 单请求 buffer 自愈 无 multi-key 连续复发; buffer 无重试无级联默认全 attempt-1 直flush 7-10s; 容器全 200)**
> cc4101-primary (主 nv_gw:40006) 实测 30min = **107/107 = 100.0% SR, 0 bad** (cc2 专属零错误)
> — **零 502, 零错误(cc2), 零 fallback, 无任何新签名(cc2 范围)**
> 非-200 归属: 唯一 1 行 **caller=hermes|502|zombie_empty_completion|fid 52e1ddb6|k1|2001ms** — **归属 hermes 非 cc2** (cc4101-primary 无任何非-200)
> fallback: 0% (158 total, fb=0, 全走 primary)
> tier 错误: 30min (tier=dsv4f0731_nv) 全 pexec_success, 仅 fid 52e1ddb6 的 k1 2× + k4 1× NVCFPexecRemoteDisconnected 一次性 distributed transient 单请求 buffer 自愈, 无 multi-key 连续复发
> buffer: 无 buffer_exhausted, 全 attempt=1 direct flush 7-10s, 无重试无级联
> 容器 (/health 2026-08-07 23:22 CST): nv_gw 200 (Up 20h), cc4101 200 (Up 19h)
> 上轮: R1113 (NOP, 111/111=100% SR 零错误)

## 本轮 (R1114) 改动 + 依据 + 验证

### 改动: 无 (NOP。30min cc2 主链 107/107=100.0% SR 零错误零 fallback。
### 唯一 502 zombie_empty_completion 实时 DB 复核归属 caller=hermes (bad fid 52e1ddb6, k1, dur 2s)
### 非 cc2; per-key RD (fid 52e1ddb6) 量小 (总 3x) 一次性 distributed transient 单请求 buffer 自愈
### 未上升, 无 multi-key 连续复发, 非配置漂移。cc2 范围无新签名 → 不改码)

### 依据 (注入轮前分析 2026-08-07 23:20 CST + 实时 DB/health 复核)

- **30min nv_requests (cc4101-primary)**: status 仅 200 × **107** = 100.0% SR, avg_dur 11.4s, 0 错误
  (cc2 专属零错误, 连续多轮 R1096-R1114 保持)。
- **dsv4f0731_nv 全量 SR**: 157/158 = **99.4%**。唯一流失为 502 zombie_empty_completion。
- **30min 全量非-200 归属 (实时 DB 交叉复核)**: 唯一 1 行 `caller=hermes, fid=52e1ddb6, nv_key_idx=1,
  status=502, error_type=zombie_empty_completion, duration_ms=2001 → 归属 hermes 非 cc2` (历史记忆模式:
  zombie_empty_completion/502 归属 hermes/dsv4f0731_nv 线, 越界容器 40666 泄漏线, 宿主分离)。
  **cc4101-primary 无任何非-200。**
- **fallback**: 0% (158 total, fallback_triggered=0, 全走 primary)。
- **nv_tier_attempts 30min**: tier=dsv4f0731_nv, 全 `pexec_success` 为主 (fid 281478d0: k0=22 k1=18 k2=24
  k3=21 k4=22)；仅 fid **52e1ddb6** (历史记忆坏 fid — 越界容器 40666 hermes 线泄漏源) 的 k1 2× + k4 1×
  `NVCFPexecRemoteDisconnected` 一次性 distributed transient 单请求 buffer 自愈。量 (总 3x)
  单请求一次性, 无 multi-key 连续复发。
- **buffer 日志 (docker logs --since 30m)**: 全 `attempt=1` direct flush
  (success_tool_call), elapsed 7-10s, 无重试无级联无 buffer_exhausted、无 WAIT。
- **容器 /health 2026-08-07 23:22 CST**: 40006 nv_gw http 200 (Up 20h), 4101 cc4101 http 200 (Up 19h)。
  nv_gw_stable Up 5d (无关, 历史遗留容器)。

### 本轮数据

| 指标 | 值 | 状态 |
|---|---|---|
| cc2 主链 (40006) 30min | cc4101-primary **107/107 = 100.0% SR, 0 bad** (avg 11.4s) | ✅ 全绿 |
| cc2 专属错误分类 | (无错误) 零错误 | ✅ |
| 非-200 归属 | 唯一 1 行 zombie_empty_completion 归属 **hermes** (fid 52e1ddb6, k1) 非 cc2 | ✅ |
| fallback 触发率 | 0% (158 total, fb=0, 全走 primary) | ✅ |
| per-key tier 错误 | 全 pexec_success (fid 281478d0); 仅 fid 52e1ddb6 的 k1 2× + k4 1× RD 一次性 transient 单请求自愈, 无 multi-key 连续复发 | ✅ |
| buffer | 全 attempt=1 direct flush 7-10s, 无重试无级联无 buffer_exhausted | ✅ |
| container /health | nv_gw 200 (Up 20h), cc4101 200 (Up 19h) | ✅ |

## 下一步
- 延续 NOP。cc2 主链连续多轮 (R1096-R1114) 100% SR + zero fallback, 无参数可调。
- **k1/k4 RD** (fid 52e1ddb6): 量小 (总 3x, 均单请求), 一次性 distributed transient,
  单请求 buffer 自愈, 与历史记忆模式一致 (泄漏源=越界容器 40666 hermes 线, 宿主分离)。
  无 multi-key 连续复发, 不构成配置漂移。仅当 RD/error 在多 key **连续复发**
  (多个独立请求多 key 持续失败) 才查链路/mihomo 线路。
- **唯一 502 (bad fid 52e1ddb6 zombie_empty_completion, caller=hermes, dur 2s)**: 非 cc2 范围,
  历史记忆归属模式, 单请求 transient, 不处置。
- 若 zombie_empty_completion 或其他错误中出现 caller=cc4101-primary (c.parent) 才进 cc2 指标并处置。

## 参数快照 (未动, 同 R1113)
- 本轮零改动。nv_gw env 复核: NVU_DISABLE_MS_FALLBACK=0, KEY_COOLDOWN_S=30,
  NV_INTEGRATE_KEY_COOLDOWN_S=90, UPSTREAM_TIMEOUT=90, BUFFER 5×90s=450s, Tier budget 180s,
  NVU_FORCE_STREAM_UPGRADE_TIMEOUT=150, NVU_FORCE_STREAM_UPGRADE=0, MIN_OUTBOUND_INTERVAL_S=10,
  NVU_CALLER_KEY_MAP=hermes:2;openclaw:3;opencode:4. nvcf_pexec_models 含 dsv4f0731_nv。
- cc4101: PRIMARY_UPSTREAM_MODEL=dsv4f0731_nv, PRIMARY_UPSTREAM_URL=http://nv_gw:40006/v1/messages,
  PRIMARY_HEADER_TIMEOUT=400, CC4101_STREAM_TOTAL_DEADLINE_S=470, UPSTREAM_TIMEOUT=130,
  FALLBACK_UPSTREAM_URL=http://ms_gw:40007/v1/chat/completions (历史残留, 未触发).
- deadline 链: 90s×5=450s buffer < 470s cc4101 < 600s SDK < 900s idle.