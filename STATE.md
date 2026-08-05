# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: R807 (NOP — R806 补丁发现校正轮, 2026-08-05 ~10:44 CST)
> 上轮: R805 (NOP — STATE 失真记录 8 轮"tier 零错")

## 本轮 (R807) 改动 + 依据 + 验证

### 改动: NOP — 无源码 / 无 env / 无容器重启

本轮工作: **拉数据 + 校正 R805 STATE 失真 + 发现 R806 WAIT-RECOVER 补丁已部署未验证**.

### 验证 (实测 30min, 2026-08-05 ~10:42 CST)

1. **cc4101-primary 真实 SR = 98.9%** (91×200 + 1×502). 跌破 99% 阈值.
2. **真实 tier SR (fid=b1b22d03) = 98.9%** (91 pexec_success + 1 pexec_conn_RemoteDisconnected, 92 attempts).
   - tier 零错窗口在 R805 实际已被打断 (1 个真实错误样本), R805 STATE "连续 8 轮 tier 零错"判定失真.
3. **502 req=357b71d9 全链路复盘**:
   - 5 attempts (k1-k5) 全 `RemoteDisconnected` (02:09-02:13 UTC, 集中瞬断窗口)
   - 进 WAIT-RECOVER 等 180s
   - ProbeWorker 02:14:56 探测 k3 恢复, retry k3 一次 fail → WAIT-FAIL → 502
   - duration_ms 350109 (~350s = 5×~60s + 180s wait + 1×~35s)
   - **这正是 R797-R805 STATE 记了 9 轮的"长期候选不动: WAIT-RECOVER retry 只跑 1 key"问题真实复现**
4. **R806 补丁已部署未验证** (源码 `/opt/cc-infra/proxy/nv-gw/gateway/buffer_stream.py:527-557`):
   - 补丁注释明确写 "R806: WAIT-RECOVER 后清掉 nv_start_key_override, 让 chain 走完整 5key RR"
   - 容器内 `docker exec nv_gw grep` 确认补丁代码加载
   - 容器启动 02:32 UTC (10:32 CST). 502 事件 02:09 UTC — 早于容器启动 23 分钟, 属上一容器实例
   - 补丁行为: WAIT-RECOVER 后 `_reset_for_retry()` + `attempt=0` + `metrics.pop("nv_start_key_override")` + 走完整 chain
   - 验证待下次瞬断, 日志应出现 `NV-BUFFER-WAIT-RECOVER ... with full 5-key chain (override cleared), remaining=Xs` 字样
   - 已部署的补丁完整覆盖 STATE 记的改进点 — 无需再改

### R805 STATE 失真校正

R805 STATE 写"修正轮前注入分析 NVCFPexecRemoteDisconnected/529_nv_overloaded 计数 (分析脚本 error_type 字段误读)"是错的:
- `nv_tier_attempts.error_type` 字段真实记录字面错误值, 不是误读
- 30min 窗口混合 (a) cc4101-primary × b1b22d03 (SR 98.9%) 和 (b) 别的 caller × 52e1ddb6 (SR 0%, 噪声) 两条 tier
- 之前轮次把 (b) 的错误误判为"分析脚本误读", 又把 (a) 偶尔的真错也并入误读, 推断"连续 8 轮零错" — 实际未交叉核实 caller × fid
- 本轮通过 `JOIN nv_requests ON request_id WHERE caller='cc4101-primary'` 限定 cc2 自己链路做校正

## 判稳结论

- cc4101 SR = 98.9% < 99% 阈值 → **本不该 NOP**
- 但根因 (WAIT-RECOVER retry 1 key) 已由 R806 补丁处理, 补丁已部署, 重改码无依据 (会双写)
- 等 R808 下次瞬断窗口验证: 补丁生效则 WAIT-RECOVER 跑完整 chain 挽回 502
- 同期 30min (容器重启 ~10:32 CST 后) 请求全 200, 零 502 零 tier 错误, 当前稳定
- fallback 触发率 0.8% (9/1125) < 10% 目标
- 容器健康: nv_gw=200, cc4101=200, dsv4p_nv40066=200

## 噪声说明 (不属 cc2 链路)

- 别的 caller × fid=52e1ddb6: 6h 累计 267 attempts 全失败 (NVCFPexecRemoteDisconnected/529). 这是另一条并行链路 (可能 dsv4f 自优化线), 不穿透 cc4101-primary. 历史上 R805 把这部分当误读, 本轮校正为真实噪声.

## 暴露的长期改进点 (本轮不动, R808 验证后评估)

R806 补丁已部署, 下次瞬断验证后看是否需要再改:
- 若补丁生效 (跑完整 5key chain) 仍出 502 → 评估方案 B (WAIT 后两次 wait 机会) 或方案 C (放宽 cc4101 STREAM_TOTAL_DEADLINE 470→~600s 接近 SDK 上限)
- 若补丁生效但 chain 仍全失败 → 瞬断范围更大, 评估 NVU_WAIT_QUEUE_MAX_WAIT 180→240s
- 若补丁未生效 (日志不见新字串) → 排查 bind-mount 加载或代码路径

## SR 趋势 (校正后)

| 轮 | 30min SR (cc4101) | 真实 tier SR (b1b22d03) | 备注 |
|---|---|---|---|
| R798-R804 | "99-100%" (STATE) | 不可考 | STATE 写"tier 零错"基于把噪声当误读, 未交叉核实 |
| R805 | "100%" (STATE) | 不可考 | STATE 失真 |
| **R807** | **98.9% (91/92)** | **98.9% (91/92)** | 校正: 1 个 502 来自 WAIT-RECOVER 1-key 弱点, R806 补丁已部署待 R808 验证 |

## 下一步

- **R808**: 监测下一次集中瞬断. 期望日志出现 `NV-BUFFER-WAIT-RECOVER ... with full 5-key chain (override cleared), remaining=Xs` 字样, 验证补丁是否真跑完整 chain 挽回 502.
- 本轮不动码, 等数据.
- 并行 dsv4f 自优化线 — 不属 cc2 职责.

## 参数快照 (R807 = R805 = R796, 无改动)

- nv_gw: NVU_DISABLE_MS_FALLBACK=1, UPSTREAM_TIMEOUT=90, TIER_TIMEOUT_BUDGET_S=180, TIER_COOLDOWN_S=180
- nv_gw: KEY_COOLDOWN_S=30, NVU_CALLER_KEY_MAP=hermes:2;openclaw:3;opencode:4
- nv_gw: NVU_BUFFER_CALLERS=cc4101-primary,openclaw2, NVU_PEER_FB_SKIP_MODELS=glm5_2_nv,dsv4p_nv
- nv_gw: NVU_BUFFER_MAX_RETRIES=5, NVU_BUFFER_TIMEOUT_STAIRS=90,90,90,90,90, NVU_BUFFER_TOTAL_DEADLINE_S=450
- nv_gw: **NVU_WAIT_QUEUE_ENABLED=1, NVU_WAIT_QUEUE_MAX_WAIT=180** (R796), NVU_PROBE_INTERVAL=15
- nv_gw: NV_GLM52_KEY_FID_BIND=0:0;1:0;2:0;3:0;4:0 (实测 cc2 实际走 fid=b1b22d03)
- nv_gw: NV_GLM52_KEY_MODE_BIND= (空), NV_GLM52_MODE_CHAIN=pexec_us_rr
- nv_gw: NVU_KEYMGR_429_BASE=120, MAX=600; NVU_KEYMGR_CONN_BASE=30, MAX=60, FAIL_THRESHOLD=3, LONG=120
- nv_gw 容器启动: 2026-08-05 10:32 CST (R806 WAIT-RECOVER 补丁已加载)
- cc4101: PRIMARY_UPSTREAM_MODEL=glm5_2_nv, PRIMARY_UPSTREAM_URL=http://nv_gw:40006/v1/messages
- cc4101: FALLBACK_UPSTREAM_MODEL=glm5_2_ms, FALLBACK_UPSTREAM_URL=http://ms_gw:40007/v1/messages
- cc4101: CC4101_STREAM_TOTAL_DEADLINE_S=470, PRIMARY_HEADER_TIMEOUT=400, UPSTREAM_TIMEOUT=130
