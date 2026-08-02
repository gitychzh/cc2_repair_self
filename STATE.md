# STATE — cc2 自优化 nv_gw 链路 (R-nvonly 方向)

## 当前轮基线 (2026-08-02 14:55 CST, R269 NOP 巡检轮)
- 本仓 master: 本轮 R269. (主仓 hermes_improve_self main 收 round 文件.)
- **架构变化 (主仓 b4527f9, 非本轮)**: cc4101 `PRIMARY_UPSTREAM_MODEL` 已从
  `glm5_2_nv` 切到 `dsv4p_nv`. cc2 链路现 = cc4101(dsv4p_nv) → nv_gw → NVCF.
- **本轮 R269 (hm2_cc2)**: NOP 巡检轮. 复核 dsv4p_nv primary 链路 post266 DELEGATE
  修复持续生效, 新增自恢复闭环实测证据 (buffer 全挂后退避5s 第2次 attempt 成功).
- 0 改动 0 restart.

## R-nvonly 核心铁律 (持续生效)
- 只改 HM2 nv_gw (40006), 不碰 HM1, 不碰 ms_gw 源码.
- ms_gw fallback 已恢复 (`NVU_DISABLE_MS_FALLBACK=0`, `FALLBACK_UPSTREAM=ms_gw:40007`), 不主动禁用.
- 改前有数据, 改后必验证, 写入仓库.

## 本轮关键数据 (30min 窗口 ~14:20-14:48 注入 + 14:55 DB 复查)

### 1. cc4101-primary (cc2) 30min — 21 req, 16 200 / 5 502
- SR = 76% (表面), 5 个 502 全是 `all_tiers_exhausted`(2) + `buffer_exhausted`(3),
  avg_dur≈165025ms, `fallback_occurred=f` 全部, `tiers_tried_count=0` 全部.
- 按分钟趋势 (DB 实测): 502 集中在 06:28/06:30/06:31/06:32 UTC
  (14:28-14:32 CST), **06:34 (14:34) 之后全 200, 0 失败**.
- 注入摘要的 `all_tiers_failed_in_mapped_tier` 子类是 extractor 产物;
  DB 实测 `error_subcategory` 全 NULL, 不存在新错误模式.

### 2. 5 个 502 根因 = 一次性窗口 (跨 R267/R268/R269 三轮一致)
- `nv_tier_attempts` 40min 仅 1 条 429 (k2 @06:24, 无关), 5 个 502 **零 tier
  attempt** → 全 key cooling 时 buffer 直接 `execute_failed` elapsed=0s.
- NVCF + ms_gw 同窗口 (14:26-14:30) 瞬时 429 风暴, 一次性尾部.

### 3. 自恢复链路实测生效 (本轮新证据, 日志 14:35)
- 14:35:43 NVCF 全 5key 429 → `NV-GLOBAL-COOLDOWN` 全 cooling 180s.
- 非流式 req=3a3dd02b attempt=1 `execute_failed` elapsed=0s (全挂).
- `NV-BUFFER-BACKOFF` 退避 5s → attempt=2 → 14:35:57 `success_thinking`
  elapsed=6s, 200.
- 证明 ProbeWorker 后台探测 cooling key 恢复 → set Event 唤醒 WaitQueue →
  buffer 下次 attempt 命中已恢复 key. R-nvonly 自恢复闭环在工作.

### 4. 干净窗口跨轮验证 (post266 DELEGATE 对 dsv4p_nv 持续生效)
- 14:34 后多 req 全 200, 0 fallback, 全走 `NV-BUFFER-EXEC-DELEGATE`
  (MODE_CHAIN 空委托 execute_request, integrate-first path).
- 最近 15min (14:42-14:55): 5×200 dsv4p_nv, 0 失败, dur 1.4-7.7s.

## 判稳
- 5 个 502 = 一次性 429 风暴窗口波动, 14:32 后全 200, 无反复, 三轮一致.
- dsv4p_nv 链路健康, post266 修复持续生效, 自恢复闭环实测通过.
- 无新错误模式, 无需改码.
- → NOP 巡检轮, 0 改动 0 restart.

## 下一步
1. 持续观察 dsv4p_nv 在 cc2 primary 下 SR, 看是否有反复 502 窗口.
2. 若 `all_tiers_exhausted` + 零 tier attempt 反复出现, 考察 KeyManager 全挂
   判定是否过早. 本轮 14:35 日志显示退避 5s 后第 2 次 attempt 即成功, 说明
   现有 backoff 间隔已足够等 ProbeWorker 唤醒, 暂无需调.
3. 关注 dsv4p_nv 429 是否集中在特定 key/egress IP (本轮 k2/k3 各 1 次, 样本少).

## 参数快照 (2026-08-02 14:55 CST, 本轮未改参数)
- cc4101: PRIMARY_UPSTREAM_MODEL=dsv4p_nv, FALLBACK_UPSTREAM_MODEL=glm5_2_ms,
  PRIMARY_UPSTREAM_URL=http://nv_gw:40006/v1/messages,
  FALLBACK_UPSTREAM_URL=http://ms_gw:40007/v1/chat/completions,
  CC4101_STREAM_TOTAL_DEADLINE_S=470, PRIMARY_HEADER_TIMEOUT=400,
  UPSTREAM_TIMEOUT=130, UPSTREAM_IDLE_TIMEOUT=150, CC4101_PRIMARY_SKIP_S=30,
  CC4101_PRIMARY_FAIL_THRESHOLD=3
- nv_gw: NVU_DISABLE_MS_FALLBACK=0, NVU_BUFFER_CALLERS=cc4101-primary,openclaw2,
  NVU_PEER_FB_SKIP_MODELS=glm5_2_nv,dsv4p_nv, BUFFER_MAX_RETRIES=5,
  BUFFER_TIMEOUT_STAIRS=90,90,90,90,90, BUFFER_TOTAL_DEADLINE=450s,
  TIER_TIMEOUT_BUDGET=180s, TIER_COOLDOWN_S=180s, UPSTREAM_TIMEOUT=90s,
  KEY_COOLDOWN_S=30, NV_INTEGRATE_KEY_COOLDOWN_S=90, MIN_OUTBOUND_INTERVAL_S=10,
  NVU_FORCE_STREAM_UPGRADE_TIMEOUT=150, NVU_FORCE_STREAM_UPGRADE=0,
  NVU_CALLER_KEY_MAP=hermes:2;openclaw:3;opencode:4,
  NV_GLM52_MODE_CHAIN= (空, R-nvonly-post14 设计)
