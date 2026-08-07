# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: **R1099 (NOP 巡检轮/不改码 — cc2 主链 100/100=100.0% SR 零错误 (cc4101-primary 经 nv_gw, primary model=dsv4f0731_nv); 全量 dsv4f0731_nv 97.9% fallback 0%; 3× zombie_empty_completion 全部归属 hermes (dsv4f0731_nv 线, peer) 非 cc2, JOIN 复核 caller=hermes 专属; per-key 基本全 pexec_success 仅 k3 RD + k4 empty_200 各 1× 一次性; buffer 无重试日志 = 全 attempt-1 直flush 秒回 零级联零 buffer_exhausted; 容器全 200)**
> cc4101-primary (主 nv_gw:40006) 实测 30min = **100/100 = 100.0% SR, 0 bad** (cc2 专属零错误)
> — **零 502, 零错误(cc2), 零 fallback, 无任何新签名(cc2 范围)**
> 全量 (含 peer) dsv4f0731_nv SR = 97.9% (137/140), 3 bad 全为 hermes 归属
> 3× 502 zombie_empty_completion — caller=**hermes** (peer), tier=dsv4f0731_nv → 归属 peer 非 cc2 主链 (JOIN 铁证, caller|count=hermes|3)
> tier 错误: 30min 5 key 基本全 pexec_success (0/1/2/3/4=19/19/16/25/21), 仅 k3 1× RD + k4 1× empty_200 一次性
> buffer: 无 NV-BUFFER-EXEC-FAIL / WAIT- 日志 = 全 attempt-1 直 flush 秒回, 零重试零级联零 buffer_exhausted
> 容器 (/health 2026-08-07 22:17 CST): nv_gw 200 (passthrough, nv_num_keys=5, nvcf_pexec_models 含 dsv4f0731_nv, default=glm5_2_nv), cc4101 200 (primary=dsv4f0731_nv); docker ps nv_gw Up 19h, cc4101 Up 18h
> 上轮: R1098 (NOP, 97/97=100% SR 零错误)

## 本轮 (R1099) 改动 + 依据 + 验证

### 改动: 无 (NOP。30min cc2 主链 100/100=100.0% SR 零错误零 fallback, buffer 无重试日志 = 全直 flush
### 秒回零重试零级联。唯一 3× zombie_empty_completion 全部归属 hermes (peer caller, dsv4f0731_nv 线),
### JOIN 复核 caller=hermes 专属。非 cc2 之作。cc2 范围无新签名 → 不改码)

### 依据 (实测 DB 2026-08-07 22:17 CST + 实时复核 + /health)

- **30min nv_requests (cc4101-primary)**: status 仅 200 × **100** = 100.0% SR, 0 错误。
  实时 10min 复核: caller=cc4101-primary count=29 全 200 (与注入数据一致)。
- **30min 全量非-200 归属**: 唯一 3× zombie_empty_completion (status=502) 全部 caller=**hermes**
  (dsv4f0731_nv 线, peer)。本轮实时 JOIN 复核: `caller|count` = `hermes|3` (cc4101-primary 0),
  request_id JOIN 复核归属铁证 (记忆 bad-fid-52e1ddb6 判归属法)。
- **cc_requests 真实 SR**: 全走主链, fallback 0% (无 fallback_triggered)。
- **nv_tier_attempts 30min**: 5 key 基本全 `pexec_success` (0/1/2/3/4=19/19/16/25/21); 仅 k3 1×
  `NVCFPexecRemoteDisconnected` + k4 1× `empty_200` 一次性 transient。无持续 tier 错误, 无
  buffer_exhausted (对比 R1098 仅 k4 empty_200 1×, 本轮 k3 RD 为一次性不构成复发)。
- **buffer 日志**: 30min 无 NV-BUFFER-EXEC-FAIL / WAIT- 等待日志 = cc4101-primary 请求 全 attempt-1
  直 flush 秒回, 零重试零级联 (SSLEOFError 无复发)。
- **容器 /health 2026-08-07 22:17 CST**: 40006 nv_gw http 200 (passthrough, nv_num_keys=5,
  nvcf_pexec_models 含 dsv4f0731_nv, default=glm5_2_nv), 4101 cc4101 http 200 (primary=dsv4f0731_nv)。
  docker ps: nv_gw Up 19h, cc4101 Up 18h。

### 本轮数据

| 指标 | 值 | 状态 |
|---|---|---|
| cc2 主链 (40006) 30min | cc4101-primary **100/100 = 100.0% SR, 0 bad** | ✅ 全绿 |
| cc2 专属错误分类 | (cc2 专属 0 rows) — 零错误 | ✅ |
| 全量 (含 peer) SR | dsv4f0731_nv 97.9% (137/140), 3 bad 全为 hermes | ✅ peer 归属 |
| fallback 触发率 | 0% (全走 primary) | ✅ |
| per-key / tier 错误 | 基本全 pexec_success; 仅 k3 1× RD + k4 1× empty_200 一次性 | ✅ 零持续 tier 错误 |
| buffer | 无重试日志 = 全 attempt-1 直 flush 秒回, 零级联零 buffer_exhausted | ✅ |

## 下一步
- 延续 NOP。cc2 主链连续多轮 100% SR + zero fallback (R1093-R1098 镜像, 本轮 R1099 同样), 无参数可调。
- **hermes 3× zombie_empty_completion** (dsv4f0731_nv 线) 持续关注, 归属 peer 非 cc2 不改动。
- 若 zombie_empty_completion 中出现 caller=cc4101-primary 才进 cc2 指标; 若 k3 RD / SSLEOFError 在多 key
  **连续复发** 才查 mihomo 线路 (记忆 ssleof-transient R1077: 单次 NOP 自愈, 持续分布才动手)。
  本轮 k3/k4 各 1× 一次性不构成复发。

## 参数快照 (未动, 同 R1098)
- 本轮零改动。见 R1098 参数快照。
- nv_gw env 复核: NV_GLM52_MODE_CHAIN=pexec_us_rr, KEY_MODE_BINDING= 空, KEY_FID_BIND=0:0;1:0;2:0;3:0;4:0。