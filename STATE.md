# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: **R1067 (NOP 巡检轮/不改码 — cc2 主链 111/111=100% SR, 0 bad; fallback 0; 唯一 bads 均 hermes 越界宿主非 cc2 范围; 连续多轮达完全健康基线)**
> cc4101-primary (主 nv_gw:40006) 实测 30min = **111/111 = 100% SR, 0 bad**;
> dsv4f0731_nv 整体 SR=98.0% (150/153) — 3 个 502 全属 hermes 越界宿主, 非主链;
> 30min cc_requests = **113/113 = 100%, fallback 0 次 / 0.0%** (DB 复核);
> 错误分类: zombie_empty_completion×3 (全 hermes 越界宿主, 非 cc2 范围);
> buffer 日志无 fail/WAIT/KEYMGR;
> 容器 (/health 复核): nv_gw Up 16h, cc4101 Up 16h, /health 40006/4101 全 200
> 上轮: R1066 (NOP, 主链 118/118=100%)

## 本轮 (R1067) 改动 + 依据 + 验证

### 改动: 无 (NOP。cc2 主链 111/111=100% 0 bad, 无新错误, 无参数可调; 唯一 bads 均为 hermes 越界宿主, 非 cc2 范围)

### 依据 (注入轮前链路分析 19:37 CST + DB/容器复核 2026-08-07)

- **30min cc4101-primary (主 nv_gw:40006) = 111/111 = 100% SR, 0 bad**。
- dsv4f0731_nv 整体 SR=98.0% (150/153) — 3 个 502 全属 hermes 越界宿主 (非主链)。
- 30min cc_requests = **113 ok / 113 = 100% SR, fallback 0 次 / 0.0%** (DB 复核)。
- 错误分类: zombie_empty_completion×3 (全 hermes 越界宿主, 非 cc2 范围)。
- buffer 日志无 fail/WAIT/KEYMGR。
- /health 实测: 40006/4101 全 200; 容器 nv_gw Up 16h, cc4101 Up 16h, nv_gw_stable Up 5d.

### 本轮数据

| 指标 | 值 | 状态 |
|---|---|---|
| 主 nv_gw(40006) cc4101-primary | **111/111 = 100% SR, 0 bad** | ✅ |
| dsv4f0731_nv 整体 | 150/153 = 98.0% (3×502 全 hermes 越界宿主) | ✅(非主链) |
| 30min cc_requests | 113/113 = 100% SR, fallback 0 次 (0.0%) | ✅ |
| hermes (越界宿主, 非 cc2 范围) | zombie_empty_completion×3 | ⚠️(非主链) |
| buffer 日志 | 无 fail/WAIT/KEYMGR | ✅ |
| 容器 | nv_gw Up 16h, cc4101 Up 16h, /health 40006/4101 全 200 | ✅ |

## 下一步
- 保持 NOP 观察。主链连续多轮 0 bad 已抵达"完全健康基线"。
- 跟踪 SSLEOFError 密度: 仅当 >10 次/10min 且同窗多请求 502 才排查 egress/proxy 出向 mihomo; 当前低频常态, 无需动作。
- 单 key 连续多轮 100% 失败才考虑 KEY_FID_BIND 换 fid; 当前主链 fid 281478d0 全 pexec_success, 无此需。

## 参数快照 (2026-08-07, 与上轮 R1066 一致, 未动)
- cc4101: PRIMARY_UPSTREAM_URL=http://nv_gw:40006/v1/messages, PRIMARY_UPSTREAM_MODEL=dsv4f0731_nv,
  FALLBACK_UPSTREAM_URL=http://ms_gw:40007/v1/chat/completions, FALLBACK_UPSTREAM_MODEL=glm5_2_ms,
  CC4101_STREAM_TOTAL_DEADLINE_S=470, PRIMARY_HEADER_TIMEOUT=400, CC4101_PRIMARY_FAIL_THRESHOLD=3, CC4101_PRIMARY_SKIP_S=30,
  UPSTREAM_TIMEOUT=130, UPSTREAM_IDLE_TIMEOUT=150
- nv_gw: NVU_DISABLE_MS_FALLBACK=0, NVU_PEER_FB_SKIP_MODELS=glm5_2_nv,dsv4p_nv, UPSTREAM_TIMEOUT=90,
  NV_INTEGRATE_KEY_COOLDOWN_S=90, KEY_COOLDOWN_S=30, NVU_FORCE_STREAM_UPGRADE=0, NVU_FORCE_STREAM_UPGRADE_TIMEOUT=150,
  TIER_TIMEOUT_BUDGET_S=180, TIER_COOLDOWN_S=180, MIN_OUTBOUND_INTERVAL_S=10,
  NVU_BUFFER_CALLERS=cc4101-primary,openclaw2, NVU_CALLER_KEY_MAP=hermes:2;openclaw:3;opencode:4
- Buffer 5 attempts × 90s = 450s; KeyManager 429→120-600s 指数退避, RemoteDisconnected→5-10s 短惩罚
