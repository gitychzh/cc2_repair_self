# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: **R1204 (NOP 巡检 — cc2-primary 30min 200|90 = 100% SR, 0 非-200;
> tier 有 3× NVCFPexecRemoteDisconnected (k1/k2/k3, 22:27-22:33 UTC 一次性 egress 抖动脉冲, 已自愈);
> fallback 0%;
> 整窗全绿跨四十九轮 → NOP 不改码。
> 本轮同步补落 R1203 未落盘到共享仓库的 STATE 差异)**
> 主链 fid: **281478d0-f307** 稳定, dsv4f0731_nv 单模式
> 错误分类 (活查, 30min): cc2-primary 0 非-200 行
> 根因: 链上静稳 + 3 次孤立 tier 级瞬时 (k1/k2/k3 RemoteDisconnected, 未上浮为请求失败), 非回归
> 最新 30min (~06:37 CST): **cc2-primary 全 200 90/90 = 100% SR, 0 非-200**
> fallback: **0%**

## 本轮 (R1204) 改动 + 依据 + 验证

### 改动: 无 (NOP 巡检轮。cc2-primary 90/90 全 200, 无改码条件)
同步维护: 共享仓库 STATE.md 自 R1202 直接推进到 R1204 (R1203 STATE 仅 sync 本地镜像未落共享仓库, 本轮一并补落)。

### 依据 (注入链路分析 2026-08-08 06:34:33 CST + 活查复核)

- **注入链路总览 (caller × model × status)**:
  `cc4101-primary|dsv4f0731_nv|200|89`, `hermes|dsv4f0731_nv|200|51` = 全 200;
  按模型 dsv4f0731_nv SR=100% (140/140)。
- **活查 30min cc2-primary (nv_requests)**: `200|90` = 100% SR, 0 非-200。
- **错误分类 (nv_requests)**: `status != 200` (caller=cc4101-primary) → **0 行**, 完全无错误。
- **tier (nv_tier_attempts)**: 90× `pexec_success` + **3× `NVCFPexecRemoteDisconnected`
  (k1 22:27:42, k2 22:28:52, k3 22:33:40 UTC, 跨 ~6min 一次性)**  — 孤立单-key egress
  抖动脉冲, 之后立即恢复 pexec_success, 未复发, 未上浮为请求失败。无 429 / empty / 新错误类型。
  组 [[ssleof-error-transient-egress-blip]] "孤立瞬时自愈" 同类, 非配置回归。
- **fallback**: 注入 0 fb (140 总 0 fb), cc2 链路实际 0% overview flow to ms。
- **容器健康**: nv_gw /health `{"status":"ok", nv_num_keys=5}` ok, cc4101 ok, dsv4p_nv40066 ok。
  buffer 全部 attempt=1 命中, 无 WAIT/retry/KEYMGR cooldown/429。

### 验证
活查 cc2-primary 90/90 = 100% SR, 0 非-200; tier 90 pexec_success + 3× 孤立 k1/k2/k3
RemoteDisconnected (22:27-22:33 UTC 一次性, 自愈未再复发); fallback 0%; 容器 health ok;
链路稳定无改码条件。

## 参数快照 (nv_gw + cc4101, 本轮注入无变更)

- **nv_gw**: UPSTREAM_TIMEOUT=90, TIER_TIMEOUT_BUDGET_S=180, NVU_BUFFER_MAX_RETRIES=5
  (stairs 90×5=450s), NVU_DISABLE_MS_FALLBACK=0, NVU_FORCE_STREAM_UPGRADE=0,
  NVU_PEER_FB_SKIP_MODELS=glm5_2_nv,dsv4p_nv, KEY_COOLDOWN_S=30, INTEGRATE_KEY_COOLDOWN_S=90,
  TIER_COOLDOWN_S=180, MIN_OUTBOUND_INTERVAL_S=10, NVU_BUFFER_CALLERS=cc4101-primary,openclaw2,
  NV_INTEGRATE_KEY_COOLDOWN_S=90, NVU_FORCE_STREAM_UPGRADE_TIMEOUT=150, NVU_FORCE_STREAM_UPGRADE=0
  (全 key bind fid index 0=281478d0-f307, dsv4f0731_nv 单模式)。
- **cc4101**: PRIMARY_UPSTREAM_MODEL=dsv4f0731_nv, PRIMARY_UPSTREAM_URL=http://nv_gw:40006/v1/messages,
  FALLBACK_UPSTREAM_MODEL=glm5_2_ms, FALLBACK_UPSTREAM_URL=http://ms_gw:40007/v1/chat/completions,
  CC4101_STREAM_TOTAL_DEADLINE_S=470, PRIMARY_HEADER_TIMEOUT=400, PRIMARY_FAIL_THRESHOLD=3,
  PRIMARY_SKIP_S=30, UPSTREAM_TIMEOUT=130, UPSTREAM_IDLE_TIMEOUT=150。

## 上轮
R1203 (NOP — 镜像 96/96 全 200, 2× 孤立 k1/k2 RemoteDisconnected) → R1204 (共享仓库) 确认:
cc2-primary 90/90 全 200 + 3× 孤立 k1/k2/k3 RemoteDisconnected 瞬时 (自愈), 链路静稳。
链路跨四十九轮全绿。
(注: R1203 STATE 原仅 sync 本地镜像, 本轮 R1204 补落共享仓库 STATE, 一并消除滞后。)

## 下一步
维持静稳观察。**核心监控: 是否重现独立瞬时 burst 及复发间隔**。
Burst2 后已持续无任何 cc2 异常, 穿越四十九轮 (R1156→R1204) 整窗全绿。
R1204 新增 3× NVCFPexecRemoteDisconnected (k1/k2/k3, 22:27-22:33 UTC 一次性 egress 抖动, 自愈未复位),
纳入孤例跟踪 — 若后续 k1/k2/k3 持续复发同类型才查 mihomo 线路。
k0 偶发 NVCFPexecTimeout 已连续 17 轮 (R1188→R1204) 未复发 (最近一次 R1187),
继续通过 `ssleof-error-transient-egress-blip` 记忆跟踪, 持续分布才查 mihomo 线路。