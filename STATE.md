# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: **R1102 (NOP 巡检轮/不改码 — cc2 主链 103/103=100.0% SR 零错误 (cc4101-primary 经 nv_gw, primary model=dsv4f0731_nv); 全量 fallback 0%; 唯一 1× zombie_empty_completion 归属 hermes (peer) 非 cc2 主链; per-key 基本全 pexec_success 仅 k3 2× RD (与上轮持平未上升) 一次性 transient 单请求 buffer 自愈; buffer 无日志 = 全 attempt-1 直flush 零重试零级联零 buffer_exhausted; 容器全 200)** 
> cc4101-primary (主 nv_gw:40006) 实测 30min = **103/103 = 100.0% SR, 0 bad** (cc2 专属零错误)
> — **零 502, 零错误(cc2), 零 fallback, 无任何新签名(cc2 范围)**
> 非-200 归属: 唯一 1× zombie_empty_completion (502) — caller=**hermes** (peer) → 归属 peer 非 cc2 主链 (JOIN 铁证, caller=hermes|502|1)
> fallback: 0% (全量 125 全走 primary)
> tier 错误: 30min 5 key 基本全 pexec_success, 仅 k3 2× NVCFPexecRemoteDisconnected 一次性 transient (与上轮持平未上升)
> buffer: 无 buffer/wait/keymanager 日志 = 全 attempt-1 直 flush, 零重试零级联零 buffer_exhausted
> 容器 (/health 2026-08-07 22:30 CST): nv_gw 200, cc4101 200; docker ps nv_gw Up 24h, cc4101 Up 19h, nv_gw_stable Up 5d
> 上轮: R1101 (NOP, 102/102=100% SR 零错误)

## 本轮 (R1102) 改动 + 依据 + 验证

### 改动: 无 (NOP。30min cc2 主链 103/103=100.0% SR 零错误零 fallback, buffer 无日志 = 全 attempt-1
### 直 flush。唯一 1× zombie_empty_completion (502) 归属 hermes (peer caller), JOIN 复核 caller=hermes
### 专属。k3 RD 2× 与上轮持平未上升, 一次性 transient 单请求 buffer 自愈, 非 multi-key 连续复发。
### cc2 范围无新签名 → 不改码)

### 依据 (实测 DB 2026-08-07 22:30 CST + 实时复核 + /health)

- **30min nv_requests (cc4101-primary)**: status 仅 200 × **103** = 100.0% SR, 0 错误。
  实时复核 `caller='cc4101-primary'` = `200|103`。
- **30min 全量非-200 归属**: 唯一 1× zombie_empty_completion (502) 全部 caller=**hermes** (peer)。
  实时复核 `caller|status|count` = `hermes|502|1` (cc4101-primary 0) —— JOIN 归属铁证 (记忆
  bad-fid 52e1ddb6 判归属法)。
- **fallback**: 0% (全量 125 全走 primary, fallback_triggered=0)。
- **nv_tier_attempts 30min**: 5 key 基本全 `pexec_success`; 仅 k3 2× `NVCFPexecRemoteDisconnected`
  一次性 distributed transient (与上轮 2× **持平未上升**; 量小, 单请求 buffer 自愈)。零
  buffer_exhausted, 零持续 tier 错误。
- **buffer 日志**: 无 buffer/wait/keymanager 日志 = 全 attempt-1 直 flush 秒回, 零重试零级联零
  buffer_exhausted。
- **容器 /health 2026-08-07 22:30 CST**: 40006 nv_gw http 200, 4101 cc4101 http 200 (实时复核
  nv_gw:200, cc4101:200)。docker ps: nv_gw Up 24h, cc4101 Up 19h, nv_gw_stable Up 5d。

### 本轮数据

| 指标 | 值 | 状态 |
|---|---|---|
| cc2 主链 (40006) 30min | cc4101-primary **103/103 = 100.0% SR, 0 bad** | ✅ 全绿 |
| cc2 专属错误分类 | (cc2 专属 0 rows) 零错误 | ✅ |
| 非-200 归属 | 1× zombie_empty_completion (502), caller=hermes (peer) | ✅ peer 归属 |
| fallback 触发率 | 0% (全量 125 全走 primary) | ✅ |
| per-key tier 错误 | 基本全 pexec_success; 仅 k3 2× RD (与上轮持平) 一次性 transient | ✅ 零持续 tier 错误 |
| buffer | 无日志 = 全 attempt-1 直 flush, 零重试零级联零 buffer_exhausted | ✅ |
| container /health | nv_gw 200, cc4101 200 (Up 24h/19h) | ✅ |

## 下一步
- 延续 NOP。cc2 主链连续多轮 100% SR + zero fallback (R1099-R1102 同), 无参数可调。
- **k3 RD 2×**: 与上轮持平未上升, 一次性 distributed transient, 单请求 buffer 自愈, 不构成
  multi-key 连续复发。仅当 k3 RD 在多 key **连续复发** (多个独立请求多 key 持续失败) 才查
  k3 mihomo 7896 线路。
- **hermes 1× zombie_empty_completion** (peer) 持续关注, 归属 peer 非 cc2 不改动。
- 若 zombie_empty_completion 中出现 caller=cc4101-primary (c.parent) 才进 cc2 指标。

## 参数快照 (未动, 同 R1101)
- 本轮零改动。nv_gw env 复核: NV_GLM52_MODE_CHAIN=pexec_us_rr, KEY_MODE_BINDING= 空,
  KEY_FID_BIND=0:0;1:0;2:0;3:0;4:0, NVU_DISABLE_MS_FALLBACK=0, UPSTREAM_TIMEOUT=90,
  NVU_BUFFER_CALLERS=cc4101-primary,openclaw2。
- cc4101: PRIMARY_UPSTREAM_MODEL=dsv4f0731_nv, FALLBACK_UPSTREAM_MODEL=glm5_2_ms,
  PRIMARY_UPSTREAM_URL=http://nv_gw:40006/v1/messages, CC4101_STREAM_TOTAL_DEADLINE_S=470,
  PRIMARY_HEADER_TIMEOUT=400。