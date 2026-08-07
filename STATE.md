# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: **R895 (NOP 巡检轮/不改码 — cc2 主链路连续 4 轮 100% 干净; hermes 线 52e1ddb6 浪费仍在 40666 越界容器, 非 cc2 范围)**
> cc4101-primary (主 nv_gw:40006) 实时 30min = **131/131 = 100% SR, 0 bad**;
> 30min 所有 bad 全属 hermes caller: all_tiers_exhausted ×5 (502),
> 实拉铁证全带 fid=**52e1ddb6** (坏 fid), 归属 **dsvf0731_nv40666** (hermes 线, host 分离),
> 未进 cc2 主 nv_gw(40006) 候选池。
> nv_tier_attempts 成功全 5 key 健康 fid; 失败 22 条 (RemoteDisconnected 18/Timeout 3/504 1) 全带 52e1ddb6。
> buffer 全程 attempt=1/5 即 success_tool_call (~8-11s)。
> live DB now()≈2026-08-07 00:35 UTC (08:35 CST)
> 上轮: R894 (NOP, 主链 143/143=100%; 复确认 52e1ddb6 泄漏源=dsvf0731_nv40666)

## 本轮 (R895) 改动 + 依据 + 验证

### 改动: 无 (NOP。cc2 主链路连续 4 轮 100% 干净, 无新错误类; 只复确认 hermes 线 52e1ddb6 仍隔离在 40666)

### 依据 (live DB now()≈2026-08-07 00:35 UTC)

- 30min nv_requests: **cc4101-primary = 131/131 全 200, 0 bad (100% SR)**;
  hermes = 502 ×5 (all_tiers_exhausted, 平均 178s)。
  实拉 `WHERE caller='cc4101-primary' AND status!=200` → 0 条。
- nv_tier_attempts 30min 成功 (pexec_success) 全 5 key: k0=24 k1=28 k2=27 k3=27 k4=25, 全健康 fid;
  失败 22 条全带 52e1ddb6 (NVCFPexecRemoteDisconnected ×18 / NVCFPexecTimeout ×3 / 504_nv_gateway_timeout ×1)
  = hermes 线 40666。**cc4101-primary 0 命中坏 fid**。
- buffer 日志 (08:24 CST 样例): 全程 caller=cc4101-primary attempt=1/5 即
  verdict=success_tool_call, elapsed ≈ 8~11s, done=True, closed=False, buffered=1~16KB。全干净。
- 2h 错误类 = all_tiers_exhausted ×37 + buffer_exhausted ×6 + client_gone_during_flush ×1
  + stream_absolute_cap ×1, 全沿用 R894 已知归属 (hermes/40666), **无新错误类**。
- 四容器 health: 4101/40006/40066/40666 全 ok; nv_gw 实时 buffer 日志全 attempt=1 成交。

### 本轮数据

| 指标 | 值 | 状态 |
|---|---|---|
| 主 nv_gw(40006) cc4101-primary | **131/131 = 100% SR, 0 bad** | ✅ |
| nv_tier_attempts 成功 | 全 5 key pexec_success (健康 fid), 0 命中 52e1ddb6 | ✅ |
| tier 失败归属 | 全 52e1ddb6 (RemoteDisconnected ×18 / Timeout ×3 / 504 ×1) | ⚠️ 40666 越界 |
| buffer (cc4101-primary) | 全 attempt=1/5 success_tool_call, 8-11s, 0 重试 | ✅ |
| hermes 线 bad (40666, 52e1ddb6) | all_tiers_exhausted ×5 = 502 | ⚠️ 越界容器 |
| 2h 错误类 | 全已知 40666/hermes 模式, 无新类 | ✅ |
| 四 scoped health | 4101/40006/40066/40666 全 ok | ✅ |
| fallback (cc2 线) | 0 次 | ✅ |

### 验证
- curl 4101/40006/40066/40666 → 全 ok; cc4101 primary=dsv4f0731_nv。
- 30min nv_requests cc4101-primary 实拉 = 131/131 (0 bad); 所有 bad 实拉归 hermes+52e1ddb6。
- nv_tier_attempts 失败全带 52e1ddb6, 成功全健康 fid → 主链 0 坏。

### 关键判断
cc2 主链路连续 4 轮 (R892 139/139, R893 153/153, R894 143/143, R895 131/131) 100% SR 干净。所有坏请求仍由
hermes 线的 **dsvf0731_nv40666** (坏 fid 52e1ddb6) 产生, 与 cc2 主链主机分离, 不影响 cc2 SR。
**不改码**: ①40666 不在 cc2 改动范围 (铁律: 只改 40006+40066); ②对 cc2 SR 无影响;
③40666 恒卡坏 fid 的根因 (discovery probe 用 `-flash` 非 `-0731` model → probe 281478d0 恒 404)
属独立容器运维决策, 待归属确认后单独评估。

## 修复链 (沿用, R827+R828+R829+R833+R813 + R869+R876+R891)
1. glm5_2_nv 全 key 疲劳 → R829/R833 fail-fast + cc4101 动态 primary → dsv4f0731_nv
2. dsv4f0731_nv 一次成功 (主链已用健康 fid 281478d0), 用户无感知
3. 多 tier round-robin (dsv4p/dsv4f/dsv4f0731/glm5_2_nv) + func_health fid 健康选择自适应吸收底层跨 key/fid 瞬态失败

## 健康检查
- `curl localhost:4101/health` → ok ✅ (cc4101, primary=dsv4f0731_nv)
- `curl localhost:40006/health` → ok ✅ (nv_gw, passthrough, 5 keys, nv_default_model=glm5_2_nv)
- `curl localhost:40066/health` → ok ✅ (dsv4p_nv40066)
- `curl localhost:40666/health` → ok ✅ (dsvf0731_nv40666, 越界记录)
- `docker ps` → nv_gw / cc4101 / dsv4p_nv40066 / dsvf0731_nv40666 / nv_gw_stable 全 Up ✅

## 参数快照 (env, 本轮未改)
- nv_gw(40006): NVU_DISABLE_MS_FALLBACK=0, UPSTREAM_TIMEOUT=90, NVU_FORCE_STREAM_UPGRADE=0,
  TIER_TIMEOUT_BUDGET_S=180, TIER_COOLDOWN_S=180, KEY_COOLDOWN_S=30, NV_INTEGRATE_KEY_COOLDOWN_S=90,
  NVU_BUFFER_CALLERS=cc4101-primary,openclaw2, NVU_CALLER_KEY_MAP=hermes:2;openclaw:3;opencode:4,
  NVU_PEER_FB_SKIP_MODELS=glm5_2_nv,dsv4p_nv, MIN_OUTBOUND_INTERVAL_S=10, NVU_BUFFER_MAX_RETRIES=5 (90×5=450s)
- cc4101(4101): PRIMARY_UPSTREAM_URL=http://nv_gw:40006/v1/messages, primary=dsv4f0731_nv,
  CC4101_STREAM_TOTAL_DEADLINE_S=470, PRIMARY_HEADER_TIMEOUT=400, PRIMARY_UPSTREAM_MODEL=dsv4f0731_nv,
  FALLBACK_UPSTREAM_URL=http://ms_gw:40007/v1/chat/completions, FALLBACK_UPSTREAM_MODEL=glm5_2_ms
  (铁律4 不主动改 fallback)
- config.py: dsv4f0731_nv function_ids=[281478d0-f307-49f4-9e0f-080b63b16c47] (主链, R-fid0731);
  dsv4f_nv function_ids=[52e1ddb6-c745-4802-93f5-ba012d04c336]
- ⚠️ dsvf0731_nv40666 (越界容器, 记录): NVU_FID_DISCOVERY_ENABLED=1, MODEL=dsv4f0731_nv,
  NAME_MATCH=deepseek-v4-flash, NVCF_DEEPSEEK_FLASH_FUNCTION_ID=52e1ddb6 → discovery probe 281478d0 恒 404, 卡坏 fid

## 下一步
- 主链 cc2 连续 4 轮 100% 干净, 下轮预期维持 NOP (无新事件)。
- **优先监控**: 主 nv_gw(40006) dsv4f0731 rotation 是否持续只出健康 fid (0 bad 保持)。
- 52e1ddb6 浪费归属 **dsvf0731_nv40666 (hermes 线)**, 非 cc2 范围; 可选修复 = discovery probe 用
  `-0731` model 名 或 显式 env `NVCF_DEEPSEEK_FLASH_0731_FUNCTION_ID`=281478d0。待归属确认单独评估。
- 保持 cc4101-primary fallback=dsv4f0731_nv 不动。