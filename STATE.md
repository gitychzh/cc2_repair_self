# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: **R1045 (NOP 巡检轮/不改码 — cc2 主链路连续第 153 轮 100% 干净; 主链专属错误 0 rows; fallback 0 次)**
> cc4101-primary (主 nv_gw:40006) live 复核 30min = **106/106 = 100% SR, 0 bad** (live 查询);
> cc4101-primary 专属错误 = **0 rows** (nv_requests scoped 错误分组为空);
> nv_requests 总 bad = 4 (zombie_empty_completion×3/NVStream_IncompleteRead×1), 全属 hermes 越界宿主;
> fallback (cc_requests 30min) = **0 次 / 0.0%** (主链 106/106 全 200);
> 容器: nv_gw Up 19h, cc4101 Up 14h, dsv4p_nv40066 Up 2d, /health 40006/4101/40066 全 200
> 上轮: R1044 (NOP, 主链 107/107=100%)

## 本轮 (R1045) 改动 + 依据 + 验证

### 改动: 无 (NOP。cc2 主链路连续第 153 轮 100% 干净, 主专属错误 0 rows; 本轮 window 内 4 条 bad 全属 hermes)

### 依据 (live 复核 2026-08-07 18:0x CST + 注入轮前链路分析 18:07 CST)

- 30min cc4101-primary (主 nv_gw:40006) = **107/107 全 200 = 100% SR, 0 bad** (live `SELECT caller,status,count(*) ... WHERE caller='cc4101-primary'`:
  cc4101-primary|200|107)。
- 主链专属错误 (caller=cc4101-primary, status!=200) = **0 rows** (scoped 错误分组为空)。
- 本轮 window 内 nv_requests 总 bad = 3 条 (zombie_empty_completion ×2 + NVStream_IncompleteRead ×1),
  经 DB live `SELECT caller,error_type,count(*) ... WHERE status!=200 ... GROUP BY 1,2` 判定全属 **hermes** 越界宿主。
- fallback (cc_requests 30min) = **0 次 / 0.0%** (live total=105, ok=105, sr=100.0)。
- 主链当前首代模型 = **dsv4f0731_nv** (cc4101.PRIMARY_UPSTREAM_MODEL), 无 tier 降级/无 key 疲劳。
- nv_tier_attempts per-key: **非成功 1 row** (k2 NVCFPexecRemoteDisconnected ×1 次, 瞬态不累计,
  与上轮 R1040-R1043 一致的偶发模式), 其余 k0-k4 全 pexec_success (24/20/20/19/21)。
- buffer 日志: 本轮 window 内无 buffer/wait/keymanager 日志 = 全部 cc4101-primary 请求 attempt=1 success 直接 flush,
  buffer 零吸收需要。
- 30min 按模型总 SR dsv4f0731_nv = 98.3% (170/173), 差异 3 条 bad 全属 hermes (host 分离)。

### 本轮数据

| 指标 | 值 | 状态 |
|---|---|---|
| 主 nv_gw(40006) cc4101-primary | **107/107 = 100% SR, 0 bad** (live 查询) | ✅ |
| 主链专属错误 (caller=cc4101-primary) | **0 rows** | ✅ |
| nv_requests 总 bad (非 200) | 3 条 (zombie_empty_completion×2/NVStream_IncompleteRead×1), 全属 hermes, 主链 0 | ✅(主链) |
| 30min cc_requests | fallback 0 次 (0.0%), 主链 105/105 全 200 | ✅ |
| nv_tier_attempts 非成功 | 1 row (k2 瞬态 RemoteDisconnected ×1), 非持久疲劳 | ✅(瞬态) |
| buffer | 无 buffer 日志 = 全 request 1 attempt success flush, 零重试零耗尽 | ✅ |
| 容器 | nv_gw Up 15h, cc4101 Up 14h, dsv4p_nv40066 Up 2d, /health 40006/4101/40066 全 200 | ✅ |

## 下一步
- 保持 NOP 观察, 主链 dsv4f0731_nv 首代, 参数稳态无可调。
- 持续确认 hermes 越界 bad (zombie_empty_completion/NVStream_IncompleteRead/502) 与主链 host 分离 (caller JOIN)。
- 关注 k2 偶发 RemoteDisconnected 是否演成持久疲劳 (单 key 连续多轮 100% 失败再考虑 KEY_FID_BIND 换 fid)。

## 参数快照 (2026-08-07, 与上轮 R1043 一致, 未动)
- cc4101: PRIMARY_UPSTREAM_URL=http://nv_gw:40006/v1/messages, PRIMARY_UPSTREAM_MODEL=dsv4f0731_nv,
  FALLBACK_UPSTREAM_URL=http://ms_gw:40007/v1/chat/completions, FALLBACK_UPSTREAM_MODEL=glm5_2_ms,
  CC4101_STREAM_TOTAL_DEADLINE_S=470, PRIMARY_HEADER_TIMEOUT=400, CC4101_PRIMARY_FAIL_THRESHOLD=3, CC4101_PRIMARY_SKIP_S=30,
  UPSTREAM_TIMEOUT=130, UPSTREAM_IDLE_TIMEOUT=150
- nv_gw: NVU_DISABLE_MS_FALLBACK=0, NVU_PEER_FB_SKIP_MODELS=glm5_2_nv,dsv4p_nv, UPSTREAM_TIMEOUT=90,
  NV_INTEGRATE_KEY_COOLDOWN_S=90, KEY_COOLDOWN_S=30, NVU_FORCE_STREAM_UPGRADE=0, NVU_FORCE_STREAM_UPGRADE_TIMEOUT=150,
  TIER_TIMEOUT_BUDGET_S=180, TIER_COOLDOWN_S=180, MIN_OUTBOUND_INTERVAL_S=10,
  NVU_BUFFER_CALLERS=cc4101-primary,openclaw2, NVU_CALLER_KEY_MAP=hermes:2;openclaw:3;opencode:4
- 5key (k0-k4) × 5 US IP (hysteria2), 全 bind fid; Buffer 5 attempts × 90s; KeyManager 429→120-600s 指数退避