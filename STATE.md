# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: **R1194 (NOP 巡检 — 活查 30min cc4101-primary 200|103 = 100% SR, 0 非-200;
> tier 活查 103 全 pexec_success 0 error
> (连续七轮无瞬时); fallback 0%;
> buffer 全 attempt-1 direct flush 无退避无 WAIT;
> 整窗全绿跨三十七轮 → NOP 不改码)**
> 主链 fid: **281478d0-f307** 稳定, dsv4f0731_nv 单模式
> 错误分类 (活查, 30min): 0 非-200 行
> 根因: 链上静稳, 全窗 0 错误
> 最新 30min (~05:37 CST): **cc2-primary 全 200 103/103 = 100% SR, 0 非-200**
> fallback: **0%**

## 本轮 (R1194) 改动 + 依据 + 验证

### 改动: 无 (NOP 巡检轮。cc2 整窗 103/103 全 200, 无改码条件)

### 依据 (注入链路分析 2026-08-08 05:36:33 CST + 活查 DB 复核)

- **活查 30min cc4101-primary**: `200|103` = 100% SR, 0 非-200
  (注入同窗 cc2 105, 活查复核 103, 均为当前整窗)。
- **错误分类 (nv_requests)**: 活查 `status != 200` → **0 行** (完全无错误)。
- **tier (nv_tier_attempts)**: 活查 103 → 全 `pexec_success`, **0 error**。
  - 连续第七轮 (R1188→R1194) 完全无瞬时: R1187 的 k0 单次 NVCFPexecTimeout
    已持续自愈、本轮未复发, 属固定 egress 抖动非回归 (记忆
    `ssleof-error-transient-egress-blip` / `k3-transient-execute-failed-self-heal`)。
  - 无 429 / empty / 新错误类型。
- **fallback**: 注入 f=168 (总线), 均档; 无实际触发 ms fallback (SR 100%)。
- **buffer 日志 (docker logs nv_gw --since 30m)**: 最近日志全 attempt-1 direct flush
  (`success_text` / `success_tool_call`, elapsed 1-17s, flush 1882b/2817b/52278b/8002b),
  无退避、无 WAIT-KEYMGR、无 buffer_exhausted。

### 验证
活查 cc4101-primary 103/103 = 100% SR, 0 非-200; tier 活查 103 全 pexec_success 0 error;
fallback 0%; buffer 全 attempt-1 direct flush 无退避无 WAIT;
nv_gw (Up 26h)/cc4101 (Up 26h) health ok; 链路稳定无改码条件。

## 参数快照 (nv_gw + cc4101, 本轮注入无变更)

- **nv_gw**: UPSTREAM_TIMEOUT=90, TIER_TIMEOUT_BUDGET_S=180, NVU_BUFFER_MAX_RETRIES=5
  (stairs 90×5=450s), NVU_DISABLE_MS_FALLBACK=0, NVU_FORCE_STREAM_UPGRADE=0,
  NVU_PEER_FB_SKIP_MODELS=glm5_2_nv,dsv4p_nv, KEY_COOLDOWN_S=30, INTEGRATE_KEY_COOLDOWN_S=90,
  TIER_COOLDOWN_S=180, MIN_OUTBOUND_INTERVAL_S=10, NVU_BUFFER_CALLERS=cc4101-primary,openclaw2,
  (全 key bind fid index 0=281478d0-f307, dsv4f0731_nv 单模式)。
- **cc4101**: PRIMARY_UPSTREAM_MODEL=dsv4f0731_nv, PRIMARY_UPSTREAM_URL=http://nv_gw:40006/v1/messages,
  FALLBACK_UPSTREAM_MODEL=glm5_2_ms, FALLBACK_UPSTREAM_URL=http://ms_gw:40007/v1/chat/completions,
  CC4101_STREAM_TOTAL_DEADLINE_S=470, PRIMARY_HEADER_TIMEOUT=400, PRIMARY_FAIL_THRESHOLD=3,
  PRIMARY_SKIP_S=30, UPSTREAM_TIMEOUT=130, UPSTREAM_IDLE_TIMEOUT=150。

## 上轮
R1193 (NOP — 活查 102/102 全 200, 0 错误) → R1194 确认:
活查 103/103 全 200, 0 错误, 链路持续静稳无新事件。
链路跨三十七轮全绿。

## 下一步
维持静稳观察。**核心监控: 是否重现独立瞬时 burst 及复发间隔**。
Burst2 后已持续无任何 cc2 异常, 穿越三十七轮 (R1158→R1194) 整窗全绿。
k0 偶发 NVCFPexecTimeout 已连续 7 轮 (R1188→R1194) 未复发 (最近一次 R1187),
继续通过 `ssleof-error-transient-egress-blip` 记忆跟踪, 持续分布才查 mihomo 线路。