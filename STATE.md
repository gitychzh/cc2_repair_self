# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: **R1097 (NOP 巡检轮/不改码 — cc2 主链 100/100=100.0% SR 零错误 (cc4101-primary 经 nv_gw, primary model=dsv4f0731_nv); cc_requests 138 全走主链 fallback 0.0%; 3× zombie_empty_completion 全部归属 hermes (dsv4f0731_nv 线, peer) 非 cc2; per-key 全 pexec_success 仅 k2 RD + k4 empty_200 各 1× 一次性; buffer 全 attempt-1 直flush 秒回 (2-12s) 零重试零级联零 buffer_exhausted; 容器全 200)**
> cc4101-primary (主 nv_gw:40006) 实测 30min = **100/100 = 100.0% SR, 0 bad** (cc2 专属零错误)
> — **零 502, 零错误(cc2), 零 fallback, 无任何新签名(cc2 范围)**
> 全量 (含 peer) dsv4f0731_nv SR = 97.8% (135/138), 3 bad 全为 hermes 归属
> 3× 502 zombie_empty_completion — caller=**hermes** (peer), tier=dsv4f0731_nv → 归属 peer 非 cc2 主链 (JOIN 铁证)
> tier 错误: 30min 5 key 全 pexec_success (0/1/2/3/4=20/18/18/22/22), 仅 k2 1× RD + k4 1× empty_200 一次性
> buffer: 全 attempt-1 直 flush 秒回 (2-12s, success_text/success_tool_call, 3ee15127/f2b8c53d/b83147bf/e17d95ad), 零重试零级联零 buffer_exhausted, 无 WAIT- 等待
> 容器 (/health 2026-08-07 22:07 CST): nv_gw 200 (passthrough, nv_num_keys=5, nvcf_pexec_models 含 dsv4f0731_nv, default=glm5_2_nv), cc4101 200 (primary=dsv4f0731_nv); nv_gw env NV_GLM52_MODE_CHAIN=pexec_us_rr, KEY_MODE_BINDING= 空
> 上轮: R1096 (NOP, 100/100=100% SR 零错误)

## 本轮 (R1097) 改动 + 依据 + 验证

### 改动: 无 (NOP。30min cc2 主链 100/100=100.0% SR 零错误零 fallback, buffer 全直 flush 秒回,
### 零重试零级联。唯一 3× zombie_empty_completion 全部归属 hermes (peer caller, dsv4f0731_nv 线),
### 非 cc2 之作。cc2 范围无新签名 → 不改码)

### 依据 (实测 DB 2026-08-07 22:07 CST + docker logs + /health)

- **30min nv_requests (cc4101-primary)**: status 仅 200 × **100** = 100.0% SR, 0 错误。
- **30min 全量非-200 归属**: 唯一 3× zombie_empty_completion (status=502) 全部 caller=**hermes**
  (dsv4f0731_nv 线, peer)。request_id JOIN 复核归属铁证: 不进 cc2 专属指标 (记忆 bad-fid-52e1ddb6 判归属法)。
- **cc_requests 真实 SR**: 138 全走主链, fallback 0% (cc4101→nv_gw primary 全 200)。
- **nv_tier_attempts 30min**: 5 key 全 `pexec_success` (0/1/2/3/4=20/18/18/22/22); 仅 2 个一次性 transient:
  k2 1× `NVCFPexecRemoteDisconnected`, k4 1× `empty_200`。无持续 tier 错误, 无 buffer_exhausted。
- **buffer 日志**: cc4101-primary 请求全 **attempt-1 直 flush 秒回** (2-12s), verdict=
  `success_text` (req=3ee15127, f2b8c53d) / `success_tool_call` (req=b83147bf, e17d95ad), 零重试零级联;
  无 NV-BUFFER-EXEC-FAIL, 无 WAIT- 等待日志 (本轮 SSLEOFError 无复发, 对比 R1096 单次自愈)。
- **容器 /health 2026-08-07 22:07 CST**: 40006 nv_gw 200 (passthrough, nv_num_keys=5,
  nvcf_pexec_models 含 dsv4f0731_nv, default=glm5_2_nv), 4101 cc4101 200 (primary=dsv4f0731_nv)。
  nv_gw env NV_GLM52_MODE_CHAIN=pexec_us_rr, KEY_MODE_BINDING= 空, KEY_FID_BIND=0:0;1:0;2:0;3:0;4:0。

### 本轮数据

| 指标 | 值 | 状态 |
|---|---|---|
| cc2 主链 (40006) 30min | cc4101-primary **100/100 = 100.0% SR, 0 bad** | ✅ 全绿 |
| cc2 专属错误分类 | (cc2 专属 0 rows) — 零错误 | ✅ |
| 全量 (含 peer) SR | dsv4f0731_nv 97.8% (135/138), 3 bad 全为 hermes | ✅ peer 归属 |
| fallback 触发率 | 0/138 = 0.0% | ✅ |
| per-key / tier 错误 | 5 key 全 pexec_success; 仅 k2 RD + k4 empty_200 各 1× 一次性 | ✅ 零持续 tier 错误 |
| buffer | 全 attempt-1 直 flush 秒回 (2-12s), 零重试零级联零 buffer_exhausted | ✅ |

## 下一步
- 保持 NOP 观察 (cc2 主链连续多轮 100% SR + zero fallback, 无参数可调)。
- **hermes 3× zombie_empty_completion** (dsv4f0731_nv 线) 持续关注, 归属 peer 非 cc2 不改动。
- 若 zombie_empty_completion 中出现 caller=cc4101-primary 才进 cc2 指标; 若 SSLEOFError/RD 多 key
  **连续复发** 才查 mihomo 线路 (记忆 ssleof-transient R1077: 单次 NOP 自愈, 持续分布才动手)。

## 参数快照 (未动, 同 R1096)
- 本轮零改动。见 R1096 参数快照。