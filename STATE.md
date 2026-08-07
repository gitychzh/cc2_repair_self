# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: **R1208 (NOP — 窗口内唯一 502(7f34c956)=R1206 残留, 新增失败=0;
> 表面 SR 98.8% 实则无净新增, fallback 0%, 防御链按设计工作)**
> 主链 fid: **281478d0-f307** 稳定, dsv4f0731_nv 单模式
> 错误分类 (活查 30min, 22:52-23:22 UTC): cc2-primary buffer_exhausted ×1 (7f34c956,
> created 23:06:49 = R1206 新失败残留, 非本轮新发生; 7562e67f(R1205 blip) 已滑出窗口)
> 根因: 无新根因; 残余来自 R1206 跨 k1-k3 连续 Remote-end-closed
> 最新窗口: 30min cc2-primary 200|82/502|1, cc_requests 84/84 SR 100%, fallback 0%
> 容器: nv_gw /health ok (5 keys + dsv4f0731_nv fid 281478d0-f307), cc4101 ok, dsv4p ok

## 本轮 (R1208) 改动 + 依据 + 验证

### 改动: 无 (NOP 巡检轮。mihomo 升级监控条件未实质触发, 不改码不查 mihomo)

### 依据 (活查 30min nv_requests + nv_tier_attempts, 2026-08-08 07:22 CST)

- **30min cc2-primary (nv_requests)**: `200|82`, `502|1` (buffer_exhausted),
  表面 SR=98.8% (82/83)。cc_requests 84/84 SR=**100%**, **fallback=0%**。
  dsv4f0731_nv 全量 (含 hermes 53) 稳定。
- **唯一 502 归属 (滚动窗口边界 re-sample, 无新增)**:
  - `7f34c956`(23:06:49 UTC, dur 167010) = **R1206 新失败残留重复计入** (R1206 已完整分析
    k1/k2/k3 连续 Remote-end-closed)。request_id 与上轮记录逐字一致, 非本轮新发生。
  - `7562e67f`(R1205 blip, created 22:47) **已随滑窗滑出本窗口**, 印证滚动边界 re-sample 预期。
  - 本窗口 502 集合 {7f34c956} ⊆ 上轮失败集合 {7562e67f, 7f34c956} ⇒ **新增失败 = ∅**。
- **attempt 级瞬时抖动全自愈**: k0 RemoteDisconnected×1+Timeout×1, k1 RemoteDisconnected×2,
  k3 Timeout×1, k4 Timeout×1, 全被 attempt-2/3 重试吸收 → status 最终 200, 无 out-window 失败。
- **mihomo 升级监控条件 (R1206/R1207 收紧) 判定**: 表面 SR<99% + buffer_exhausted 看似触发,
  但归属核实证明唯一 502 为上轮残留、本轮新增=0 → 不满足"真实新失败 + SR<99%"实质条件,
  mihomo 隧道检查延后。触发条件: **R1209 出现真实新失败 + SR<99%** 才执行。
- **容器健康**: nv_gw /health ok (5 keys + dsv4f0731_nv, fid 281478d0-f307), cc4101 ok
  (primary=dsv4f0731_nv), dsv4p ok。无重配置迹象, 参数与 R1206/1207 一致 → 非配置回归。

### 验证
表面 1× buffer_exhausted (7f34c956) 经 request_id 逐字 JOIN 为上轮 R1206 已计残留, 本窗口
最终 502 集合 ⊆ 上轮集合, 新增失败 = 0; 全部 attempt 级失败被重试自愈; cc_requests SR 100%、
fallback 0%; 容器 health ok、参数无漂移 → 无改码条件。fallback 0%。

## 参数快照 (nv_gw + cc4101, 与 R1206/R1207 一致)

- **nv_gw**: UPSTREAM_TIMEOUT=90, TIER_TIMEOUT_BUDGET_S=180, NVU_BUFFER_MAX_RETRIES=5
  (stairs 90×5=450s), NVU_DISABLE_MS_FALLBACK=0, NVU_FORCE_STREAM_UPGRADE=0,
  KEY_COOLDOWN_S=30, INTEGRATE_KEY_COOLDOWN_S=90, TIER_COOLDOWN_S=180, MIN_OUTBOUND_INTERVAL_S=10,
  NVU_BUFFER_CALLERS=cc4101-primary,openclaw2, NV_INTEGRATE_KEY_COOLDOWN_S=90,
  NVU_FORCE_STREAM_UPGRADE_TIMEOUT=150 (全 key bind fid index 0=281478d0-f307, dsv4f0731_nv 单模式)。
- **cc4101**: PRIMARY_UPSTREAM_MODEL=dsv4f0731_nv, PRIMARY_UPSTREAM_URL=http://nv_gw:40006/v1/messages,
  FALLBACK_UPSTREAM_MODEL=glm5_2_ms, FALLBACK_UPSTREAM_URL=http://ms_gw:40007/v1/chat/completions,
  CC4101_STREAM_TOTAL_DEADLINE_S=470, PRIMARY_HEADER_TIMEOUT=400, PRIMARY_FAIL_THRESHOLD=3,
  PRIMARY_SKIP_S=30, UPSTREAM_TIMEOUT=130, UPSTREAM_IDLE_TIMEOUT=150。

## 上轮
R1207 (NOP — 表面 2× buffer_exhausted 全为上轮重复, 实际新增=0) → R1208: 窗口推进, 7562e67f
滑出, 仅剩 7f34c956 (R1206 残留) 在窗, 新增仍为 0。SSLEOFError/Remote-end-closed 瞬时 egress
抖动未产生净新增, 非配置回归。

## 下一步
维持静稳观察。**mihomo 升级监控触发条件 (R1206/R1207 收紧)**: 若 **R1209 出现真实新失败
(非上轮 request_id) + SR<99%** → 拉 mihomo 隧道线路质量 (各 egress_ip 失败率、隧道状态、
`mihomo get proxies`), 评估是否调整 key→proxy 绑定。7f34c956 随下一滑窗将自然滑出, 预期
R1209 表面 SR 回到 100%。单次瞬时自愈 / 上轮残留重计一律 NOP 自愈。
- 主键: 最大化单位时间 NV 成功数; 存在历史 3h 100% SR 基线, 防御链工作正常。