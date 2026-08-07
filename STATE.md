# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: **R1110 (NOP 巡检轮/不改码 — cc2 主链 112/112=100.0% SR 零错误 (cc4101-primary 经 nv_gw, primary model=dsv4f0731_nv); 全量 dsv4f0731_nv 161/161=100% SR; fallback 0% (161 total fb=0 全走 primary); 本窗口任何 caller 非-200 0 rows 零错误; per-key 全 pexec_success (fid 281478d0) 仅 fid 52e1ddb6 的 k0/k1 2× NVCFPexecRemoteDisconnected + k3 1× empty_200 一次性 distributed transient 与上轮基本持平未上升, 无 multi-key 连续复发; buffer 无重试无级联默认全 attempt-1 直flush; 容器全 200)**
> cc4101-primary (主 nv_gw:40006) 实测 30min = **112/112 = 100.0% SR, 0 bad** (cc2 专属零错误)
> — **零 502, 零错误(cc2), 零 fallback, 无任何新签名(cc2 范围)**
> 非-200 归属: 本窗口 0 rows (任何 caller 无非-200)
> fallback: 0% (161 total, fb=0, 全走 primary)
> tier 错误: 30min (tier=dsv4f0731_nv) 全 pexec_success, 仅 fid 52e1ddb6 的 k0/k1 2× NVCFPexecRemoteDisconnected + k3 1× empty_200 一次性 distributed transient (与上轮基本持平), 无 multi-key 连续复发
> buffer: 无 buffer/wait/keymanager 日志, 无重试无级联无 buffer_exhausted
> 容器 (/health 2026-08-07 23:05 CST): nv_gw 200 (5 key, dsv4f0731_nv 含), cc4101 200 (dsv4f0731_nv); docker ps nv_gw Up 20h, cc4101 Up 19h
> 上轮: R1109 (NOP, 115/115=100% SR 零错误)

## 本轮 (R1110) 改动 + 依据 + 验证

### 改动: 无 (NOP。30min cc2 主链 112/112=100.0% SR 零错误零 fallback, 任何 caller 非-200 0 rows。
### k0/k1 RD (fid 52e1ddb6) + k3 empty_200 量小一次性 distributed transient 与上轮基本持平
### 未上升, 无 multi-key 连续复发, 非配置漂移。cc2 范围无新签名 → 不改码)

### 依据 (注入轮前分析 2026-08-07 23:02 CST + 实时 /health 复核)

- **30min nv_requests (cc4101-primary)**: status 仅 200 × **112** = 100.0% SR, 0 错误
  (注入报告 `cc4101-primary|dsv4f0731_nv|200|112`)。
- **dsv4f0731_nv 全量 SR**: 161/161 = **100.0%** (所有 caller)。
- **30min 全量非-200 归属**: (无错误) 0 rows, 任何 caller 无非-200。cc2 范围延续多轮 (R1096-R1110) 零非-200。
- **fallback**: 0% (161 total, fallback_triggered=0, 全走 primary)。
- **nv_tier_attempts 30min**: tier=dsv4f0731_nv, 全 `pexec_success` 为主;
  仅 fid **52e1ddb6** (历史记忆坏 fid — 越界容器 40666 hermes 线泄漏源) 的 k0/k1 2× `NVCFPexecRemoteDisconnected`
  + k3 1× `empty_200` 一次性 distributed transient 单请求 buffer 自愈。量 (3x) 与 R1109 (3x) 持平未上升,
  无 multi-key 连续复发。
- **buffer 日志 (docker logs --since 30m)**: 无 buffer/wait/keymanager 日志 —— 无重试无级联无 buffer_exhausted。
- **容器 /health 2026-08-07 23:05 CST**: 40006 nv_gw http 200 (nv_num_keys=5, nvcf_pexec_models 含
  dsv4f0731_nv), 4101 cc4101 http 200 (primary=dsv4f0731_nv)。docker ps: nv_gw Up 20h, cc4101 Up 19h。

### 本轮数据

| 指标 | 值 | 状态 |
|---|---|---|
| cc2 主链 (40006) 30min | cc4101-primary **112/112 = 100.0% SR, 0 bad** | ✅ 全绿 |
| cc2 专属错误分类 | (无错误) 零错误 | ✅ |
| 非-200 归属 | 0 rows (任何 caller 无非-200) | ✅ |
| fallback 触发率 | 0% (161 total, fb=0, 全走 primary) | ✅ |
| per-key tier 错误 | 全 pexec_success; 仅 fid 52e1ddb6 的 k0/k1 2× RD + k3 1× empty_200 一次性 transient 持平, 无 multi-key 连续复发 | ✅ |
| buffer | 无 buffer/wait 日志, 无重试无级联无 buffer_exhausted | ✅ |
| container /health | nv_gw 200, cc4101 200 (Up 19-20h) | ✅ |

## 下一步
- 延续 NOP。cc2 主链连续多轮 (R1096-R1110) 100% SR + zero fallback, 无参数可调。
- **k0/k1 RD** (fid 52e1ddb6) + **k3 empty_200**: 量小 (总 3x, 均单请求, 与上轮基本持平未上升),
  一次性 distributed transient, 单请求 buffer 自愈, 与历史记忆模式一致 (泄漏源=越界容器 40666
  hermes 线, 宿主分离)。无 multi-key 连续复发, 不构成配置漂移。仅当 RD/empty_200 在多 key **连续
  复发** (多个独立请求多 key 持续失败) 才查链路/mihomo 线路。
- 若 zombie_empty_completion 或其他错误中出现 caller=cc4101-primary (c.parent) 才进 cc2 指标并处置。

## 参数快照 (未动, 同 R1109)
- 本轮零改动。nv_gw env 复核: NVU_DISABLE_MS_FALLBACK=0, KEY_COOLDOWN_S=30,
  NV_INTEGRATE_KEY_COOLDOWN_S=90, UPSTREAM_TIMEOUT=90, BUFFER 5×90s=450s, Tier budget 180s,
  NVU_FORCE_STREAM_UPGRADE_TIMEOUT=150, NVU_FORCE_STREAM_UPGRADE=0, MIN_OUTBOUND_INTERVAL_S=10,
  NVU_CALLER_KEY_MAP=hermes:2;openclaw:3;opencode:4. nvcf_pexec_models 含 dsv4f0731_nv。
- cc4101: PRIMARY_UPSTREAM_MODEL=dsv4f0731_nv, PRIMARY_UPSTREAM_URL=http://nv_gw:40006/v1/messages,
  PRIMARY_HEADER_TIMEOUT=400, CC4101_STREAM_TOTAL_DEADLINE_S=470, UPSTREAM_TIMEOUT=130,
  FALLBACK_UPSTREAM_URL=http://ms_gw:40007/v1/chat/completions (历史残留, 未触发)。
- deadline 链 (未动): 90s/attempt × 5 = 450s buffer < 470s cc4101 < 600s SDK < 900s idle。