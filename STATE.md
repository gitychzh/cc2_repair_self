# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: **R1095 (NOP 巡检轮/不改码 — cc2 主链 102/102=100.0% SR 零错误 (cc4101-primary 经 nv_gw, 现 primary model=dsv4f0731_nv); cc_requests 103/103=100% fallback 0.0%; 3× zombie_empty_completion 全部归属 hermes (dsv4f0731_nv 线, peer caller) 非 cc2; per-key 全 pexec_success 仅 k4 empty_200 + k2 RD 各 1× 一次性; buffer 全 attempt-1 直flush 9-11s 秒回零重试零 502; 容器全 200)**
> cc4101-primary (主 nv_gw:40006) 实测 30min = **102/102 = 100.0% SR, 0 bad** (cc2 专属零错误)
> — **零 502, 零错误(cc2), 零 fallback, 无任何新签名(cc2 范围)**
> cc_requests 真实 SR 103/103 = **100.0%**, fallback 0/103 = 0.0%
> 3× 502 zombie_empty_completion (bc925d33 66s / 8cc82d57 5.5s / 322b7d2f 3s) — caller=**hermes**, tier=dsv4f0731_nv, egress 134.195.101.197/193
>   → 归属 peer 非 cc2 主链, 不计入 cc2 指标 (记忆: bad-fid 归属用 request_id JOIN 复核)
> tier 错误: 30min 5 key 全 pexec_success (102), 仅 k4 1× empty_200 + k2 1× NVCFPexecRemoteDisconnected (一次性 transient 非分布)
> buffer 复窗口 cc2 全 attempt-1 直flush 9-11s, 零重试零 502 零 buffer_exhausted 零 WAIT 挂起 (req=93f83c82 8s / ae0e319d 9.8s / fa85824e 11.3s)
> 容器 (/health 复核 2026-08-07 21:58 CST): nv_gw 200 (nv_num_keys=5, nvcf_pexec_models 含 dsv4f0731_nv, default=glm5_2_nv), cc4101 200;
>   nv_gw env: NV_GLM52_MODE_CHAIN=pexec_us_rr, KEY_MODE_BINDING= 空, NVU_DISABLE_MS_FALLBACK=0, NV_INTEGRATE_MODELS=glm5_2_nv
> 上轮: R1094 (NOP, 主链 115/115=100% SR 零错误, 唯一 k3 一次性 execute_failed 自愈)

## 本轮 (R1095) 改动 + 依据 + 验证

### 改动: 无 (NOP。30min cc2 主链 102/102=100.0% SR 零错误零 fallback, buffer 全 attempt-1 直flush 秒回零重试,
### 无配置漂移, cc2 范围无新签名。3× zombie_empty_completion 全部归属 hermes (peer caller, dsv4f0731_nv 线), 非 cc2
### 之作, 不构成 cc2 目标回归)

### 依据 (轮前注入 21:56:33 CST + DB/日志实测 2026-08-07 21:58 CST + 容器 /health 实测)

- **30min nv_requests (caller×model×status)**: cc4101-primary|dsv4f0731_nv|200|**102**, hermes|dsv4f0731_nv|200|30 + 502|3。
  - **cc2 专属 (cc4101-primary) = 102/102 = 100.0% SR, 0 错误**。
- **错误分类**: 唯一 3× `zombie_empty_completion` — 全部 **caller=hermes** (avg ~24.8s), tier_model=dsv4f0731_nv,
  upstream_type=nvcf_pexec, egress 134.195.101.197/193, finish_reason=stop 但空 completion。
  → 归属 peer hermes 线 (非 cc2 主链), 不进入 cc2 指标与优化范围。
- **cc_requests 真实 SR (含 fallback)**: 103/103 = **100.0%**, fallback 0/103 = **0.0%** (全走主链)。
- **tier 错误 (nv_tier_attempts 30min)**: 5 key 全 `pexec_success` (102); 唯一 2 个一次性 transient:
  k4 1× `empty_200`, k2 1× `NVCFPexecRemoteDisconnected`。**无持续 tier 错误** (同一性以 pexec_success 主体为准)。
- **buffer 日志** (--since 30m): cc2 请求全 attempt-1 直 flush 9-11s (success_tool_call), 零重试零 502。
  例 req=93f83c82 8s / ae0e319d 9.8s / fa85824e 11.3s; **零 buffer_exhausted, 零 WAIT 挂起**。
- **容器 /health 实测 2026-08-07 21:58 CST**: 40006 nv_gw 200 (nv_num_keys=5, nvcf_pexec_models=
  kimi_nv/dsv4p_nv/dsv4f_nv/dsv4f0731_nv/glm5_2_nv, default=glm5_2_nv); 4101 cc4101 200;
  nv_gw env NV_GLM52_MODE_CHAIN=pexec_us_rr, KEY_MODE_BINDING= 空, NVU_DISABLE_MS_FALLBACK=0, NV_INTEGRATE_MODELS=glm5_2_nv。
- **配置观察 (记录不改)**: 现运行几何 cc4101.**PRIMARY_UPSTREAM_MODEL=dsv4f0731_nv**, PRIMARY_UPSTREAM_URL=http://nv_gw:40006/v1/messages,
  FALLBACK=ms_gw 40007。cc2 主链实际经 nv_gw 走 dsv4f0731_nv, 以 env+DB 铁证为准。

### 本轮数据

| 指标 | 值 | 状态 |
|---|---|---|
| cc2 主链 (40006) 30min | cc4101-primary **102/102 = 100.0% SR, 0 bad** | ✅ 全绿 |
| cc2 专属错误分类 | (cc2 专属 0 rows) — **零错误** | ✅ |
| cc_requests 真实 SR | 103/103 = 100.0%, fallback 0/103 = 0.0% | ✅ |
| 502 归属 | 3× zombie_empty_completion 全部 = **hermes** (dsv4f0731_nv 线) | ⚠️ peer, 非 cc2 |
| per-key / tier 错误 | 5 key 全 pexec_success; 仅 k4 empty_200 + k2 RD 各 1× 一次性 | ✅ 零持续 tier 错误 |
| buffer | cc2 全 attempt-1 直flush 9-11s, 零重试零 502 零 buffer_exhausted | ✅ healthy |

## 下一步
- 保持 NOP 观察 (cc2 主链 100% SR, 无参数可调)。
- **hermes 3× zombie_empty_completion** (dsv4f0731_nv 线) 列入下轮关注: 若多轮持续复发且影响 hermes 线, 但**归属非 cc2,
  不改动**; 判归属用 request_id JOIN nv_tier_attempts 复核。本轮不改。
- 若 egress IP 多轮连续失败不再 attempt-1 直flush, 才查 mihomo 端口。

## 参数快照 (未动, 与 R1094 一致)
- 本轮零改动。配置同 R1094/R1093。见 R1093 参数快照。
