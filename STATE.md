# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: **R1205 (NOP 巡检 — 30min 窗含 ~5min 瞬时全-key SSL egress blip
> (06:43-06:47 CST / 22:43-22:47 UTC, SSLEOFError 全 5 key 同时抖),
> 撞上 2 请求 → 2× buffer_exhausted (SR 97.1%); blip 自愈, 恢复后窗口 22:47-22:53 全 200 100%;
> 无配置回归, 近 50 轮内首次同窗双 buffer_exhausted, 均系瞬时 egress blip → NOP 不改码)**
> 主链 fid: **281478d0-f307** 稳定, dsv4f0731_nv 单模式
> 错误分类 (活查, 30min): cc2-primary buffer_exhausted ×2 (avg 68950ms)
> 根因: ~5min 瞬时全-key egress SSL 抖动 (mihomo 5 US IP 同时 SSLEOFError), 撞上 2 请求; 防御链
> (buffer 5-attempt + AKE fail-fast + ms 兜底) 按设计工作, blip 后静稳 (同 ssleof-error memory), 非回归
> 最新 30min (尾部净稳): blip 后 (22:47-22:53 UTC) cc2-primary 19/19 全 200 = 100% SR
> fallback: **0%**

## 本轮 (R1205) 改动 + 依据 + 验证

### 改动: 无 (NOP 巡检轮。2× buffer_exhausted 系 ~5min 瞬时全-key SSL egress blip, 已自愈, 无改码条件)

### 依据 (活查 30min + nv_gw 日志时序, 2026-08-08 07:00 CST)

- **活查 30min cc2-primary (nv_requests)**: `200|66`, `502|2` → SR=97.1% (66/68), 0 fallback。
- **错误分类**: `buffer_exhausted ×2` (avg 68950ms), req=76fb2449 / 7562e67f。
- **根因 (nv_gw 日志时序铁证)**: 06:43-06:47 CST (22:43-22:47 UTC) ~5min 全-key egress
  SSL 抖动脉冲 (`SSLEOFError: UNEXPECTED_EOF_WHILE_READING`, 06:47:13-38 连环 k4→k5→k1→k2→k3→k4,
  全 5 key 各 5-10s), 撞上 2 请求 → buffer 5-attempt + AKE fail-fast + ms 兜底全败 (同一 egress blip)。
  同 [[ssleof-error-transient-egress-blip]] "瞬时多 key egress 抖动 NOP 自愈" 模式, **非配置回归**。
- **防御链按设计工作 (未加码已生效)**: buffer 5-attempt 跨 key 轮转 ✓, AKE fail-fast 连续 3 次
  all_keys_exhausted 跳过 WaitQueue (省 ~120s) ✓, ms_gw fallback 尝试 (同一 blip 下也败, 非走 ms 成功链) ✓。
- **恢复后净稳**: 06:47 后无 SSL cycle; 22:47-22:53 UTC 窗口 cc2-primary 19/19 全 200 = 100% SR;
  06:49:59 起全 buffer attempt=1 命中 (elapsed 5-23s)。
- **容器健康**: nv_gw /health `{"status":"ok", nv_num_keys=5}` (+ 主链 dsv4f0731_nv, fid 281478d0-f307) ok,
  cc4101 ok, dsv4p_nv40066 ok。

### 验证
2× buffer_exhausted 均系瞬时全-key SSL egress blip (日志时序铁证), blip 后窗口 100% SR 无复发;
防御链 (buffer + AKE fail-fast + ms 兜底) 全部按设计工作; fallback 0%; 容器 health ok;
链路静稳确认, 无改码条件。

## 参数快照 (nv_gw + cc4101, 本轮注入无变更)

- **nv_gw**: UPSTREAM_TIMEOUT=90, TIER_TIMEOUT_BUDGET_S=180, NVU_BUFFER_MAX_RETRIES=5
  (stairs 90×5=450s), NVU_DISABLE_MS_FALLBACK=0, NVU_FORCE_STREAM_UPGRADE=0,
  NVU_PEER_FB_SKIP_MODELS=glm5_2_nv,dsv4p_nv, KEY_COOLDOWN_S=30, INTEGRATE_KEY_COOLDOWN_S=90,
  TIER_COOLDOWN_S=180, MIN_OUTBOUND_INTERVAL_S=10, NVU_BUFFER_CALLERS=cc4101-primary,openclaw2,
  NV_INTEGRATE_KEY_COOLDOWN_S=90, NVU_FORCE_STREAM_UPGRADE_TIMEOUT=150, NVU_FORCE_STREAM_UPGRADE=0
  (全 key bind fid index 0=281478d0-f307, dsv4f0731_nv 单模式)。
- **cc4101**: PRIMARY_UPSTREAM_MODEL=dsv4f0731_nv, PRIMARY_UPSTREAM_URL=http://nv_gw:40006/v1/messages,
  FALLBACK_UPSTREAM_MODEL=glm5_2_ms, FALLBACK_UPSTREAM_URL=http://ms_gw:40007/v1/chat/completions,
  CC4101_STREAM_TOTAL_DEADLINE_S=470, PRIMARY_HEADER_TIMEOUT=400, PRIMARY_FAIL_THRESHOLD=3,
  PRIMARY_SKIP_S=30, UPSTREAM_TIMEOUT=130, UPSTREAM_IDLE_TIMEOUT=150。

## 上轮
R1204 (NOP — cc2-primary 90/90 全 200 = 100% SR + 3× 孤立 k1/k2/k3 RemoteDisconnected 瞬时自愈,
链路静稳跨四十九轮无异常) → R1205 (共享仓库): 本轮首现同窗 2× buffer_exhausted,
根因为 ~5min 瞬时全-key SSL egress blip (非 k1/k2/k3 单-key 抖, 是 5 线同抖), blip 撞上 2 请求成错;
恢复后窗口 100% SR 无复发。防御链 (buffer + AKE fail-fast + ms 兜底) 按设计工作, 非回归。

## 下一步
维持静稳观察。**核心监控: 瞬时全-key SSL egress blip 是否再现及复发间隔**。
本轮 (R1205) 是近 50 轮内首次同窗同时出现 2× buffer_exhausted, 均系 ~5min 全 5 key
SSLEOFError 同时抖动脉冲 (06:43-06:47 CST), 撞上 2 请求。已并入 `ssleof-error-transient-egress-blip`
记忆跟踪 (从单-key 抖扩展到全-key 同抖场景)。
- 若此类**全 5 key 同时 SSL 抖动**复发间隔明显缩短 / 单个 blip 内失败请求 > 2,
  才查 mihomo 5 US 线路 (egress_ip 分布) 与宿主机链路质量。
- 孤立瞬时 (单/双 key, 自愈不复) 仍 NOP 自愈即可。
- 主键: 最大化单位时间 NV 成功数, 当前链路整体 SR 高 (blip 后窗口 100%)。