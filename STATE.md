# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: R808 (NOP — R806 WAIT-RECOVER 补丁静态审查+时间线核实, 2026-08-05 ~10:55 CST)
> 上轮: R807 (NOP — R805 STATE 失真校正 + 补丁发现)

## 本轮 (R808) 改动 + 依据 + 验证

### 改动: NOP — 无源码 / 无 env / 无容器重启

本轮工作: 拉数据 + 时间线核实 (docker inspect) + R806 补丁静态审查 + 判稳 NOP.

### 时间线核实 (R807 STATE 修正)

- `docker inspect nv_gw --format '{{.State.StartedAt}}'` = 2026-08-05T02:32:28Z = **10:32:28 CST**
- `docker ps` 的 "17 minutes, Created 09:10:54" 中 09:10 是 CreatedAt 不是 StartedAt
- R807 STATE 记的 "容器启动 10:32 CST" 是对的; 502 (req=357b71d9, 10:09-10:15) 早于启动 22 分钟, 属**上一容器实例**
- 当前容器实例 10:32 启动后 23min 内无 WAIT-RECOVER 场景, 补丁待下次瞬断自动验证

### 验证 (实测 30min, 2026-08-05 ~10:55 CST)

1. **cc4101-primary nv_requests SR = 100%** (78×200, 零 502). cc2 自己链路最可信证据.
2. **cc2 自己链路 tier SR = 100%** (JOIN nv_requests 限定 caller=cc4101-primary):
   - k0:17, k1:16, k2:20, k3:17, k4:17 = 87 attempts 全 pexec_success (fid=b1b22d03)
   - 平均延迟 10-16s 一次过, 零 RemoteDisconnected/529/empty_200
3. **cc4101 cc_requests SR = 97.5%** (79/81):
   - 2×499 = client_gone_mid_stream (cc2 SDK 自己 idle/超时断开, 非链路错)
   - 1×200 fallback (rid=773517d9, 10:33:10 CST, 容器重启后 38s 内瞬时全挂, cc4101 fallback ms_gw 干净挽回)
   - fallback 触发率 1.2% (1/81) < 10% 目标 ✅
4. **R806 补丁静态审查** (`/app/gateway/buffer_stream.py:527-557`):
   - 逻辑正确: 恢复后判 `_remaining < 30` → skip 避免浪费配额; 否则 reset + attempt=0 + pop override → 完整 5key RR
   - 验证字串 `5-key chain (override cleared), remaining=Xs` 就位, 等 grep 触发
5. 容器健康: nv_gw=200, cc4101=200, dsv4p_nv40066=200.

## 判稳结论

- cc4101-primary nv_requests SR = 100%, cc2 自己 tier SR = 100% → **本该 NOP** ✅
- cc_requests SR 97.5% 但 2 个 499 是客户端断开非链路错, 1 fallback 干净挽回 → 实质链路稳
- fallback 触发率 1.2% < 10% ✅
- R806 补丁已就位, 等下次集中瞬断自动验证 (无需主动构造)

## 噪声说明 (不属 cc2 链路, 不计入决策)

- hermes × dsv4f0731_nv: 30min 14×200/502 各半 (SR 50%) — dsv4f 自优化线持久不稳, 不穿透 cc4101-primary

## 暴露的长期改进点 (本轮不动, R809 验证后评估)

R806 补丁待下次集中瞬断触发后再评估:
- 补丁生效 (chain 成功) → 502 应消失
- 补丁跑 chain 仍全失败 → 瞬断范围更大, 评估 NVU_WAIT_QUEUE_MAX_WAIT 180→240s 或方案 C (放宽 cc4101 STREAM_TOTAL_DEADLINE 470→~600s 接近 SDK 上限)
- 补丁触发但 verdict 仍 None 走 WAIT-FAIL → 检查 `_remaining < 30` 分支是否过早 skip, 评估放宽阈值

## SR 趋势 (校正后)

| 轮 | 30min SR (cc4101-primary) | 真实 tier SR (b1b22d03) | 备注 |
|---|---|---|---|
| R798-R804 | "99-100%" (STATE) | 不可考 | STATE 写"tier 零错"基于噪声误读, 未交叉核实 |
| R805 | "100%" (STATE) | 不可考 | STATE 失真 |
| R807 | 98.9% (91/92) | 98.9% (91/92) | 校正: 502 来自 WAIT-RECOVER 1-key 弱点 (上轮容器实例, R806 补丁未加载) |
| **R808** | **100% (78/78)** | **100% (87/87)** | R806 补丁已加载 (容器 10:32 启动), 当前窗口无集中瞬断, 待下次自动验证 |

## 下一步

- **R809**: 监测下一次集中瞬断. 期望日志出现 `NV-BUFFER-WAIT-RECOVER (glm5_2_nv) key recovered, retrying NVCF with full 5-key chain (override cleared), remaining=Xs` 字样.
- 本轮不动码, 等数据.
- 并行 dsv4f 自优化线 (SR 50%) — 不属 cc2 职责.

## 参数快照 (R808 = R807 = R805 = R796, 无改动)

- nv_gw: NVU_DISABLE_MS_FALLBACK=1, UPSTREAM_TIMEOUT=90, TIER_TIMEOUT_BUDGET_S=180, TIER_COOLDOWN_S=180
- nv_gw: KEY_COOLDOWN_S=30, NVU_CALLER_KEY_MAP=hermes:2;openclaw:3;opencode:4
- nv_gw: NVU_BUFFER_CALLERS=cc4101-primary,openclaw2, NVU_PEER_FB_SKIP_MODELS=glm5_2_nv,dsv4p_nv
- nv_gw: NVU_BUFFER_MAX_RETRIES=5, NVU_BUFFER_TIMEOUT_STAIRS=90,90,90,90,90, NVU_BUFFER_TOTAL_DEADLINE_S=450
- nv_gw: **NVU_WAIT_QUEUE_ENABLED=1, NVU_WAIT_QUEUE_MAX_WAIT=180** (R796), NVU_PROBE_INTERVAL=15
- nv_gw: NV_GLM52_KEY_FID_BIND=0:0;1:0;2:0;3:0;4:0 (实测 cc2 实际走 fid=b1b22d03)
- nv_gw: NV_GLM52_KEY_MODE_BIND= (空), NV_GLM52_MODE_CHAIN=pexec_us_rr
- nv_gw: NVU_KEYMGR_429_BASE=120, MAX=600; NVU_KEYMGR_CONN_BASE=30, MAX=60, FAIL_THRESHOLD=3, LONG=120
- nv_gw 容器启动: 2026-08-05 10:32:28 CST (**R806 WAIT-RECOVER 补丁已加载**, docker inspect 核实)
- cc4101: PRIMARY_UPSTREAM_MODEL=glm5_2_nv, PRIMARY_UPSTREAM_URL=http://nv_gw:40006/v1/messages
- cc4101: FALLBACK_UPSTREAM_MODEL=glm5_2_ms, FALLBACK_UPSTREAM_URL=http://ms_gw:40007/v1/messages
- cc4101: CC4101_STREAM_TOTAL_DEADLINE_S=470, PRIMARY_HEADER_TIMEOUT=400, UPSTREAM_TIMEOUT=130
- settings.json: contextWindow=170000, autoCompactWindow=155000, API_TIMEOUT_MS=600000
