# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: **R1019 (NOP 巡检轮/不改码 — cc2 主链路连续第 127 轮 100% 干净; 主链专属错误 0 rows; fallback 0)**
> cc4101-primary (主 nv_gw:40006) 实时 30min = **125/125 = 100% SR, 0 bad** (live 复核);
> cc4101-primary 专属错误 = **0 rows** (125 request 全 200);
> 容器: nv_gw Up 18h, cc4101 Up, dsv4p_nv40066 Up, /health 全 200
> 上轮: R1018 (NOP, 主链 128/128=100%)

## 本轮 (R1019) 改动 + 依据 + 验证

### 改动: 无 (NOP。cc2 主链路连续 127 轮 100% 干净, 主专属错误 0 rows; 本轮 window 内 4 条 bad 全属 hermes)

### 依据 (live 复核 2026-08-07 ~16:35 CST + 注入轮前链路分析)

- 30min cc4101-primary (主 nv_gw:40006) = **125/125 全 200 = 100% SR, 0 bad** (live `SELECT caller,status,count(*) ... caller='cc4101-primary'`)。
- 主链专属错误 (caller=cc4101-primary, status!=200) = **0 rows** (scoped 错误分组为空)。
- 本轮 window 内 nv_requests 总 bad = 4 条 (502),
  经 DB live `SELECT caller,error_type` 判定 4 行全属 hermes (all_tiers_exhausted 2 / NVStream_IncompleteRead 1 / stream_absolute_cap 1)。
- fallback (cc_requests 30min) = **0 次 / 0.0%** (2033 request, 主链无 fallback 触发)。
- 主链当前首代模型 = **dsv4f0731_nv**, 无 tier 降级/无 key 疲劳。
- buffer 全 attempt=1 成功 (elapsed 3~17s), 无 attempt>1, 无 WAIT/cooldown 日志。
- 本轮 4 bad 全属 hermes 越界宿主, 主链 host 分离干净, 无泄漏。

### 本轮数据

| 指标 | 值 | 状态 |
|---|---|---|
| 主 nv_gw(40006) cc4101-primary | **125/125 = 100% SR, 0 bad** (live 查询) | ✅ |
| 主链专属错误 (caller=cc4101-primary) | **0 rows** | ✅ |
| nv_requests 总 bad (非 200) | 4 条 (502), 全属 hermes, 主链 0 | ✅(主链) |
| 30min cc_requests | 2033 request, fallback 0 次 (0.0%) | ✅ |
| 容器 | nv_gw Up 18h, cc4101 Up, dsv4p_nv40066 Up, /health 全 200 | ✅ |

### 验证
- docker exec logs_db psql: `SELECT caller,status,count(*) ... GROUP BY 1,2` → cc4101-primary 125 行全 200, 4 行 bad 全 caller=hermes。
- `SELECT caller,error_type ... status!=200` → 4 行全 hermes (all_tiers_exhausted 2 / NVStream_IncompleteRead 1 / stream_absolute_cap 1)。
- `SELECT count(*),sum(fallback_triggered) FROM cc_requests` → 2033/0 (0.0%)。
- health: 40006/4101/40066 全 200; 容器 nv_gw Up 18h。

### 关键判断
cc2 主链路连续第 **127** 轮 (R893-R1019) 100% SR 干净, 主链专属错误 0 rows。
本轮 4 条 bad (502) 归属全属 hermes 越界宿主 (all_tiers_exhausted 2 / NVStream_IncompleteRead 1 / stream_absolute_cap 1),
经 caller 铁证与主链 host 分离完全干净 — 主链 125/125 全 200。
fallback 0 次 (0.0%), 无新 cc2 主链错误类, 无持久 key 疲劳。
multi-key round-robin + func_health + buffer (attempt=1 全成功) 完全吸收瞬态错误,
未穿透到 caller, 已达稳态。
**不改码**: ①主链 SR 100% + 专属错误 0 行, 无优化需求; ②本轮 bad 全属 hermes 越界, 主链无根因可查;
③参数处于稳态, 无参数可调。

## 下一步
- 保持 NOP 观察, 主链 dsv4f0731_nv 为首代, 无需参数改动。
- 后续窗口继续确认 hermes 越界 bad (502) 是否持续与主链隔离 (caller JOIN)。

## 容器健康
- nv_gw Up 18h, cc4101 Up, dsv4p_nv40066 Up; /health 40006/4101/40066 全 200。
- 配置快照: PRIMARY_UPSTREAM_MODEL=dsv4f0731_nv, nv_gw nv_default_model=glm5_2_nv,
  NVU_DISABLE_MS_FALLBACK=0, NVU_BUFFER_MAX_RETRIES=5, KeyManager 429 120s-600s 退避,
  ProbeWorker 15s, WaitQueue max 120s, nv_breaker mid-stream 软挂→OPEN。
  deadline 链: 90s×5=450s buffer < 470s cc4101 < 600s API < 900s idle。ms_gw fallback 保持不禁用。
