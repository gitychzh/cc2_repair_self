# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: **R1108 (NOP 巡检轮/不改码 — cc2 主链 117/117=100.0% SR 零错误 (cc4101-primary 经 nv_gw, primary model=dsv4f0731_nv); 全量 fallback 0% (117 total fb=0 全走 primary); 本窗口非-200 0 rows (连已归属 hermes 的 1× zombie_empty_completion 也移出 30min, 上轮 caller=hermes|502|1 仍归属 peer 非 cc2); per-key 基本全 pexec_success (fid 281478d0) 仅 k0/k1 3× NVCFPexecRemoteDisconnected (fid 52e1ddb6 历史坏 fid) + k3 1× empty_200 一次性 distributed transient 与上轮基本持平未上升, 无 multi-key 连续复发; buffer 全 attempt-1 直flush 7-9s 零重试零级联零 buffer_exhausted; 容器全 200)**
> cc4101-primary (主 nv_gw:40006) 实测 30min = **117/117 = 100.0% SR, 0 bad** (cc2 专属零错误)
> — **零 502, 零错误(cc2), 零 fallback, 无任何新签名(cc2 范围)**
> 非-200 归属: 本窗口 0 rows (任何 caller 无非-200)。上轮唯一 1× zombie_empty_completion (502)
> caller=**hermes** (peer) → 归属 peer 非 cc2 主链 (JOIN 铁证)
> fallback: 0% (117 total, fb=0, 全走 primary)
> tier 错误: 30min (tier=dsv4f0731_nv) 117 pexec_success, 仅 fid 52e1ddb6 的 k0/k1 3× NVCFPexecRemoteDisconnected + k3 1× empty_200 一次性 distributed transient (与上轮基本持平), 无 multi-key 连续复发
> buffer: 全 attempt-1 直 flush 秒回 (7-9s), 零重试零级联零 buffer_exhausted
> 容器 (/health 2026-08-07 22:55 CST): nv_gw 200, cc4101 200; docker ps nv_gw Up 19h
> 上轮: R1107 (NOP, 112/112=100% SR 零错误)

## 本轮 (R1108) 改动 + 依据 + 验证

### 改动: 无 (NOP。30min cc2 主链 117/117=100.0% SR 零错误零 fallback, buffer 全 attempt-1
### 直 flush 秒回。本窗口任何 caller 非-200 = 0 rows (连已归属 hermes 的 1× zombie 也移出窗口)。
### k0/k1 RD (fid 52e1ddb6) + k3 empty_200 量小一次性 distributed transient 与上轮基本持平
### 未上升, 无 multi-key 连续复发, 非配置漂移。cc2 范围无新签名 → 不改码)

### 依据 (实测 DB 2026-08-07 22:55 CST + 实时复核 + /health)

- **30min nv_requests (cc4101-primary)**: status 仅 200 × **117** = 100.0% SR, 0 错误
  (实时复核 `caller|status|count` = `cc4101-primary|200|117`)。较 R1107 的 112 略升, 全 200。
- **30min 全量非-200 归属**: 实时复核 `caller|status|count` = **0 rows** (本窗口任何 caller 无非-200,
  上轮 hermes 1× zombie_empty_completion 已移出 30min)。cc2 范围延续零非-200。
- **fallback**: 0% (117 total, fallback_triggered=0, 全走 primary)。
- **nv_tier_attempts 30min**: tier=dsv4f0731_nv, 117 `pexec_success`; 仅 fid **52e1ddb6**
  (历史记忆坏 fid — 越界容器 40666 hermes 线泄漏源) 的 k0/k1 3× `NVCFPexecRemoteDisconnected`
  + k3 1× `empty_200` 一次性 distributed transient 单请求 buffer 自愈。per-key ok:
  k0 24/26, k1 22/23, k2 22/22, k3 24/25, k4 25/25。量 (4x) 与 R1107 持平未上升, 无 multi-key 连续复发。
- **buffer 日志 (docker logs --since 30m)**: 全 `attempt=1/5` 直 flush 秒回 (req=e1eff9d7 elapsed=7s,
  req=2fcf56c2 elapsed=9s), verdict 全 success_tool_call, 零重试零级联零 buffer_exhausted。
- **容器 /health 2026-08-07 22:55 CST**: 40006 nv_gw http 200 (nv_num_keys=5, nvcf_pexec_models 含
  dsv4f0731_nv), 4101 cc4101 http 200 (primary=dsv4f0731_nv)。docker ps: nv_gw Up 19h。

### 本轮数据

| 指标 | 值 | 状态 |
|---|---|---|
| cc2 主链 (40006) 30min | cc4101-primary **117/117 = 100.0% SR, 0 bad** | ✅ 全绿 |
| cc2 专属错误分类 | (cc2 专属 0 rows) 零错误 | ✅ |
| 非-200 归属 | 0 rows (任何 caller 无非-200; 上轮 hermes 1× zombie 已移出窗口) | ✅ |
| fallback 触发率 | 0% (117 total, fb=0, 全走 primary) | ✅ |
| per-key tier 错误 | 117 pexec_success; 仅 fid 52e1ddb6 的 k0/k1 3× RD + k3 1× empty_200 一次性 transient 持平, 无 multi-key 连续复发 | ✅ |
| buffer | 全 attempt-1 直 flush (7-9s), 零重试零级联零 buffer_exhausted | ✅ |
| container /health | nv_gw 200, cc4101 200 (Up 19h) | ✅ |

## 下一步
- 延续 NOP。cc2 主链连续多轮 (R1096-R1108) 100% SR + zero fallback, 无参数可调。
- **k0/k1 RD** (fid 52e1ddb6) + **k3 empty_200**: 量小 (总 4x, 均单请求, 与上轮基本持平未上升),
  一次性 distributed transient, 单请求 buffer 自愈, 与历史记忆模式一致 (泄漏源=越界容器 40666
  hermes 线, 宿主分离)。无 multi-key 连续复发, 不构成配置漂移。仅当 RD/empty_200 在多 key **连续
  复发** (多个独立请求多 key 持续失败) 才查链路/mihomo 线路。
- **hermes 1× zombie_empty_completion** (上轮 peer 归属) 持续关注, 归属 peer 非 cc2 不改动。
- 若 zombie_empty_completion 或其他错误中出现 caller=cc4101-primary (c.parent) 才进 cc2 指标并处置。

## 参数快照 (未动, 同 R1107)
- 本轮零改动。nv_gw env 复核: NV_GLM52_MODE_CHAIN=pexec_us_rr, NVU_DISABLE_MS_FALLBACK=0,
  KEY_COOLDOWN_S=30, NV_INTEGRATE_KEY_COOLDOWN_S=90, UPSTREAM_TIMEOUT=90, BUFFER 5×90s=450s,
  Tier budget 180s. nvcf_pexec_models 含 dsv4f0731_nv。
- cc4101: PRIMARY_UPSTREAM_MODEL=dsv4f0731_nv, PRIMARY_UPSTREAM_URL=http://nv_gw:40006/v1/messages,
  PRIMARY_HEADER_TIMEOUT=400, CC4101_STREAM_TOTAL_DEADLINE_S=470, UPSTREAM_TIMEOUT=130,
  FALLBACK_UPSTREAM_URL=http://ms_gw:40007/v1/chat/completions (历史残留, 未触发)。
- deadline 链 (未动): 90s/attempt × 5 = 450s buffer < 470s cc4101 < 600s SDK < 900s idle。