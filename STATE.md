# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: **R902 (NOP 巡检轮/不改码 — cc2 主链路连续第 11 轮 100% 干净; 5 条 all_tiers_exhausted+stream_absolute_cap (502) + 22 条 bad fid 52e1ddb6 全属 hermes 线, JOIN 铁证, 非 cc2 范围)**
> cc4101-primary (主 nv_gw:40006) 实时 30min = **131/131 = 100% SR, 0 bad** (实拉);
> live DB now()≈2026-08-07 08:45 CST
> 上轮: R901 (NOP, 主链 127/127=100%)

## 本轮 (R902) 改动 + 依据 + 验证

### 改动: 无 (NOP。cc2 主链路连续 11 轮 100% 干净, 无新错误类; bad 请求 + bad fid 全属 hermes 非 cc2)

### 依据 (live DB 30min 实拉, ≈2026-08-07 08:45 CST)

- 30min cc4101-primary (主 nv_gw:40006) = **131/131 全 200, 0 bad (100% SR)**。
  实拉 `WHERE caller='cc4101-primary' AND status!=200` → **0 条**。
- per-key (nv_tier_attempts JOIN 30min): 5 key × 26 = 130 次全走健康 fid **281478d0**,
  error_type=pexec_success, 0 错误。0 条 52e1ddb6 进 cc2 候选池。
- 30min 所有 bad = `caller=hermes`: `all_tiers_exhausted ×4 (avg 178869ms)` +
  `stream_absolute_cap ×1 (avg 177533ms)`。
- 坏 fid 52e1ddb6 (22 条) 全走 `dsv4f0731_nv` tier 但 **request_id JOIN 铁证**: 22 条全
  caller=hermes, cc2 主链 0 泄漏 (越界容器 40666 hermes 线, 容器级分离奏效)。
- buffer (cc4101-primary): 全 attempt=1/5 成交, 8-10s 复盘 success_tool_call, 0 重试 / 0 429 / 0 cooldown。
- fallback (cc2 线) 0 次。
- 三 scoped 容器 health: 4101/40006/40066 全 ok (200), nv_gw Up 5 hours。

### 本轮数据

| 指标 | 值 | 状态 |
|---|---|---|
| 主 nv_gw(40006) cc4101-primary | **131/131 = 100% SR, 0 bad** (实拉) | ✅ |
| hermes 线 bad (502) | all_tiers_exhausted ×4 + stream_absolute_cap ×1, avg ~178s | ⚠️ 越界 |
| bad fid 52e1ddb6 | 22 条全 caller=hermes (JOIN 铁证), cc2 0 泄漏 | ✅ 隔离 |
| per-key (nv_tier_attempts) | 主链各 key 281478d0 ×26, 全 pexec_success, 0 错误 | ✅ |
| buffer (cc4101-primary) | 全 attempt=1/5, 0 重试 / 0 429 / 0 cooldown | ✅ |
| 三 scoped health | 4101/40006/40066 全 ok (200), nv_gw Up 5h | ✅ |
| fallback (cc2 线) | 0 次 | ✅ |

### 验证
- curl 4101/40006/40066 → 全 ok (200); cc4101 primary=dsv4f0731_nv。
- 30min nv_requests cc4101-primary 实拉 = 131/131 (0 bad)。
- 52e1ddb6 归属 JOIN 铁证: 22 条全 caller=hermes, cc2 主链 0 泄漏。
- per-key 主链全 281478d0 健康, 0 error。

### 关键判断
cc2 主链路连续 11 轮 (R892 139/139, R893 153/153, R894 143/143, R895 137/137,
R896 134/134, R897 126/126, R898 125/125, R899 124/124, R900 126/126, R901 127/127,
**R902 131/131**) 100% SR 干净。bad 请求 + bad fid 52e1ddb6 100% 属 hermes caller 活动,
JOIN 铁证未进 cc2 主链候选池。
**不改码**: ①主链 SR 100% 无优化需求; ②坏请求/坏 fid 全属 hermes 越 cc2 范围; ③容器级分离持续奏效, 已达稳态。

## 修复链 (沿用, R827+R828+R829+R833+R813 + R869+R876+R891)
1. glm5_2_nv 全 key 疲劳 → R829/R833 fail-fast + cc4101 动态 primary → dsv4f0731_nv
2. dsv4f0731_nv 一次成功 (主链已用健康 fid 281478d0), 用户无感知
3. 多 tier round-robin + func_health fid 健康选择自适应吸收底层跨 key/fid 瞬态失败

## 健康检查
- `curl localhost:4101/health` → ok ✅ (cc4101, primary=dsv4f0731_nv)
- `curl localhost:40006/health` → ok ✅ (nv_gw, passthrough, 5 keys)
- `curl localhost:40066/health` → ok ✅ (dsv4p_nv40066)

## 参数快照 (env, 本轮未改)
- nv_gw(40006): NVU_DISABLE_MS_FALLBACK=0, UPSTREAM_TIMEOUT=90, NVU_FORCE_STREAM_UPGRADE=0,
  NVU_FORCE_STREAM_UPGRADE_TIMEOUT=150, TIER_TIMEOUT_BUDGET_S=180, TIER_COOLDOWN_S=180,
  KEY_COOLDOWN_S=30, NV_INTEGRATE_KEY_COOLDOWN_S=90, NVU_BUFFER_CALLERS=cc4101-primary,openclaw2,
  NVU_CALLER_KEY_MAP=hermes:2;openclaw:3;opencode:4, MIN_OUTBOUND_INTERVAL_S=10,
  NVU_BUFFER_MAX_RETRIES=5 (90×5=450s)
- cc4101(4101): PRIMARY_UPSTREAM_URL=http://nv_gw:40006/v1/messages, primary=dsv4f0731_nv,
  CC4101_STREAM_TOTAL_DEADLINE_S=470, PRIMARY_HEADER_TIMEOUT=400, PRIMARY_FAIL_THRESHOLD=3,
  UPSTREAM_TIMEOUT=130, UPSTREAM_IDLE_TIMEOUT=150, FALLBACK_UPSTREAM_URL=http://ms_gw:40007/v1/chat/completions,
  FALLBACK_UPSTREAM_MODEL=glm5_2_ms (铁律4 不主动改 fallback)
- config.py: dsv4f0731_nv function_ids=[281478d0-f307-49f4-9e0f-080b63b16c47] (主链 R-fid0731);
  dsv4f_nv function_ids=[52e1ddb6-c745-4802-93f5-ba012d04c336]
- deadline 链: 90s×5=450s buffer < 470s cc4101 < 600s API < 900s idle

## 下一步
- 主链 cc2 连续 11 轮 100% 干净, 下轮预期维持 NOP。
- **优先监控**: ①主链 dsv4f0731 rotation 持续只出健康 fid 281478d0; ②hermes 线 all_tiers_exhausted
  + 52e1ddb6 泄漏活动 — 若污染进 40006/40066 候选池再介入 (目前 0 泄漏); ③fallback 触发率保持 <5% (当前 0)。