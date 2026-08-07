# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: **R1096 (NOP 巡检轮/不改码 — cc2 主链 100/100=100.0% SR 零错误 (cc4101-primary 经 nv_gw, primary model=dsv4f0731_nv); cc_requests 101/101=100% fallback 0.0%; 3× zombie_empty_completion 全部归属 hermes (dsv4f0731_nv 线, peer) 非 cc2; per-key 全 pexec_success 仅 k2 RD + k4 empty_200 各 1× 一次性; buffer 唯一 req=6d9589b5 attempt-2 SSLEOFError(k4) 10s backoff attempt-3 自愈 200, 零级联; 容器全 200)**
> cc4101-primary (主 nv_gw:40006) 实测 30min = **100/100 = 100.0% SR, 0 bad** (cc2 专属零错误)
> — **零 502, 零错误(cc2), 零 fallback, 无任何新签名(cc2 范围)**
> cc_requests 真实 SR 101/101 = **100.0%**, fallback 0/101 = 0.0%
> 3× 502 zombie_empty_completion — caller=**hermes** (peer), tier=dsv4f0731_nv → 归属 peer 非 cc2 主链
> tier 错误: 30min 5 key 全 pexec_success (0/1/2/3/4=21/16/19/23/22), 仅 k2 1× RD + k4 1× empty_200 一次性
> buffer: 唯一 req=6d9589b5 attempt-2 SSLEOFError(k4, penalty 10s) → execute_failed → 10s backoff → attempt-3 200 (41.4s success_tool_call 6885b), 零级联零 502; 其余全 attempt-1 直flush 秒回
> 容器 (/health 2026-08-07 22:05 CST): nv_gw 200 (nv_num_keys=5, nvcf_pexec_models 含 dsv4f0731_nv, default=glm5_2_nv), cc4101 200 (primary=dsv4f0731_nv); nv_gw env NV_GLM52_MODE_CHAIN=pexec_us_rr, KEY_MODE_BINDING= 空
> 上轮: R1095 (NOP, 102/102=100% SR 零错误)

## 本轮 (R1096) 改动 + 依据 + 验证

### 改动: 无 (NOP。30min cc2 主链 100/100=100.0% SR 零错误零 fallback, buffer 全直 flush 秒回,
### 唯一 transient SSLEOFError(attempt-2,k4) attempt-3 自愈 200 零级联。3× zombie_empty_completion 全部归属
### hermes (peer caller, dsv4f0731_nv 线), 非 cc2 之作。cc2 范围无新签名 → 不改码)

### 依据 (实测 DB 2026-08-07 22:0x CST + docker logs + /health)

- **30min nv_requests (cc4101-primary)**: status 仅 200 × **100** = 100.0% SR, 0 错误。
- **30min 全量错误归属**: 唯一 3× `zombie_empty_completion` 全部 caller=**hermes** (dsv4f0731_nv 线, egress
  134.195.101.197/193)。→ 归属 peer, 不进 cc2 指标 (request_id JOIN 复核归属铁证)。
- **cc_requests 真实 SR (含 fallback)**: 101/101 = **100.0%**, fallback 0/101 = 0.0% (全走主链)。
- **nv_tier_attempts 30min**: 5 key 全 `pexec_success` (0/1/2/3/4=21/16/19/23/22); 仅 2 个一次性 transient:
  k2 1× `NVCFPexecRemoteDisconnected`, k4 1× `empty_200`。无持续 tier 错误。
- **buffer 日志**: 唯一 req=**6d9589b5** attempt-2 时 k4 一次性 **SSLEOFError** (transport_err penalty 10s 不累计
  conn_count) → NV-BUFFER-EXEC-FAIL (elapsed 26s) → 10s backoff → attempt-3 成功 flush (41.4s, success_tool_call
  6885b) → **final status=200 零错误**。单 key egress 抖动 attempt-3 自愈, 零级联 (记忆 ssleof-transient R1077:
  持续分布才查 mihomo; 单次 NOP 自愈)。其余请求 (如 eea7f297) 全 attempt-1 直flush 10s。
- **容器 /health 2026-08-07 22:05 CST**: 40006 nv_gw 200 (nv_num_keys=5, nvcf_pexec_models 含 dsv4f0731_nv,
  default=glm5_2_nv), 4101 cc4101 200 (primary=dsv4f0731_nv); nv_gw env NV_GLM52_MODE_CHAIN=pexec_us_rr,
  KEY_MODE_BINDING= 空。CC4101 PRIMARY_UPSTREAM_MODEL=dsv4f0731_nv (env 铁证)。

### 本轮数据

| 指标 | 值 | 状态 |
|---|---|---|
| cc2 主链 (40006) 30min | cc4101-primary **100/100 = 100.0% SR, 0 bad** | ✅ 全绿 |
| cc2 专属错误分类 | (cc2 专属 0 rows) — 零错误 | ✅ |
| cc_requests 真实 SR | 101/101 = 100.0%, fallback 0/101 = 0.0% | ✅ |
| 502 归属 | 3× zombie_empty_completion 全部 = hermes (dsv4f0731_nv 线) | ⚠️ peer, 非 cc2 |
| per-key / tier 错误 | 5 key 全 pexec_success; 仅 k2 RD + k4 empty_200 各 1× 一次性 | ✅ 零持续 tier 错误 |
| buffer | 唯一 req=6d9589b5 SSLEOFError(attempt-2,k4) attempt-3 自愈 200 零级联; 余全 attempt-1 直flush | ✅ healthy self-heal |

## 下一步
- 保持 NOP 观察 (cc2 主链 100% SR, 无参数可调)。
- **hermes 3× zombie_empty_completion** (dsv4f0731_nv 线) 持续关注, 归属 peer 非 cc2 不改动。
- 若 SSLEOFError / RD 多 key **连续复发** 且不再 attempt-N 自愈直 flush, 才查 mihomo 线路端口 (目前单次自愈)。

## 参数快照 (未动, 同 R1095)
- 本轮零改动。见 R1095 参数快照。