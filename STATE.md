# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: **R1150 (恢复闭环 NOP/不改码 — R1148/49 那场瞬时 (DEGRADED-fid + egress RemoteDisconnected)
> 风暴的尾窗已完全滚出活跃窗口: 风暴段 17:47-18:02 UTC 结束后所有请求 55/55 = 100% SR, 最新 5min
> 15/15 = 100% SR; 30min surface 仍计的 4× 502 (all_tiers_exhausted) 全落 17:54-18:02 = 风暴尾窗,
> 下窗口滚出即正式闭环; 错误签名与 R1148/49 完全一致, 无新类型; 无配置漂移 → 无码可改)**
> 主链 fid: **281478d0-f307** 稳定 (全 5 key pexec), 旧 52e1ddb6 已完全消失
> 错误分类 (surface, 30min): all_tiers_exhausted × 4 (全 17:54-18:02 UTC 风暴尾窗)
> 根因: **R1148 瞬时过境事件的残余尾窗, 已 100% 自愈**
> 最新 5min: **cc2-primary 200|15 = 0 非-200, 100% SR**
> 风暴后连续: **200|55 = 100% SR** (18:03:42 → 18:20:05)

## 本轮 (R1150) 改动 + 依据 + 验证

### 改动: 无 (恢复闭环 NOP。30min surface 窗口的 4× 502 全属 R1148/49 风暴带尾窗 (17:54-18:02 UTC),
### 风暴结束后 55/55 = 100% SR, 最新 5min 15/15。无新错误类型、无配置漂移 → NOP 不改码)

### 依据 (live 实查 2026-08-08 02:18 CST)

- **30min cc2-primary (实查)**: 58 total = 54|200 + 4|502 = 93.1% 整窗 SR。4 个失败全落 **17:54:11-18:02:45 UTC**
  = R1149 记录风暴带 (17:47-18:02) 的**尾窗**。末次失败 18:02:45, 之后 18:03:42 → 18:20:05 连续 55 个 200。
- **风暴后 18:03 起 (实查)**: **55/55 = 100% SR, 0 失败** — R1148/49 风暴完全过境, 恢复闭环。
- **最新 5min (实查)**: 15/15 = **100% SR**。
- **错误分类 (surface)**: `all_tiers_exhausted` × 4, avg_dur ~237s — 与 R1148/49 同签名, **无新类型**。
- **Tier 层 (实查)**: 主链 dsv4f0731_nv 全 5 key → **281478d0-f307**, 全部 `pexec_success`; 错误仅
  `NVCFPexecRemoteDisconnected` × 2 (k0/k1), **429=0, empty200=0** → 非 key-cooldown/非空响应根因。
- **nv_gw 日志 (实查)**: 全 `attempt=1/5 → success_tool_call → direct flush` (7-35s/req)。唯一一次
  attempt-1 `execute_failed` (req=9f06e4d9, k4) → 5s backoff → **attempt-2 success (35053ms)** = 已知
  k 瞬时 egress 自愈签名, 非回归。无 WAIT/DEGRADED/exhaust。
- **fallback**: cc_requests nb=0 — ms_gw 未走。✅
- **容器**: nv_gw 40006 ok (23h), dsv4p_nv40066 40066 ok (3d), cc4101 4101 ok (22h), 全稳定未重启。

### 验证
风暴后连续 55 个 200 = 100% SR; 最新 5min 15/15 = 100% SR; buffer 全 attempt-1 direct flush, 唯一瞬时
execute_failed attempt-2 自愈; 容器全稳定。下窗口 4× 502 滚出后整窗 SR 将稳回 97%+ → 正式闭环。

## 参数快照 (nv_gw + cc4101, 注入)

- **nv_gw**: UPSTREAM_TIMEOUT=90, TIER_TIMEOUT_BUDGET_S=180, NVU_BUFFER_MAX_RETRIES=5 (stairs 90×5=450s),
  NVU_DISABLE_MS_FALLBACK=0, NVU_FORCE_STREAM_UPGRADE=0, NVU_PEER_FB_SKIP_MODELS=glm5_2_nv,dsv4p_nv,
  KEY_COOLDOWN_S=30, NV_INTEGRATE_KEY_COOLDOWN_S=90, TIER_COOLDOWN_S=180, MIN_OUTBOUND_INTERVAL_S=10,
  NVU_BUFFER_CALLERS=cc4101-primary,openclaw2, NVU_CALLER_KEY_MAP=hermes:2;openclaw:3;opencode:4
  (NV_GLM52_MODE_CHAIN=pexec_us_rr, 全 5 key bind fid index 0=281478d0-f307)。
- **cc4101**: PRIMARY_UPSTREAM_MODEL=dsv4f0731_nv, PRIMARY_UPSTREAM_URL=http://nv_gw:40006/v1/messages,
  FALLBACK_UPSTREAM_MODEL=glm5_2_ms, FALLBACK_UPSTREAM_URL=http://ms_gw:40007/v1/chat/completions,
  CC4101_STREAM_TOTAL_DEADLINE_S=470, PRIMARY_HEADER_TIMEOUT=400, PRIMARY_FAIL_THRESHOLD=3,
  PRIMARY_SKIP_S=30, UPSTREAM_TIMEOUT=130, UPSTREAM_IDLE_TIMEOUT=150。

## 上轮
R1149 (恢复期 NOP — 30min 整窗 87.5% SR 仍含 R1148 风暴尾窗 6× 502, 降级带后 28+ 全 200, 最新 5min
20/20=100%)。R1150 确认该尾窗已完全滚入风暴带之外: 18:03 起 55/55=100%, 恢复闭环。

## 下一步
维持静稳观察。下轮若 30min 整窗 SR ≥ 97% (4× 502 滚出 30min 窗口) 即正式宣告 R1148 风暴闭环。
若再出现全 5 key 连败或新错误类型, 再深挖 egress 线路 (mihomo) / KeyManager cooldown。