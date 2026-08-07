# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: **R1041 (NOP 巡检轮/不改码 — cc2 主链路连续第 149 轮 100% 干净; 主链专属错误 0 rows; fallback 0 次)**
> cc4101-primary (主 nv_gw:40006) live 复核 30min = **105/105 = 100% SR, 0 bad** (live 查询);
> cc4101-primary 专属错误 = **0 rows** (nv_tier_attempts 非成功也 0 rows, buffer 零重试);
> nv_requests 总 bad = 4 (zombie_empty_completion×3/NVStream_IncompleteRead×1), 全属 hermes 越界宿主;
> fallback (cc_requests 30min) = **0 次 / 0.0%** (106 request, 106 ok, SR=100.0%);
> 容器: nv_gw Up 14h, cc4101 Up 14h, dsv4p_nv40066 Up 2d, /health 40006/4101/40066 全 200
> 上轮: R1040 (NOP, 主链 107/107=100%)

## 本轮 (R1041) 改动 + 依据 + 验证

### 改动: 无 (NOP。cc2 主链路连续第 149 轮 100% 干净, 主专属错误 0 rows; 本轮 window 内 4 条 bad 全属 hermes)

### 依据 (live 复核 2026-08-07 CST + 注入轮前链路分析 17:50 CST)

- 30min cc4101-primary (主 nv_gw:40006) = **105/105 全 200 = 100% SR, 0 bad** (live `SELECT caller,status,count(*) ... WHERE caller='cc4101-primary'`:
  cc4101-primary|200|105)。注入窗口与 live 复核一致, 全 200。
- 主链专属错误 (caller=cc4101-primary, status!=200) = **0 rows** (scoped 错误分组为空)。
- 本轮 window 内 nv_requests 总 bad = 4 条 (zombie_empty_completion ×3 + NVStream_IncompleteRead ×1),
  经 DB live `SELECT caller,error_type,count(*) ... WHERE status!=200 ... GROUP BY 1,2` 判定全属 **hermes** 越界宿主。
- fallback (cc_requests 30min) = **0 次 / 0.0%** (106 request, SR=100.0%)。
- 主链当前首代模型 = **dsv4f0731_nv** (cc4101.PRIMARY_UPSTREAM_MODEL), 无 tier 降级/无 key 疲劳。
- nv_tier_attempts per-key: **非成功 0 rows** (30min 无任何 key 错误, 无 RemoteDisconnected/execute_failed,
  比上轮 R1040 偶发 k2/k3 RemoteDisconnected 更干净 — 本轮连 key 层瞬态错误都没有)。
- buffer 日志: 本轮 window 内全部 cc4101-primary 请求 attempt=1 verdict=success 直接 flush
  (elapsed 0.9s~12s, 无 backoff 无重试无缓冲耗尽), buffer 零吸收需要。

### 本轮数据

| 指标 | 值 | 状态 |
|---|---|---|
| 主 nv_gw(40006) cc4101-primary | **105/105 = 100% SR, 0 bad** (live 查询) | ✅ |
| 主链专属错误 (caller=cc4101-primary) | **0 rows** | ✅ |
| nv_requests 总 bad (非 200) | 4 条 (zombie_empty_completion×3/NVStream_IncompleteRead×1), 全属 hermes, 主链 0 | ✅(主链) |
| 30min cc_requests | 106 request, fallback 0 次 (0.0%), SR=100.0% | ✅ |
| nv_tier_attempts 非成功 | **0 rows** (30min 无任何 key 错误) | ✅ |
| buffer | 全 request 1 attempt success flush, 零重试零耗尽 | ✅ |
| 容器 | nv_gw Up 14h, cc4101 Up 14h, dsv4p_nv40066 Up 2d, /health 40006/4101/40066 全 200 | ✅ |

### 验证
- docker exec logs_db psql: `SELECT caller,status,count(*) ... WHERE caller='cc4101-primary'` → cc4101-primary 105 行全 200, 无 bad。
- `SELECT caller,error_type,count(*) FROM nv_requests WHERE status!=200 ... GROUP BY 1,2` → 4 bad 全属 hermes
  (zombie_empty_completion×3/NVStream_IncompleteRead×1), 主链专属错误 0 rows。
- `SELECT count(*),sum(case when status=200 then 1 else 0 end),sum(case when coalesce(fallback_triggered,false) then 1 else 0 end) FROM cc_requests` → 106/106/0 (100.0% SR, 0.0% fallback)。
- `SELECT nv_key_idx,error_type,count(*) FROM nv_tier_attempts` → **0 rows 非成功**, 各 key 全 pexec_success。
- docker logs nv_gw --since 30m grep BUFFER- → 全 attempt=1 success flush, 无重试, 无缓冲耗尽。
- health: 40006/4101/40066 全 200; 容器 nv_gw Up 14h, cc4101 Up 14h, dsv4p_nv40066 Up 2d。

### 关键判断
cc2 主链路连续第 **149** 轮 (R893-R1041) 100% SR 干净, 主链专属错误 0 rows。
本轮 4 条 bad (zombie_empty_completion×3/NVStream_IncompleteRead×1) 归属全属 **hermes** 越界宿主, 经 caller 铁证与主链 host 分离完全干净 — 主链 105/105 全 200。
fallback 0 次 (0.0%), 无新 cc2 主链错误类, 无持久 key 疲劳。
**tier 层本轮 0 错误** (nv_tier_attempts 非成功 0 rows), buffer 零重试零吸收 — 链路处于最健康状态。
**不改码**: ①主链 SR 100% + 专属错误 0 行, 无优化需求; ②本轮 bad 全属 hermes 越界, 主链无根因可查;
③参数处于稳态, 无参数可调。

## 下一步
- 保持 NOP 观察, 主链 dsv4f0731_nv 为首代, 无需参数改动。
- 后续窗口继续确认 hermes 越界 bad (502/NVStream_IncompleteRead/zombie_empty_completion) 是否持续与主链隔离 (caller JOIN)。

## 容器健康
- nv_gw Up 14h, cc4101 Up 14h, dsv4p_nv40066 Up 2d; /health 40006/4101/40066 全 200。