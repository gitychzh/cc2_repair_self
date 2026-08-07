# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: **R1051 (NOP 巡检轮/不改码 — cc2 主链路连续第 159 轮 100% 干净; 主链专属错误 0 rows; fallback 0 次)**
> cc4101-primary (主 nv_gw:40006) 复核 30min = **111/111 = 100% SR, 0 bad** (注入链路分析);
> cc4101-primary 专属错误 = **0 rows** (scoped 错误分组唯一 status=200);
> nv_requests 总 bad = 2 (zombie_empty_completion×2 502), 全属 hermes 越界宿主;
> fallback (cc_requests 30min) = **0 次 / 0.0%** (主链 111/111 全 200);
> 容器 (/health 复核): nv_gw Up 15h, cc4101 Up 15h, nv_gw_stable Up 5d+, /health 40006/4101/40066 全 200
> 上轮: R1050 (NOP, 主链 110/110=100%)

## 本轮 (R1051) 改动 + 依据 + 验证

### 改动: 无 (NOP。cc2 主链路连续第 159 轮 100% 干净, 主链专属错误 0 rows; 本轮 window 内 2 条 bad 全属 hermes)

### 依据 (注入轮前链路分析 18:28 CST + /health 复核 2026-08-07)

- 30min cc4101-primary (主 nv_gw:40006) = **111/111 全 200 = 100% SR, 0 bad** (注入链路总览:
  cc4101-primary|dsv4f0731_nv|200|111, 无任何非 200)。
- 主链专属错误 (caller=cc4101-primary, status!=200) = **0 rows** (scoped 分组唯一 status=200, 无 error_type)。
- 本轮 window 内 nv_requests 总 bad = 2 条 (zombie_empty_completion ×2), 链路总览 caller×model×status 判定均属 **hermes**
  (this=hermes|dsv4f0731_nv|502|2, cc4101-primary 无任何非 200)。
- fallback (cc_requests 30min) = **0 次 / 0.0%** (fallback 发生率 f|184, 注入总览)。
- 主链当前首代模型 = **dsv4f0731_nv** (cc4101.PRIMARY_UPSTREAM_MODEL), 无 tier 降级/无 key 疲劳。
- nv_tier_attempts (dsv4f0731_nv, 30min) = k0-k4 全 pexec_success (22/23/21/21/24) — 无 tier 层错误。
- 30min nv_gw buffer/wait/keymanager 日志: 无 (零 buffer 吸收需要, 全 request attempt=1 直接成功)。
- /health 复核: 40006/4101/40066 全 200; 容器 nv_gw Up 15h, cc4101 Up 15h, nv_gw_stable Up 5d+。

### 本轮数据

| 指标 | 值 | 状态 |
|---|---|---|
| 主 nv_gw(40006) cc4101-primary | **111/111 = 100% SR, 0 bad** | ✅ |
| 主链专属错误 (caller=cc4101-primary) | **0 rows** | ✅ |
| nv_requests 总 bad (非 200) | 2 条 (zombie_empty_completion×2 502), 全属 hermes, 主链 0 | ✅(主链) |
| 30min cc_requests | fallback 0 次 (0.0%), 主链 111/111 全 200 | ✅ |
| nv_tier_attempts (dsv4f0731_nv) | k0-k4 全 pexec_success (22/23/21/21/24), 无 tier 错误 | ✅ |
| buffer | 30min 无 buffer/wait/keymanager 日志, 零吸收需要 | ✅ |
| 容器 | nv_gw Up 15h, cc4101 Up 15h, nv_gw_stable Up 5d+, /health 40006/4101/40066 全 200 | ✅ |

## 下一步
- 保持 NOP 观察, 主链 dsv4f0731_nv 首代, 参数稳态无可调。
- 持续确认 hermes 越界 bad (zombie_empty_completion/502) 与主链 host 分离 (caller JOIN)。
- 关注偶发 RemoteDisconnected 是否演成持久疲劳 (单 key 连续多轮 100% 失败再考虑 KEY_FID_BIND 换 fid)。

## 参数快照 (2026-08-07, 与上轮 R1050 一致, 未动)
- cc4101: PRIMARY_UPSTREAM_URL=http://nv_gw:40006/v1/messages, PRIMARY_UPSTREAM_MODEL=dsv4f0731_nv,
  FALLBACK_UPSTREAM_URL=http://ms_gw:40007/v1/chat/completions, FALLBACK_UPSTREAM_MODEL=glm5_2_ms,
  CC4101_STREAM_TOTAL_DEADLINE_S=470, PRIMARY_HEADER_TIMEOUT=400, CC4101_PRIMARY_FAIL_THRESHOLD=3, CC4101_PRIMARY_SKIP_S=30,
  UPSTREAM_TIMEOUT=130, UPSTREAM_IDLE_TIMEOUT=150
- nv_gw: NVU_DISABLE_MS_FALLBACK=0, NVU_PEER_FB_SKIP_MODELS=glm5_2_nv,dsv4p_nv, UPSTREAM_TIMEOUT=90,
  NV_INTEGRATE_KEY_COOLDOWN_S=90, KEY_COOLDOWN_S=30, NVU_FORCE_STREAM_UPGRADE=0, NVU_FORCE_STREAM_UPGRADE_TIMEOUT=150,
  TIER_TIMEOUT_BUDGET_S=180, TIER_COOLDOWN_S=180, MIN_OUTBOUND_INTERVAL_S=10,
  NVU_BUFFER_CALLERS=cc4101-primary,openclaw2, NVU_CALLER_KEY_MAP=hermes:2;openclaw:3;opencode:4
- 5key (k0-k4) × 5 US IP (hysteria2), 全 bind fid; Buffer 5 attempts × 90s; KeyManager 429→120-600s 指数退避