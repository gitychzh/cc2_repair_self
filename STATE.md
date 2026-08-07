# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: **R1152 (恢复闭环 NOP/不改码 — R1148/49 那场瞬时风暴彻底过境: 65min 全量 cc2 6× 502 逐点匹配
> 风暴带 17:47-18:02 UTC, 末次失败 18:02:45, 之后 18:03 起连续 92/92 = 100% SR, 最新 5min 18/18;
> 30min surface 余下 2× 502 (注入时 3× 又 1× 自然滚出) 全落 18:01-18:02 风暴带尾窗; 错误签名与 R1148/49
> 完全一致, 无新类型; 无配置漂移 → NOP 不改码; R1148/49 风暴彻底过境)**
> 主链 fid: **281478d0-f307** 稳定 (全 5 key pexec), 旧 52e1ddb6 已完全消失
> 错误分类 (surface, 30min): all_tiers_exhausted × 2 (全 18:01-18:02 UTC 风暴带尾窗)
> 根因: **R1148 瞬时过境事件的残余尾窗, 已彻底自然滚出**
> 最新 5min: **cc2-primary 200|18 = 0 非-200, 100% SR**
> 风暴后连续: **200|92 = 100% SR** (18:03:00 → 18:29)

## 本轮 (R1152) 改动 + 依据 + 验证

### 改动: 无 (恢复延续 NOP。30min surface 窗口余下 2× 502 全属 R1148/49 风暴带尾窗 (18:01-18:02 UTC),
### 风暴结束后 92/92 = 100% SR, 最新 5min 18/18。无新错误类型、无配置漂移 → NOP 不改码)

### 依据 (live 实查 2026-08-08 02:29 CST)

- **65min cc2 全量失败 (实查)**: 6× 502 时间戳 **17:47 / 17:49 / 17:54 / 17:58 / 18:01 / 18:02 UTC** —
  与 R1149 记录风暴带 (17:47-18:02) 逐点吻合, 铁证风暴**彻底过境**。末次失败 18:02:45, 之后 23min 零失败。
- **风暴后 18:03 起 (实查)**: **92/92 = 100% SR, 0 失败** — 较 R1151 的 74 又延伸, 彻底闭环延续。
- **最新 5min (实查)**: 18/18 = **100% SR**。
- **30min surface**: 注入时计 3×, 实查已 2× (18:01 / 18:02, 第 3× 已自然滚出) — 全在风暴带尾窗。
- **错误分类 (surface)**: `all_tiers_exhausted` × 2 — 与 R1148/49 同签名, **无新类型**。
- **Tier 层 (实查)**: 主链 dsv4f0731_nv 全 5 key → **281478d0-f307**, 91× `pexec_success`; 错误仅
  `NVCFPexecRemoteDisconnected` × 1, **429=0, empty200=0** → 非 key-cooldown/非空响应根因。
- **nv_gw 日志 (实查)**: 全 `attempt=1/5 → success → direct flush`, 干净稳态, 无 WAIT/DEGRADED/exhaust。
- **fallback**: f|192, ms_gw 未走。✅
- **容器**: nv_gw 40006 ok (28h), dsv4p_nv40066 40066 ok (3d), cc4101 4101 ok (23h), 全稳定未重启。

### 验证
65min 全量 502 逐点匹配风暴带; 风暴后连续 92× 200 = 100% SR; 最新 5min 18/18; buffer 全 attempt-1
direct flush; tier 无 429/empty; fid 稳定; 容器全稳定。下轮 2× 502 (18:01/18:02) 滚出 30min 窗口后
整窗 SR 应稳回 100% → R1148/49 风暴彻底闭环。

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
R1151 (恢复延续 NOP — 风暴带尾窗基本滚出, 窗口内 3×, 风暴后 74/74=100% SR)。
R1152 确认尾窗再滚出 1× (窗口内剩 2×), 65min 全量 502 逐点匹配风暴带, 风暴后 streak 延伸至 92/92 → 彻底过境。

## 下一步
维持静稳观察。下轮 2× 502 (18:01/18:02) 将全部滚出 30min 窗口, 整窗 SR 应稳回 100%。
若再出现全 5 key 连败或新错误类型, 再深挖 egress 线路 (mihomo) / KeyManager cooldown。