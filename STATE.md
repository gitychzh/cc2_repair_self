# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: R813 (restart 加载 R813 chain_full_retry 修复, 2026-08-05 12:20 CST)
> 上轮: R812 (NOP — R806 WAIT-RECOVER 补丁首次 RECOVER 分支实战触发)

## 本轮 (R813) 改动 + 依据 + 验证

### 改动: docker compose restart nv_gw (无源码改动, 加载已有 R813 修复)

R813 `chain_full_retry=True` 修复已于 R812 commit (3f72bae) 写入 buffer_stream.py:268-273 + 571-572,
但容器主进程 10:32 CST 启动, 加载的是修复前的老代码. 本轮 restart 让主进程重新 import.

### 根因 (铁证)
- 2h 内 WAIT-RECOVER 触发 11 次, 全部 WAIT-FAIL, 0 次 NV-BUFFER-CHAIN-FULL
- RECOVER 后日志: `BUFFER_OVERRIDE start_key=kX (NVCF 1 attempt)` = 老逻辑 (只试 1 key)
- 新代码应 emit `NV-BUFFER-CHAIN-FULL` + 走完整 5key RR, 但 0 次出现 → 主进程跑老代码
- docker exec python3 (新进程) 能看到 chain_full_retry, 但主 uvicorn 进程缓存 10:32 时的代码

### 验证 (restart 后 12:18 CST)
1. **health OK**: `curl /health` → status=ok, 5 keys ✅
2. **docker exec 验证**: `inspect.signature(_execute_and_drain)` → `(self, timeout_s, is_first=False, chain_full_retry=False)` ✅
3. **待下个窗口**: 若再触发 WAIT-RECOVER, 应出现 `NV-BUFFER-CHAIN-FULL` log + 走完整 5key chain

## 判稳结论

| 指标 | restart 前 30min | 目标 | 状态 |
|---|---|---|---|
| nv_gw SR (cc4101-primary) | 89.2% (66/74) | 90%+ | ⚠️ 略低 |
| fallback 触发率 | 10.53% (8/76) | <10% | ⚠️ 略超 |
| R806 RECOVER 成功率 | 0% (0/11) | >0% | ❌ 老代码 → restart 修复 |

**本轮实质: R813 修复代码早已 commit 但容器主进程未 restart 加载 → RECOVER 11 次全走老逻辑 (只试 1 key) → 全 FAIL. restart 后修复应生效.**

## SR 趋势

| 轮 | 30min SR (cc4101-primary) | RECOVER 触发 | 备注 |
|---|---|---|---|
| R811 | 100% (91/91) | 1 (fall-through) | WAIT 首触达 |
| R812 | 98.75% (79/80) | 1 (RECOVER 首次) | 补丁 RECOVER 首触发 |
| **R813** | **89.2% (66/74)** | **11 (全 FAIL)** | **restart 加载 R813 修复** |

## 噪声 (不属 cc2 链路)

- hermes × dsv4f0731_nv: 30min SR 73.3% (11/15, 4×502) — dsv4f 自优化线, 不穿透 cc2

## 下一步

- **R814**: 监测 restart 后下一个 WAIT-RECOVER 触发:
  1. ✅ 预期: `NV-BUFFER-CHAIN-FULL` log 出现 (新代码生效标志)
  2. ✅ 预期: RECOVER 后走完整 5key RR, 非 `BUFFER_OVERRIDE ... 1 attempt`
  3. ⏳ 待观测: RECOVER retry 成功 → `NV-BUFFER-WAIT-OK` (补丁真正挽救 req)
  4. 若仍 WAIT-FAIL 但 CHAIN-FULL 出现: 5key 确实全在抖, 需考虑:
     - ProbeWorker probe 间隔 15s 是否太短 (刚 probe 通但实际不稳)
     - NVU_WAIT_QUEUE_MAX_WAIT 180→240s
     - RECOVER retry 失败后给一次额外 WAIT

## 参数快照 (R813 = R812 参数, 仅 restart)

- nv_gw StartedAt: 2026-08-05 12:18 CST (R813 chain_full_retry 修复已加载)
- nv_gw: NVU_DISABLE_MS_FALLBACK=1, UPSTREAM_TIMEOUT=90, TIER_TIMEOUT_BUDGET_S=180, TIER_COOLDOWN_S=180
- nv_gw: KEY_COOLDOWN_S=30, NVU_CALLER_KEY_MAP=hermes:2;openclaw:3;opencode:4
- nv_gw: NVU_BUFFER_CALLERS=cc4101-primary,openclaw2, NVU_PEER_FB_SKIP_MODELS=glm5_2_nv,dsv4p_nv
- nv_gw: NVU_BUFFER_MAX_RETRIES=5, NVU_BUFFER_TIMEOUT_STAIRS=90×5, NVU_BUFFER_TOTAL_DEADLINE_S=450
- nv_gw: NVU_WAIT_QUEUE_ENABLED=1, NVU_WAIT_QUEUE_MAX_WAIT=180, NVU_PROBE_INTERVAL=15
- nv_gw: NVU_KEYMGR_429_BASE=120 MAX=600, NVU_KEYMGR_CONN_BASE=30 MAX=60 FAIL_THRESHOLD=3
- cc4101: PRIMARY=glm5_2_nv @ nv_gw:40006, FALLBACK=glm5_2_ms @ ms_gw:40007
- cc4101: CC4101_STREAM_TOTAL_DEADLINE_S=470, PRIMARY_HEADER_TIMEOUT=400, UPSTREAM_TIMEOUT=130

## 一句话总结

R813 根因轮 — 30min SR 89.2% + fallback 10.53% 双双告警, 深挖发现 R806 WAIT-RECOVER 补丁 2h 内触发 11 次全 WAIT-FAIL. 根因: R812 commit 已含 R813 chain_full_retry 修复 (buffer_stream.py:268-273), 但容器主进程 10:32 启动加载老代码, R813 修复从未生效. 日志铁证: RECOVER 后走 BUFFER_OVERRIDE (老逻辑只试 1 key) 而非 NV-BUFFER-CHAIN-FULL (新逻辑走完整 5key RR). docker compose restart nv_gw 12:18 CST 加载新代码, 待下个 RECOVER 触发验证 CHAIN-FULL log + retry 成功.
