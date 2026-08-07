# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: **R1148 (恢复期 NOP/不改码 — 30min 主链 95.8% SR (113/118), 6× 502
> (all_tiers_exhausted 5 + buffer_exhausted 1) 是一段瞬时过境事件已自愈: fid 281478d0-f307
> (dsv4f0731_nv 现主 fid) 被 NVCF 瞬时标 DEGRADED 1× (400 "DEGRADED function cannot be invoked") +
> NV-KEYMGR RemoteDisconnected 横扫全 5 key (k1-k5) ~15min 风暴, 25 次 all-5-key chain-fail;
> NV-TIER-FAIL 全程 429=0 empty200=0 → 非 KeyManager/cooldown 根因是 egress 传输层瞬时抖动,
> buffer 高峰尝试 2-3 次自愈 (b3abed35 attempt-3 成功), 过尽后全 attempt-1 direct flush;
> 最新 5min 实查 200|16 = 0 非-200 = 100% SR, 降级带完全过境; fallback 未走; 无码可改)**
> 主链 fid 变迁: 现 pexec 实际走 **281478d0-f307** (87× pexec_success), 旧 fid **52e1ddb6** 仅剩尾误
>   (4× RD + 1× 500_nv_error), 主指纹已切到 281478d0-f307
> 错误分类 (surface, 30min): all_tiers_exhausted × 5 + buffer_exhausted × 1 (6 req, avg 219662ms) — 风暴带产物
> 根因: **瞬时 DEGRADED-fid + 全 5 key egress RemoteDisconnected 风暴** (01:47-02:05 CST),
>   非配置回归 (429=0 排除 key-cooldown), 已自愈
> 最新 5min: **cc2-primary 200|16 = 0 非-200, 100% SR**
> 容器 (实查): nv_gw 40006 ok, dsv4p_nv40066 40066 ok, 稳定未重启
> 上轮: R1147 (NOP, 主链零表面错误 100% SR)

## 本轮 (R1148) 改动 + 依据 + 验证

### 改动: 无 (恢复期 NOP。30min 6× 502 为瞬时 DEGRADED-fid (281478d0-f307 被 NVCF 标 DEGRADED 400) +
### 全 5 key RemoteDisconnected 过境风暴 (NV-TIER-FAIL 全程 429=0 empty200=0 = 非 key-cooldown/非配置根因) 的
### 产物, buffer 高峰 attempt-2/3 自愈 (b3abed35 成功), 已完全过境。最新 5min 200|16 = 100% SR = 0 错。
### 无码可改 → NOP)

### 依据 (本 session 实查 2026-08-08)

- **30min cc2-primary (实查)**: 200|113 + 502|6 (avg_dur 219662ms) = 95.8% SR。6 个失败 id 分散在
  17:47-18:02 UTC, 持续 ~15min 降级带 (非单 burst)。
- **错误分类 (surface, 实查)**: `all_tiers_exhausted` × 5 + `buffer_exhausted` × 1。
- **根因 (nv_gw 日志实查)**: `01:47:54 fid=281478d0-f307 resp=400 "DEGRADED function cannot be invoked"`
  → tier DEGRADED cooldown 60s (3× DEGRADED 事件); `NV-KEYMGR transport_err RemoteDisconnected` 横扫
  k1-k5 (7901/7894/7897/7896/7899 全掉连) 01:46→02:05 + 1× SSLEOFError; 25× `all 5 keys + modes exhausted`。
- **非 key-cooldown**: 全部 `NV-TIER-FAIL` 均 `429=0, empty200=0` (other=2~4, timeout ≤1) →
  **egress 传输层瞬时失败 + 瞬时 fid DEGRADED**, 非 KeyManager/配置根因。
- **buffer 自愈**: 风暴期 b3abed35 尝试 attempt-1/2 失败 → attempt-3 success_tool_call (93786ms, 1602b);
  02:05 后全 `attempt=1 → success direct flush` (5-13s/req), 无 exhaust/无 WAIT。
- **最新 5min (实查)**: cc2-primary 200|16 = **0 非-200, 100% SR** — 降级带已过境。
- **主链 fid 变迁**: 现 pexec 走 **281478d0-f307** (87× pexec_success), 旧 fid **52e1ddb6** (上轮 STATE 记主用)
  仅剩 4× RemoteDisconnected + 1× 500_nv_error 尾误; nv_gw host env fid 基线仍 NVCF_GLM52_FUNCTION_ID=b1b22d03
  (glm5_2_nv), dsv4f0731_nv 走 281478d0-f307。

### 本轮数据

| 指标 | 值 | 状态 |
|---|---|---|
| cc2 主链 (40006) 30min | 95.8% SR (200|113 + 502|6) | ⚠️ 风暴带 |
| 最新 5min SR | **100% (200|16 = 0 非-200)** | ✅ 已自愈 |
| surface 错误 | all_tiers_exhausted 5 + buffer_exhausted 1 | 风暴带产物 |
| 根因 | DEGRADED-fid 281478d0-f307 + 全 5 key RemoteDisconnected (429=0) | 瞬时, 已过境 |
| fallback | 30min f\|119, 未走 ms_gw | ✅ |
| buffer | 风暴期 attempt-2/3 自愈, 过后全 attempt-1 direct flush | ✅ 自愈生效 |
| container | nv_gw 40006 ok, dsv4p_nv40066 40066 ok | ✅ |

## 参数快照 (nv_gw + cc4101, 注入)

- **nv_gw**: UPSTREAM_TIMEOUT=90, TIER_TIMEOUT_BUDGET_S=180, NVU_BUFFER_MAX_RETRIES=5 (stairs 90×5=450s),
  NVU_DISABLE_MS_FALLBACK=0, NVU_FORCE_STREAM_UPGRADE=0, NVU_PEER_FB_SKIP_MODELS=glm5_2_nv,dsv4p_nv,
  KEY_COOLDOWN_S=30, NV_INTEGRATE_KEY_COOLDOWN_S=90, TIER_COOLDOWN_S=180, MIN_OUTBOUND_INTERVAL_S=10,
  NVU_BUFFER_CALLERS=cc4101-primary,openclaw2, NVU_CALLER_KEY_MAP=hermes:2;openclaw:3;opencode:4。
- **cc4101**: PRIMARY_UPSTREAM_MODEL=dsv4f0731_nv, PRIMARY_UPSTREAM_URL=http://nv_gw:40006/v1/messages,
  FALLBACK_UPSTREAM_MODEL=glm5_2_ms, FALLBACK_UPSTREAM_URL=http://ms_gw:40007/v1/chat/completions,
  CC4101_STREAM_TOTAL_DEADLINE_S=470, PRIMARY_HEADER_TIMEOUT=400, CC4101_PRIMARY_FAIL_THRESHOLD=3,
  CC4101_PRIMARY_SKIP_S=30, UPSTREAM_TIMEOUT=130, UPSTREAM_IDLE_TIMEOUT=150。
- **nv_gw 主链 fid**: cc4101-primary 走 dsv4f0731_nv → 现主 fid **281478d0-f307** (87× 成功; R1147 记 52e1ddb6
  已切换), 瞬时 DEGRADED 标记过遇后恢复健康。

## 下一步

- **NOP 巡检收尾**。本轮记录为一次自愈的瞬时 DEGRADED-fid + egress 风暴, 无码可改。
- **仅当以下复发且未自愈才改码**:
  (1) 6×/30min 级 all_tiers_exhausted **连续两轮**出现且非单窗口 → 查 mihomo 7901/7894/7897/7896/7899 线路质量;
  (2) `DEGRADED function cannot be invoked` 对 281478d0-f307 **持续复发** → 若固发考虑换 fid (先拉 per-key fid 分布铁证);
  (3) 风暴期内 buffer 无法 attempt 内自愈 (净 502 持续) → 才考虑 k0-k4 多 fid 冗余绑定。
- 注: cc4101 FALLBACK_UPSTREAM_URL 仍指 ms_gw:40007 (历史残留), 但 fallback=0% 从未走, 铁律 4 不主动改。