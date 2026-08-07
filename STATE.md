# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: **R1153 (NOP — R1148/49 那场瞬时风暴彻底闭环: 30min 整窗 cc4101-primary 104× 200 = 100% SR,
> 0 错误, 0 fallback; surface 错误分类完全为空, 原 R1152 记录的尾窗 2× 502 (18:01/18:02 UTC) 已全部滚出
> 30min 窗口; tier 全 5 key pexec_success 仅 1× 瞬时 NVCFPexecRemoteDisconnected, 429=0 empty=0;
> buffer 全 attempt-1 direct flush 干净稳态 → NOP 不改码)**
> 主链 fid: **281478d0-f307** 稳定 (全 5 key pexec), 旧 52e1ddb6 已完全消失
> 错误分类 (surface, 30min): **(空)** — 零错误
> 根因: R1148/49 瞬时风暴, 尾窗已彻底自然滚出, 整窗干净
> 最新 5min: **cc2-primary 200|104 = 0 非-200, 100% SR**
> fallback: **0/212 = 0%**, ms_gw 未走

## 本轮 (R1153) 改动 + 依据 + 验证

### 改动: 无 (NOP 巡检轮。30min 整窗 cc4101-primary 104× 200 = 100% SR, surface 错误分类为空,
### fallback 0%, tier 仅 1× 瞬时 NVCFPexecRemoteDisconnected, buffer 干净 → 不符改动触发条件, 不改码)

### 依据 (live 实查 2026-08-08 02:33 CST)

- **cc4101-primary per-status (实查)**: `200|104` — **100% SR, 0 非-200**。
- **错误分类 (实查)**: `(0 rows)` — surface 错误**完全为空**, R1152 记录的尾窗 2× 502 已全滚出。
- **全模型 SR (注入)**: dsv4f0731_nv **100%** (212/212, 含 hermes 线)。
- **fallback (注入)**: `f|212 = 0%` — ms_gw 未走。
- **Tier 层 (注入)**: 全 5 key `pexec_success` (k0:22, k1:20, k2:20, k3:22, k4:18);
  仅 `NVCFPexecRemoteDisconnected` × 1 → 瞬时 egress 抖动, NOP 自愈; **429=0, empty=0**。
- **buffer/wait (注入)**: 无日志 — 全 attempt-1 direct flush, 干净稳态。
- **容器 (实查)**: nv_gw 40006 `ok`, cc4101 4101 `ok`, 全稳定未重启。

### 验证
30min 整窗 104× 200 = 100% SR; surface 错误分类空; fallback 0%; tier 无 429/empty; fid 稳定;
容器全健康。R1152 预期的"尾窗滚出后整窗稳回 100%"已如期兑现 → **R1148/49 风暴正式彻底闭环**。

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
R1152 (恢复闭环 NOP — 尾窗 2× 502 @ 18:01/18:02, 风暴后 92/92=100% SR, 65min 全量逐点匹配风暴带)。
R1153 确认整窗 104/104=100% SR, surface 错误分类空 → 尾窗彻底滚出, R1148/49 风暴正式闭环。

## 下一步
维持静稳观察。保持 NOP。若再出现全 5 key 连败或新错误类型, 再深挖 egress 线路 (mihomo)
/ KeyManager cooldown / fid 健康。

## R1148→R1153 全时段事务闭环记录 (供审计)
- R1148 风暴起 (17:47-18:02 UTC), 峰值多 key RemoteDisconnected/all_tiers_exhausted。
- R1149-1150 恢复期, 尾窗逐步滚出, 降级带后连续 200。
- R1151 尾窗基本滚出 (剩 3×)。
- R1152 尾窗剩 2× (18:01/18:02), 风暴后 streak 92/92。
- **R1153 尾窗全滚出, surface 错误分类空, 整窗 104/104=100% SR → 彻底闭环。**