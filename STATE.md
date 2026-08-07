# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: **R1149 (恢复期 NOP/不改码 — 30min 整窗主链 87.5% SR (42/48) 仍含 R1148 那场风暴带的
> 6 个 502 尾窗 (all_tiers_exhausted 5 + buffer_exhausted 1, 全落在 17:47-18:02 UTC), 但降级带
> 结束后 18:03→18:14 连续 28+ 个 200, 最新 5min 实查 20/20 = 100% SR = 0 错; 错误签名与 R1148
> 完全相同 (无新类型), tier 错误仅 2× NVCFPexecRemoteDisconnected (瞬时 egress), 429=0/empty200=0
> = 非 cooldown/非配置根因; buffer 全 attempt-1 direct flush 干净稳态; 主 fid 281478d0-f307 稳定,
> 旧 52e1ddb6 仅 2 尾误; fallback 未走; 无码可改)**
> 主链 fid 变迁: 现 pexec 实际走 **281478d0-f307** (37× nvcf_pexec, 全 5 key), 旧 fid **52e1ddb6** 仅剩
>   2× 尾误 (k0/k1 各 1) — 与 R1148 "主指纹已切 281478d0-f307" 一致
> 错误分类 (surface, 30min): all_tiers_exhausted × 5 + buffer_exhausted × 1 (6 req) — R1148 风暴带尾窗,
>   非新事件
> 根因: **R1148 瞬时 DEGRADED-fid + 全 5 key egress RemoteDisconnected 风暴的过境尾窗**, 已完全自愈
> 最新 5min: **cc2-primary 200|20 = 0 非-200, 100% SR** (末次失败 18:02, 之后全 200)

## 本轮 (R1149) 改动 + 依据 + 验证

### 改动: 无 (恢复期 NOP。30min 整窗的 6× 502 与 R1148 为同一场风暴 (17:47-18:02 UTC) 的尾窗,
### 降级带结束后的所有请求 100% SR, 最新 5min 20/20。无新错误类型、无配置漂移 → NOP 不改码)

### 依据 (live 实查 2026-08-08 02:14 CST)

- **30min cc2-primary (实查)**: 48 total = 42|200 + 6|502 = 87.5% 整窗 SR。6 个失败全部落在
  **17:47-18:02 UTC** (末次 9731043f @18:02), 之后 18:03→18:14 连续 28+ 个 200。
- **最新 5min (实查)**: 20/20 = **100% SR** — R1148 风暴带完全过境。
- **错误分类 (surface)**: `all_tiers_exhausted` × 5 + `buffer_exhausted` × 1, avg_dur ~220s — 与 R1148
  完全相同, **无新错误类型**。
- **Tier 层 (实查)**: 主链 dsv4f0731_nv 全 5 key → **281478d0-f307** (37× pexec); 旧 52e1ddb6 仅
  k0/k1 各 1 尾误。错误仅 `NVCFPexecRemoteDisconnected` × 2 (瞬时 egress), **429=0, empty200=0**
  → 排除 key-cooldown/integrate 空响应根因。
- **nv_gw 日志**: 无 WAIT/DEGRADED/buffer exhaust 新事件; 全 `attempt=1/5 → success_tool_call →
  direct flush` (2-14s/req, 最大 33551b/13306ms) — 干净稳态签名。
- **fallback**: cc_requests 30min nb=0/1783 — ms_gw 未走。✅
- **容器**: nv_gw 40006 ok, dsv4p_nv40066 40066 ok, 稳定未重启。

### 验证
同上 — 最新 5min 20/20 = 100% SR, nv_gw buffer 全 attempt-1 direct flush, 无任何 WAIT/exhaust/DEGRADED。
降级带已过, 恢复闭环在望。

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
R1148 (恢复期 NOP — 30min 主链 95.8% SR (113/118) 为瞬时 DEGRADED-fid 281478d0-f307 + 全 5 key
egress RemoteDisconnected 风暴已自愈, 429=0 非 cooldown, 最新 5min 100% SR)。
R1149 与其同源: 30min 整窗仍见该风暴尾窗 6× 502, 但降级带已过, 最新窗口 100% SR, 无码可改。

## 下一步
维持 R1148 结论: 该瞬时 (DEGRADED-fid + egress 风暴) 为一过境事件, 无参数可调、无码可改。
继续静稳观察; 若 30min 整窗 SR 回升 97%+ (尾窗滚出窗口) 即告恢复闭环; 若再出现全 5 key 连败或新错误类型再深挖。