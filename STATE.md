# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: **R1014 (NOP 巡检轮/不改码 — cc2 主链路连续第 122 轮 100% 干净; 主链专属错误 0 rows; fallback 0)**
> cc4101-primary (主 nv_gw:40006) 实时 30min = **125/125 = 100% SR, 0 bad** (live 复核);
> cc4101-primary 专属错误 = **0 rows** (125 request 全 200);
> 容器: nv_gw Up 13h, cc4101 Up 12h, dsv4p_nv40066 Up 2d, dsv4p health 全 200
> 上轮: R1013 (NOP, 主链 121/121=100%)

## 本轮 (R1014) 改动 + 依据 + 验证

### 改动: 无 (NOP。cc2 主链路连续 122 轮 100% 干净, 主专属错误 0 rows; 本轮 window 内 4 条 bad 全属 hermes)

### 依据 (live 复核 2026-08-07 16:20 CST + 注入轮前链路分析)

- 30min cc4101-primary (主 nv_gw:40006) = **125/125 全 200 = 100% SR, 0 bad** (live re-pull)。
- 主链专属错误 (caller=cc4101-primary, status!=200) = **0 rows** (scoped 错误分组为空)。
- 本轮 window 内 nv_requests 总 bad = 4 条 (dsv4f0731_nv 502), **经 DB live `SELECT caller,status,fid` 判定全属 hermes**
  (越界宿主 fid 52e1ddb6 泄漏)。
- fallback (cc_requests 30min) = **0 次** (125 request, 主链无 fallback 触发)。
- buffer 日志: 全 attempt=1 一次成功 (flush 1.2-3.9KB, 2-18s), verdict 全 success_tool_call, 无 BUFFER-/WAIT- 停滞。
- 主链当前首代模型 = **dsv4f0731_nv**。

### 本轮数据

| 指标 | 值 | 状态 |
|---|---|---|
| 主 nv_gw(40006) cc4101-primary | **125/125 = 100% SR, 0 bad** (live re-pull) | ✅ |
| 主链专属错误 (caller=cc4101-primary) | **0 rows** | ✅ |
| nv_requests 总 bad (非 200) | 4 条 (dsv4f0731_nv 502), 全属 hermes (fid 52e1ddb6), 主链 0 | ✅(主链) |
| 30min cc_requests | 125 request 无 fallback 触发 | ✅ |
| 30min nv_tier_attempts | 125 pexec_success + RemoteDisconnected(16)/Timeout(4)/empty_200(1), 全被 buffer 吸收 | ✅ |
| 容器 | nv_gw Up 13h, cc4101 Up 12h, dsv4p_nv40066 Up 2d, /health 全 200 | ✅ |

### 验证
- 30min nv_requests cc4101-primary = 125/125 (0 bad)。
- 主链专属错误分组 = 空 (0 rows)。
- 4 条非 200 经 DB live `SELECT caller,status,fid` 证实全属 hermes (caller=hermes, status=502, fid=52e1ddb6), 非 cc2 主链。
- cc_requests 30min 主链无 fallback 触发。
- buffer 日志: 全 attempt=1 成功 (flush 1.2-3.9KB, 2-18s), 无 BUFFER-/WAIT- 停滞。
- health: 4101/40006/40066 全 200; 容器 nv_gw/cc4101/dsv4p_nv40066 皆 Up。

### 关键判断
cc2 主链路连续第 **122** 轮 (R893-R1014) 100% SR 干净, 主链专属错误 0 rows。
本轮 4 条 bad (dsv4f0731_nv 502) 归属全属 hermes 越界宿主 (fid 52e1ddb6 泄漏) — 与主链 host
分离保持, 主链 125/125 全 200。fallback 0 次, 无新 cc2 主链错误类, 无持久 key 疲劳, 无 BUFFER-/WAIT- 停滞。
buffer + multi-key round-robin + func_health 完全吸收瞬态错误 (nv_tier_attempts 里 RemoteDisconnected 16 次
/ Timeout 4 次 / empty_200 1 次 从未穿透到 caller), 全 attempt=1 一次成功 (flush 1.2-3.9KB, 2-18s)。
**不改码**: ①主链 SR 100% + 专属错误 0 行, 无优化需求; ②本轮 bad 全属 hermes 越界, 主链无根因可查;
③ multi-key round-robin + func_health + buffer (attempt=1 全成功) 已达稳态, 无参数可调。

## 下一步
- 保持 NOP 观察, 主链 dsv4f0731_nv 为首代, 无需参数改动。
- 后续窗口继续确认 hermes 越界 bad (fid 52e1ddb6) 是否持续与主链隔离 (host 分离保持)。

## 容器健康
- nv_gw Up 13h, cc4101 Up 12h, dsv4p_nv40066 Up 2d; /health 40006/4101/40066 全 200。
- 配置快照: PRIMARY_UPSTREAM_MODEL=dsv4f0731_nv, nv_gw nv_default_model=glm5_2_nv,
  NVU_DISABLE_MS_FALLBACK=0, NVU_BUFFER_MAX_RETRIES=5, KeyManager 429 120s-600s 退避,
  ProbeWorker 15s, WaitQueue max 120s, nv_breaker mid-stream 软挂→OPEN。
  deadline 链: 90s×5=450s buffer < 470s cc4101 < 500s SDK idle。ms_gw fallback 保持不禁用。