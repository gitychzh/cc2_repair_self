# STATE — cc2 自优化 nv_gw 链路 (R-nvonly 方向)

## 当前轮基线 (2026-08-02 15:13 CST, R274 NOP 巡检轮)
- 本仓 master: 本轮 R274. (主仓 hermes_improve_self main 收 round 文件.)
- **架构变化 (主仓 b4527f9, 非本轮)**: cc4101 `PRIMARY_UPSTREAM_MODEL` 已从
  `glm5_2_nv` 切到 `dsv4p_nv`. cc2 链路现 = cc4101(dsv4p_nv) → nv_gw → NVCF.
- **本轮 R274 (hm2_cc2)**: NOP 巡检轮. cc2 (cc4101-primary) 30min 0 req (session 间歇空闲),
  hermes/openclaw caller dsv4p_nv 28/29=96.6% 全 200 除 1 个瞬时 429 风暴尾巴
  (req eab966c9, 15:10:31, k3 命中 NVCF 429 无 retry-after 头, TIER_COOLDOWN 牵连 4 健 key 180s,
  与 R269/R271 记录的"一次性 429 风暴窗口"同模式, 非代码缺陷). 0 fallback. 0 改动 0 restart.

## R-nvonly 核心铁律 (持续生效)
- 只改 HM2 nv_gw (40006), 不碰 HM1, 不碰 ms_gw 源码.
- ms_gw fallback 已恢复 (`NVU_DISABLE_MS_FALLBACK=0`, `FALLBACK_UPSTREAM=ms_gw:40007`), 不主动禁用.
- 改前有数据, 改后必验证, 写入仓库.

## 本轮关键数据 (30min 实时 DB 复查 ~15:13)

### 1. 全 caller × model × status (cc2 primary 0 req)
| caller | model | status | count |
|---|---|---|---|
| hermes | dsv4p_nv(k3) | 200 | 27 |
| hermes | (mapped) | 429 | 1 |
| openclaw | dsv4p_nv(k4) | 200 | 1 |
- dsv4p_nv SR=28/29=96.6%. cc4101-primary 30min 0 req (session 间歇空闲).

### 2. 唯一失败 eab966c9 (hermes caller 非 cc2, 15:10:31)
- k3 → NVCF 429, egress=203.10.96.139/mihomo-7902, 无 retry-after 头.
- 级联 TIER_COOLDOWN 把 k1/k2/k4/k5 也标 cooling 180s (各自 count decayed>300s→reset count=1).
- 1547ms 声明 all_tiers_exhausted: 1 真实 429 + 4 被牵连. `nv_tier_attempts` 0 条 (走 pexec peek-retry path).
- 模式同 R269/R271 一次性风暴尾巴, 非新错误, 非代码缺陷.

### 3. post266 DELEGATE + 自恢复闭环
- 上轮 R268-R273 已实测: buffer 全挂后退避 5s → attempt2 ProbeWorker 唤醒 → success.
- 本轮无 cc2 流量, 未触发自恢复闭环复测, 待 session 恢复流量后复测.

### 4. health (本轮无 restart)
- nv_gw /health: status=ok, nv_num_keys=5, default_model=glm5_2_nv, port=40006.

## 判稳
- cc2 primary 无流量 (0 req), 链路空闲健康.
- hermes/openclaw dsv4p_nv 28/29=96.6%, 唯一失败为瞬时 429 风暴尾巴非代码缺陷.
- 无新错误模式, 无 fallback (f=29 全 false).
- → NOP 巡检轮, 0 改动 0 restart.

## 下一步
1. 持续观察 dsv4p_nv 在 cc2 primary 下 SR, 看是否有新 429 风暴窗口.
2. 若 all_tiers_exhausted + TIER_COOLDOWN 牵连 4 健 key 反复出现 (>1/h), 考察
   TIER_COOLDOWN 对"单 key 429"是否过度牵连. 现状对孤立风暴可接受, 高频时再调.
3. cc2 session 恢复流量后复测自恢复闭环 (backoff 5s→attempt2).

## 参数快照 (2026-08-02 15:13 CST, 本轮未改参数)
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
  NV_GLM52_MODE_CHAIN= (空, post266 设计)
