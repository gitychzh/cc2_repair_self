# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: **R1042 (NOP 巡检轮/不改码 — cc2 主链路连续第 150 轮 100% 干净; 主链专属错误 0 rows; fallback 0 次)**
> cc4101-primary (主 nv_gw:40006) live 复核 30min = **104/104 = 100% SR, 0 bad** (live 查询);
> cc4101-primary 专属错误 = **0 rows** (nv_requests scoped 错误分组为空);
> nv_requests 总 bad = 4 (zombie_empty_completion×3/NVStream_IncompleteRead×1), 全属 hermes 越界宿主;
> fallback (cc_requests 30min) = **0 次 / 0.0%** (103 request, 103 ok, SR=100.0%);
> 容器: nv_gw Up 19h, cc4101 Up 14h, dsv4p_nv40066 Up 5d, /health 40006/4101/40066 全 200
> 上轮: R1041 (NOP, 主链 105/105=100%)

## 本轮 (R1042) 改动 + 依据 + 验证

### 改动: 无 (NOP。cc2 主链路连续第 150 轮 100% 干净, 主专属错误 0 rows; 本轮 window 内 4 条 bad 全属 hermes)

### 依据 (live 复核 2026-08-07 CST + 注入轮前链路分析 17:54 CST)

- 30min cc4101-primary (主 nv_gw:40006) = **104/104 全 200 = 100% SR, 0 bad** (live `SELECT caller,status,count(*) ... WHERE caller='cc4101-primary'`:
  cc4101-primary|200|104)。注入窗口与 live 复核一致, 全 200。
- 主链专属错误 (caller=cc4101-primary, status!=200) = **0 rows** (scoped 错误分组为空)。
- 本轮 window 内 nv_requests 总 bad = 4 条 (zombie_empty_completion ×3 + NVStream_IncompleteRead ×1),
  经 DB live `SELECT caller,error_type,count(*) ... WHERE status!=200 ... GROUP BY 1,2` 判定全属 **hermes** 越界宿主。
- fallback (cc_requests 30min) = **0 次 / 0.0%** (103 request, SR=100.0%)。
- 主链当前首代模型 = **dsv4f0731_nv** (cc4101.PRIMARY_UPSTREAM_MODEL), 无 tier 降级/无 key 疲劳。
- nv_tier_attempts per-key: **非成功 2 rows** (k2/k3 NVCFPexecRemoteDisconnected 各 1 次, 瞬态不累计,
  与上轮 R1040/R1041 一致的偶发模式), 其余 k0-k4 全 pexec_success (24/20/20/19/20)。
- buffer 日志: 本轮 window 内全部 cc4101-primary 请求 attempt=1 verdict=success_text/success_tool_call 直接 flush
  (elapsed 2s~14s, 无 backoff 无重试无缓冲耗尽), buffer 零吸收需要。

### 本轮数据

| 指标 | 值 | 状态 |
|---|---|---|
| 主 nv_gw(40006) cc4101-primary | **104/104 = 100% SR, 0 bad** (live 查询) | ✅ |
| 主链专属错误 (caller=cc4101-primary) | **0 rows** | ✅ |
| nv_requests 总 bad (非 200) | 4 条 (zombie_empty_completion×3/NVStream_IncompleteRead×1), 全属 hermes, 主链 0 | ✅(主链) |
| 30min cc_requests | 103 request, fallback 0 次 (0.0%), SR=100.0% | ✅ |
| nv_tier_attempts 非成功 | 2 rows (k2/k3 瞬态 RemoteDisconnected 各 1), 非持久疲劳 | ✅(瞬态) |
| buffer | 全 request 1 attempt success flush, 零重试零耗尽 | ✅ |
| 容器 | nv_gw Up 19h, cc4101 Up 14h, dsv4p_nv40066 Up 5d, /health 40006/4101/40066 全 200 | ✅ |

### 验证
- docker exec logs_db psql: `SELECT caller,status,count(*) ... WHERE caller='cc4101-primary'` → cc4101-primary 104 行全 200, 无 bad。
- `SELECT caller,error_type,count(*) FROM nv_requests WHERE status!=200 ... GROUP BY 1,2` → 4 bad 全属 hermes
  (zombie_empty_completion×3/NVStream_IncompleteRead×1), 主链专属错误 0 rows。
- `SELECT count(*),sum(case when status=200 then 1 else 0 end),sum(case when coalesce(fallback_triggered,false) then 1 else 0 end) FROM cc_requests` → 103/103/0 (100.0% SR, 0.0% fallback)。
- `SELECT nv_key_idx,error_type,count(*) FROM nv_tier_attempts` → 仅 k2/k3 瞬态 RemoteDisconnected 各 1, 其余全 pexec_success。
- docker logs nv_gw --since 30m grep BUFFER- → 全 attempt=1 success flush, 无重试, 无缓冲耗尽。
- health: 40006/4101/40066 全 200; 容器 nv_gw Up 19h, cc4101 Up 14h, dsv4p_nv40066 Up 5d。

### 关键判断
cc2 主链路连续第 **150** 轮 (R893-R1042) 100% SR 干净, 主链专属错误 0 rows。
本轮 4 条 bad (zombie_empty_completion×3/NVStream_IncompleteRead×1) 归属全属 **hermes** 越界宿主, 经 caller 铁证与主链 host 分离完全干净 — 主链 104/104 全 200。
fallback 0 次 (0.0%), 无新 cc2 主链错误类, 无持久 key 疲劳。
**tier 层仅 k2/k3 偶发瞬态 RemoteDisconnected (各 1 次, 与历史模式一致, 不累计 conn_count)**, buffer 零重试零吸收 — 链路处于健康状态。
**不改码**: ①主链 SR 100% + 专属错误 0 行, 无优化需求; ②本轮 bad 全属 hermes 越界, 主链无根因可查;
③参数处于稳态, 无参数可调; ④k2/k3 瞬态不构成持久疲劳, 无须换 fid。

## 下一步
- 保持 NOP 观察, 主链 dsv4f0731_nv 为首代, 无需参数改动。
- 后续窗口继续确认 hermes 越界 bad (zombie_empty_completion/NVStream_IncompleteRead/502) 是否持续与主链隔离 (caller JOIN)。
- 关注 k2/k3 偶发 RemoteDisconnected 是否演变成持久疲劳 (若单 key 连续多轮 100% 失败再考虑 KEY_FID_BIND 换 fid b6029a96)。