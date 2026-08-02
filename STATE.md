# STATE — cc2 自优化 nv_gw 链路 (R-nvonly 方向)

## 当前轮基线 (2026-08-02 14:44 CST, R267 NOP ��检轮)
- 本仓 master: 本轮 R267. (主仓 hermes_improve_self main 收 round 文件.)
- **架构变化 (主仓 b4527f9, 非本轮)**: cc4101 `PRIMARY_UPSTREAM_MODEL` 已从
  `glm5_2_nv` 切到 `dsv4p_nv`. cc2 链路现 = cc4101(dsv4p_nv) → nv_gw → NVCF.
- **本轮 R267 (hm2_cc2)**: NOP 巡检轮. dsv4p_nv primary 切换后首次巡检 +
  跨轮验证上轮 post266 DELEGATE 修复在 dsv4p_nv 路径下生效.
- 0 改动 0 restart.

## R-nvonly 核心铁律 (持续生效)
- 只改 HM2 nv_gw (40006), 不碰 HM1, 不碰 ms_gw 源码.
- ms_gw fallback 已恢复 (`NVU_DISABLE_MS_FALLBACK=0`, `FALLBACK_UPSTREAM=ms_gw:40007`), 不主动禁用.
- 改前有数据, 改后必验证, 写入仓库.

## 本轮关键数据 (30min, 14:39 CST 注入 + 14:44 复查)

### 1. cc4101-primary (cc2) 30min — 25 req, 20 200 / 5 502
- SR = 80% (表面), 但 5 个 502 全部集中在 14:26-14:30 CST 4 分钟窗口.

### 2. 5 个 502 根因 (非代码缺陷)
- 全是 `all_tiers_exhausted`(2) + `buffer_exhausted`(3), avg_dur=165025ms.
- `nv_tier_attempts` 表 30min 仅 1 条无关 429 (key2), 这 5 个 502 **零 tier
  attempt 记录** → 全 key cooling 时 buffer 5 次 attempt 直接 `execute_failed`
  elapsed=0s, 没真正打 NVCF.
- ms_gw fallback 同窗口也 FAIL (ms_gw 14:22-14:28 v5 全 key 429 风暴,
  `MS-VARIANT-EXHAUSTED`).
- 结论: NVCF + ms_gw 同窗口瞬时 429 风暴, 一次性尾部, 非反复.

### 3. 跨轮验证 post266 DELEGATE 修复 (对 dsv4p_nv 同效)
- 14:32 CST 之后干净窗口: 11 req 全 200, 0 失败, 0 fallback, 全 `nvcf_pexec`.
- 日志 `NV-BUFFER-EXEC-DELEGATE` 命中 4 次, 均 1 attempt 成功 (11-21s).
- post266 buffer `_execute_and_drain` MODE_CHAIN 空委托 `execute_request` 修复
  在 dsv4p_nv 路径下确认生效.

## 判稳
- 5 个 502 = 一次性窗口波动, 14:32 后全 200, 无反复.
- dsv4p_nv 链路 post266 修复生效, 无新错误模式.
- → NOP 巡检轮, 0 改动 0 restart.

## 下一步
1. 持续观察 dsv4p_nv 在 cc2 primary 下 SR, 看是否有反复 502 窗口.
2. 若 `all_tiers_exhausted` + 零 tier attempt 反复出现, 考察 KeyManager 全挂
   判定是否过早 (buffer 应能等 ProbeWorker 唤醒后重试, 而非 0s execute_failed).
3. 关注 dsv4p_nv 429 是否集中在特定 key/egress IP (本轮 key2 有 1 次, 样本少).

## 参数快照 (2026-08-02 14:44 CST, 本轮未改参数)
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
