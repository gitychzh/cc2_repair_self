# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: **R1035 (NOP 巡检轮/不改码 — cc2 主链路连续第 143 轮 100% 干净; 主链专属错误 0 rows; fallback 0)**
> cc4101-primary (主 nv_gw:40006) live 复核 30min = **119/119 = 100% SR, 0 bad** (live 查询);
> cc4101-primary 专属错误 = **0 rows** (119 request 全 200);
> 容器: nv_gw Up 14h, cc4101 Up 14h, dsv4p_nv40066 Up 2d, /health 全 200
> 上轮: R1034 (NOP, 主链 113/113=100%)

## 本轮 (R1035) 改动 + 依据 + 验证

### 改动: 无 (NOP。cc2 主链路连续第 143 轮 100% 干净, 主专属错误 0 rows; 本轮 window 内 2 条 bad 全属 hermes)

### 依据 (live 复核 2026-08-07 + 注入轮前链路分析 17:24 CST)

- 30min cc4101-primary (主 nv_gw:40006) = **119/119 全 200 = 100% SR, 0 bad** (live `SELECT caller,status,count(*) ... GROUP BY 1,2`)。
- 主链专属错误 (caller=cc4101-primary, status!=200) = **0 rows** (scoped 错误分组为空)。
- 本轮 window 内 nv_requests 总 bad = 2 条 (502), 经 DB live
  `SELECT caller,status,count(*) FROM nv_requests WHERE status!=200 ... GROUP BY 1,2` 判定全属 **hermes** 越界宿主。
- dsv4f0731_nv 全 caller SR = 98.9% (182/184), 2 bad 归属 hermes, 主链 0。
- fallback (cc_requests 30min) = **0 次 / 0.0%** (119 request, 主链无 fallback 触发)。
- 主链当前首代模型 = **dsv4f0731_nv** (cc4101.PRIMARY_UPSTREAM_MODEL), 无 tier 降级/无 key 疲劳。
- nv_tier_attempts per-key 健康: pexec_success 119 (k0=24/k1=21/k2=27/k3=24/k4=23), 偶发 NVCFPexecRemoteDisconnected x4
  / NVCFPexecTimeout x1 / empty_200 x1 全被 multi-key round-robin + func_health + buffer 吸收, 未穿透 caller。
- buffer 日志: 主链请求全 `[NV-BUFFER-VERDICT] attempt=1 verdict=success_text|success_tool_call` → 1 attempt 成功 flush, 无重试/无 wait/无缓冲耗尽。

### 本轮数据

| 指标 | 值 | 状态 |
|---|---|---|
| 主 nv_gw(40006) cc4101-primary | **119/119 = 100% SR, 0 bad** (live 查询) | ✅ |
| 主链专属错误 (caller=cc4101-primary) | **0 rows** | ✅ |
| nv_requests 总 bad (非 200) | 2 条 (502), 全属 hermes, 主链 0 | ✅(主链) |
| 30min cc_requests | 119 request, fallback 0 次 (0.0%) | ✅ |
| nv_tier_attempts 非成功 | RemoteDisconnected x4 / Timeout x1 / empty_200 x1 (全被吸收) | ✅ |
| 容器 | nv_gw Up 14h, cc4101 Up 14h, dsv4p_nv40066 Up 2d, /health 40006/4101/40066 全 200 | ✅ |

### 验证
- docker exec logs_db psql: `SELECT caller,status,count(*) ... GROUP BY 1,2` → cc4101-primary 119 行全 200, 无 bad。
- `SELECT caller,status,count(*) FROM nv_requests WHERE status!=200 ... GROUP BY 1,2` → 2 bad 502 caller 全 = hermes,
  主链专属错误 0 rows。
- `SELECT count(*),sum(case when fallback_triggered then 1 else 0 end) FROM cc_requests` → 119/0 (0.0%)。
- `SELECT nv_key_idx,error_type,count(*) FROM nv_tier_attempts` → 各 key pexec_success 为主 + 6 非成功 (4 RDisconn/1 Timeout/1 empty_200), 未穿透。
- docker logs nv_gw --since 30m grep BUFFER- → 主链请求全 attempt=1 success flush, 无重试。
- health: 40006/4101/40066 全 200; 容器 nv_gw Up 14h, cc4101 Up 14h, dsv4p_nv40066 Up 2d。

### 关键判断
cc2 主链路连续第 **143** 轮 (R893-R1035) 100% SR 干净, 主链专属错误 0 rows。
本轮 2 条 bad (502) 归属全属 **hermes** 越界宿主, 经 caller 铁证与主链 host 分离完全干净 — 主链 119/119 全 200。
fallback 0 次 (0.0%), 无新 cc2 主链错误类, 无持久 key 疲劳。
multi-key round-robin + func_health + buffer (attempt=1 大多成功) 完全吸收瞬态错误
(各 key 偶发 NVCFPexecRemoteDisconnected/NVCFPexecTimeout/empty_200), 未穿透到 caller, 已达稳态。
**不改码**: ①主链 SR 100% + 专属错误 0 行, 无优化需求; ②本轮 bad 全属 hermes 越界, 主链无根因可查;
③参数处于稳态, 无参数可调。

## 下一步
- 保持 NOP 观察, 主链 dsv4f0731_nv 为首代, 无需参数改动。
- 后续窗口继续确认 hermes 越界 bad (502) 是否持续与主链隔离 (caller JOIN)。

## 容器健康
- nv_gw Up 14h, cc4101 Up 14h, dsv4p_nv40066 Up 2d; /health 40006/4101/40066 全 200。