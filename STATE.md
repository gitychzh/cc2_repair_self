# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: **R1105 (NOP 巡检轮/不改码 — cc2 主链 109/109=100.0% SR 零错误 (cc4101-primary 经 nv_gw, primary model=dsv4f0731_nv); 全量 fallback 0% (109 total fb=0 全走 primary); 唯一 1× zombie_empty_completion 归属 hermes (peer) 非 cc2 主链 (JOIN caller=hermes|502|1); per-key 基本全 pexec_success 仅 k0 1× + k3 2× NVCFPexecRemoteDisconnected (fid 52e1ddb6 历史坏 fid) + k3 1× empty_200 一次性 distributed transient 与上轮持平未上升, 无 multi-key 连续复发; buffer 全 attempt-1 直flush 秒回(5-14s) 零重试零级联零 buffer_exhausted; 容器全 200)**
> cc4101-primary (主 nv_gw:40006) 实测 30min = **109/109 = 100.0% SR, 0 bad** (cc2 专属零错误)
> — **零 502, 零错误(cc2), 零 fallback, 无任何新签名(cc2 范围)**
> 非-200 归属: 唯一 1× zombie_empty_completion (502) — caller=**hermes** (peer) → 归属 peer 非 cc2 主链 (JOIN 铁证, caller=hermes|502|1)
> fallback: 0% (109 total, fb=0, 全走 primary)
> tier 错误: 30min (tier=dsv4f0731_nv) 5 key 基本全 pexec_success, 仅 k0 1× + k3 2× NVCFPexecRemoteDisconnected + k3 1× empty_200 一次性 distributed transient (与上轮基本持平), 无 multi-key 连续复发
> buffer: 全 attempt-1 直 flush 秒回 (5-14s), 零重试零级联零 buffer_exhausted
> 容器 (/health 2026-08-07 22:45 CST): nv_gw 200, cc4101 200; docker ps nv_gw Up 19h, cc4101 Up 19h
> 上轮: R1104 (NOP, 107/107=100% SR 零错误)

## 本轮 (R1105) 改动 + 依据 + 验证

### 改动: 无 (NOP。30min cc2 主链 109/109=100.0% SR 零错误零 fallback, buffer 全 attempt-1
### 直 flush 秒回。唯一 1× zombie_empty_completion (502) 归属 hermes (peer caller), JOIN 复核 caller=hermes
### 专属。k0/k3 RD (fid 52e1ddb6) + k3 empty_200 量小一次性 distributed transient 与上轮基本持平
### 未上升, 无 multi-key 连续复发, 非配置漂移。cc2 范围无新签名 → 不改码)

### 依据 (实测 DB 2026-08-07 22:45 CST + 实时复核 + /health)

- **30min nv_requests (cc4101-primary)**: status 仅 200 × **109** = 100.0% SR, 0 错误
  (较 R1104 的 107 略升, 全 200)。实时复核 `caller='cc4101-primary'` = `200|109`。
- **30min 全量非-200 归属**: 唯一 1× zombie_empty_completion (502) 全部 caller=**hermes** (peer)。
  实时复核 `caller|status|count` = `hermes|502|1` (cc4101-primary 0) —— JOIN 归属铁证 (记忆
  bad-fid 52e1ddb6 + bad-fid-52e1ddb6-leaks 判归属法)。
- **fallback**: 0% (109 total, fallback_triggered=0, 全走 primary)。
- **nv_tier_attempts 30min**: tier=dsv4f0731_nv, 5 key 基本全 `pexec_success` (fid 281478d0);
  仅 fid **52e1ddb6** (历史记忆坏 fid — 越界容器 40666 hermes 线泄漏源) 的 k0 1× + k3 2×
  `NVCFPexecRemoteDisconnected` + k3 1× `empty_200` 一次性 distributed transient 单请求 buffer
  自愈。量 (总 4x 含 empty_200) 与 R1104 **基本持平未上升**, 零 buffer_exhausted, 无 multi-key 连续复发。
- **buffer 日志**: 全 `attempt=1/5` 直 flush 秒回 (req=112487c4 elapsed=5s, req=be834acc
  elapsed=14s, req=e23d94d6 elapsed=6s, req=de9a39cb elapsed=8s), verdict 全 success_tool_call/
  success_text, 零重试零级联零 buffer_exhausted。
- **容器 /health 2026-08-07 22:45 CST**: 40006 nv_gw http 200, 4101 cc4101 http 200 (实时复核
  nv_gw:200, cc4101:200)。docker ps: nv_gw Up 19h, cc4101 Up 19h。

### 本轮数据

| 指标 | 值 | 状态 |
|---|---|---|
| cc2 主链 (40006) 30min | cc4101-primary **109/109 = 100.0% SR, 0 bad** | ✅ 全绿 |
| cc2 专属错误分类 | (cc2 专属 0 rows) 零错误 | ✅ |
| 非-200 归属 | 1× zombie_empty_completion (502), caller=hermes (peer) | ✅ peer 归属 |
| fallback 触发率 | 0% (109 total, fb=0, 全走 primary) | ✅ |
| per-key tier 错误 | 基本全 pexec_success; 仅 k0 1× + k3 2× RD + k3 1× empty_200 一次性 transient 持平, 无 multi-key 连续复发 | ✅ |
| buffer | 全 attempt-1 直 flush (5-14s), 零重试零级联零 buffer_exhausted | ✅ |
| container /health | nv_gw 200, cc4101 200 (Up 19h/19h) | ✅ |

## 下一步
- 延续 NOP。cc2 主链连续多轮 (R1096-R1105) 100% SR + zero fallback, 无参数可调。
- **k0/k3 RD** (fid 52e1ddb6) + **k3 empty_200**: 量小 (总 4x, 均单请求, 与上轮基本持平未上升),
  一次性 distributed transient, 单请求 buffer 自愈, 与历史记忆模式一致 (泄漏源=越界容器 40666
  hermes 线, 宿主分离)。无 multi-key 连续复发, 不构成配置漂移。仅当 RD/empty_200 在多 key **连续
  复发** (多个独立请求多 key 持续失败) 才查链路/mihomo 线路。
- **hermes 1× zombie_empty_completion** (peer) 持续关注, 归属 peer 非 cc2 不改动。
- 若 zombie_empty_completion 中出现 caller=cc4101-primary (c.parent) 才进 cc2 指标。

## 参数快照 (未动, 同 R1104)
- 本轮零改动。nv_gw env 复核: NV_GLM52_MODE_CHAIN=pexec_us_rr, NVU_DISABLE_MS_FALLBACK=0,
  UPSTREAM_TIMEOUT=90, NVU_BUFFER_CALLERS=cc4101-primary,openclaw2, NVU_CALLER_KEY_MAP=hermes:2;openclaw:3;opencode:4,
  KEY_FID_BIND=0:0;1:0;2:0;3:0;4:0, NVU_BUFFER_MAX_RETRIES=5 (90s×5=450s)。
- cc4101: PRIMARY_UPSTREAM_MODEL=dsv4f0731_nv, FALLBACK_UPSTREAM_MODEL=glm5_2_ms,
  PRIMARY_UPSTREAM_URL=http://nv_gw:40006/v1/messages, CC4101_STREAM_TOTAL_DEADLINE_S=470,
  PRIMARY_HEADER_TIMEOUT=400, FALLBACK_UPSTREAM_URL=http://ms_gw:40007/v1/chat/completions。