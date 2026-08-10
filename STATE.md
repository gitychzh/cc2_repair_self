# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: **R1248 (内容改动 — 4 容器 (cc4101/hm4104/opclaw4103/oc4105) fallback 统一切到 ms_gw:40007 dsv4f0731_ms, 与 NVCF 账号解耦 实现跨供应商真备用; 用户手动密集请求待核验)**
> 主链 fid: **281478d0-f307** (dsv4f0731_nv), 现经 **dsvf0731_nv40666 容器** (40666)
> **链路 (R1248)**: cc → cc4101 (4101) → primary `dsvf0731_nv40666:40666/v1/messages` (dsv4f0731_nv, fid 281478d0, 单 fid + integrate 内部兜底) ✅ 200 (~2.6s)
> fallback → `ms_gw:40007/v1/messages` (**dsv4f0731_ms**, modelscope 7key 10variant, **SR 98.8%** 实测) ✅ 200 (ttfb ~1.3s)
> **agent 链路 (R1247 起, R1248 改 fallback)**: hermes→hm4104(4104)+openclaw→opclaw4103(4103)+opencode→oc4105(4105) → primary 40666(dsv4f0731) + fallback **ms_gw:40007(dsv4f0731_ms)**
> **R1248 动机**: 原 fallback(glm5_2_nv@nv_gw:40006) 与 primary 同挂 NVCF 同一批 key/账号, 账号级 429 时 fallback 被同款故障打败 (非真备用)。切 ms_gw 跨供应商。
> **glm5_2_nv new fid**: 3b9748d8 (ai-glm-5_2, ACTIVE) 替代死链 b1b22d03 (mn-tp8-b200 INACTIVE 404)。(glm5_2_nv 仍为 nv_gw 内部 модель, 不再是 4 容器 fallback)
> **改前数据锚点**: 40666 dsv4f0731 0.7-3.1s / 40006 glm5.2 新 fid ~7s (R1246 实测); ms_gw dsv4f0731_ms SR 98.8% (83/84, 24h); dsv4p_nv 已 EOL (NVCF 410 Gone 2026-08-07, 容器保留)。

## 本轮 (R1248) 改动 + 依据 + 验证

### 动机 (用户 + 数据): fallback 与 primary 同源 NVCF, 非真备用
- **问题**: 4 容器 primary 全走 `dsv4f0731_nv@40666` (NVCF), fallback 全走 `glm5_2_nv@nv_gw:40006` (NVCF)。
  两条链同挂 NVCF 同一批 5 个 key (k0~k4) / 同一账号。NVCF 限流是**账号级共享配额**:
  - 24h `key_cycle_429s`: dsv4f0731_nv 1110 次, glm5_2_nv 180 次, 同 5 key 同 `nvcf_pexec`。
  - 小时级: dsv4f0731 429 高 (09~11 点 92/122/109) 时 glm5_2 429 同高 (14/28/10); dsv4f0731 低 (16~20 点 22~38) 时 glm5_2 全 0。
  - **关键不对称**: 无任何小时 glm5_2 有 429 而 dsv4f0731 没有 (`g_without_d=0`)。
  - 秒级: 08:30:19 dsv4f0731 502 + 08:30:44/31:03 glm5_2 502 同波。
- **结论**: primary 被账号限流时, 原 fallback(glm5_2_nv) 同源同败 = 不是真的备用。切 ms_gw 跨供应商。

### 改动 (compose env, 4 容器 fallback 统一切 ms_gw:40007 + dsv4f0731_ms + ms-gw-token)
| 容器 | FALLBACK_URL | FALLBACK_MODEL | auth token |
|---|---|---|---|
| cc4101 | nv_gw:40006/v1/messages → **ms_gw:40007/v1/messages** | glm5_2_nv → **dsv4f0731_ms** | FALLBACK_UPSTREAM_TOKEN nv→ms-gw-token |
| hm4104 | nv_gw:40006/v1 → **ms_gw:40007/v1** | glm5_2_nv → **dsv4f0731_ms** | MS_GW_API_KEY nv→ms-gw-token |
| opclaw4103 | nv_gw:40006/v1 → **ms_gw:40007/v1** | glm5_2_nv → **dsv4f0731_ms** | MS_GW_API_KEY nv→ms-gw-token |
| oc4105 | nv_gw:40006/v1 → **ms_gw:40007/v1** | glm5_2_nv → **dsv4f0731_ms** | FALLBACK_API_KEY nv→ms-gw-token |

**认证变量注意 (cc-adapter config.py:70)**: `FALLBACK_API_KEY = os.environ.get("FALLBACK_API_KEY", MS_GW_API_KEY)`。
cc-adapter fallback 走 `_post_upstream(FALLBACK_URL, FALLBACK_MODEL, FALLBACK_API_KEY)`:
- hm4104/opclaw4103 未显式设 FALLBACK_API_KEY → 回落 MS_GW_API_KEY (改 MS_GW_API_KEY)。
- oc4105 显式设 FALLBACK_API_KEY=nv-gw-token → 覆盖 MS_GW_API_KEY (改 FALLBACK_API_KEY)。
- cc4101 走 routing.py:161 用 FALLBACK_UPSTREAM_TOKEN (改回 ms-gw-token)。
**不碰**: cx4102 (fallback 已禁用 none); ms_gw/nv_gw/dsvf40666 自身; HM1。

### 依据 (DB/实测)
- ms_gw health: role=ms_uni, num_keys=7, num_variants=10, models 含 `dsv4f0731_ms`, rr_counter `ms_dsv4f0731=2212`。
- `ms_requests.status='ok'` 24h: **dsv4f0731_ms SR 98.8%** (83/84), avg ~35s; glm5_2_ms SR 80% (12/15)。
  (正确字段是 `status='ok'`, 非 `resp_status` — 后者对 stream 不填充, 勿误读为 0%。)
- 端到端 curl: `/v1/messages` (cc4101 路径) 200 ttfb 1.3s; `/v1/chat/completions` (adapter 路径) 200 ttfb 1.4s。
- auth: `MSU_GATEWAY_API_KEY=ms-gw-token`; 无/错 token 均 401。

### 验证 (R1248 已通过部分; fallback 实地触发待用户密集请求后 DB 复核)
| 项目 | 结果 |
|---|---|
| ms_gw dsv4f0731_ms 端到端 | `/v1/messages` 200 (1.3s) + `/v1/chat/completions` 200 (1.4s) |
| compose config | `docker compose config --quiet` → **CONFIG VALID** |
| docker compose up -d | cc4101/opclaw4103/hm4104/oc4105 全 Recreated + Started |
| 4 容器 health | 全 HTTP 200, `fallback_url=http://ms_gw:40007/v1` |
| 4 容器 env 生效 | fallback URL/model/token 全确认切到 ms_gw/dsv4f0731_ms/ms-gw-token |
| 残留 nv_gw:40006 fallback | 无 (仅剩 cc4101 primary 注释 + cx4102 PRIMARY_URL, 均无关) |
| **待: fallback 实地触发** | ⏳ 用户手动密集请求 → 查 `nv_requests.fallback_occurred=true` + `fallback_to` 含 ms_gw / dsv4f0731_ms |

**上轮 (R1247) 已验证 (历史保留)**: 40666 dsv4f0731 200 (fid 281478d0), nv_gw glm5.2 200 (fid 3b9748d8, mode chain pexec→integrate), openclaw/hermes primary 200, fallback 200 (当时切到 nv_gw glm5_2, 已在本轮改走 ms_gw)。

## 参数快照 (R1248: fallback 通道已切 ms_gw dsv4f0731_ms, 实测 env)

- **nv_gw (40006)**: `NV_GLM52_MODE_CHAIN=pexec_us_rr,integrate_us_rr` (R1247 新增 integrate 兜底),
  `NVCF_GLM52_FUNCTION_ID=3b9748d8`, `KEY_FID_BIND=0:0;1:0;2:0;3:0;4:0` (全锁 pos0=3b9748d8),
  `NV_INTEGRATE_MODELS=glm5_2_nv`, `NVU_PEER_FB_SKIP_MODELS=glm5_2_nv` (R1246 删 dsv4p_nv),
  TIER_TIMEOUT_BUDGET_S=180, NVU_BUFFER_MAX_RETRIES=5 (stairs 90×5=450s),
  NVU_DISABLE_MS_FALLBACK=0, NVU_FORCE_STREAM_UPGRADE=0, NVU_FORCE_STREAM_UPGRADE_TIMEOUT=150,
  NVU_CALLER_KEY_MAP=hermes:2;openclaw:3;opencode:4。
- **dsvf0731_nv40666 (40666)**: `NVU_FID_DISCOVERY_ENABLED=1`, MODEL=dsv4f0731_nv, NAME_MATCH=deepseek-v4-flash,
  fid 281478d0 自动发现, **单 fid** (R1247 删 4 行多余 NVCF_FUNCTION_ID);
  `NVU_PEER_FB_SKIP_MODELS=glm5_2_nv,dsv4p_nv,dsv4f_nv,dsv4f0731_nv`,
  TIER_TIMEOUT_BUDGET_S=180, BUFFER_MAX_RETRIES=5, BUFFER_CALLERS=cc4101-fallback;
  `upstream.py:2577` gate 扩展 `dsv4f0731_nv` → pexec→integrate dynamic 兜底。
- **cc4101**: PRIMARY_UPSTREAM_MODEL=dsv4f0731_nv, PRIMARY_UPSTREAM_URL=http://dsvf0731_nv40666:40666/v1/messages,
  FALLBACK_UPSTREAM_MODEL=**dsv4f0731_ms**, FALLBACK_UPSTREAM_URL=http://**ms_gw:40007**/v1/messages, FALLBACK_UPSTREAM_TOKEN=ms-gw-token (R1248 改),
  CC4101_STREAM_TOTAL_DEADLINE_S=470, PRIMARY_HEADER_TIMEOUT=400, PRIMARY_FAIL_THRESHOLD=3,
  PRIMARY_SKIP_S=30, UPSTREAM_TIMEOUT=130, UPSTREAM_IDLE_TIMEOUT=150。
- **hm4104 (hermes)**: PRIMARY_URL=dsvf0731_nv40666:40666, PRIMARY_MODEL=dsv4f0731_nv,
  FALLBACK_URL=http://**ms_gw:40007**/v1, FALLBACK_MODEL=**dsv4f0731_ms**, MS_GW_API_KEY=ms-gw-token (R1248 改; 原 R1247 曾改 nv-gw-token)。
- **opclaw4103 (openclaw)**: PRIMARY_URL=dsvf0731_nv40666:40666, PRIMARY_MODEL=dsv4f0731_nv,
  FALLBACK_URL=http://**ms_gw:40007**/v1, FALLBACK_MODEL=**dsv4f0731_ms**, MS_GW_API_KEY=ms-gw-token (R1248 改; 原 R1247 曾改 nv-gw-token)。
- **oc4105 (opencode)**: PRIMARY_URL=dsvf0731_nv40666:40666, PRIMARY_MODEL=dsv4f0731_nv,
  FALLBACK_URL=http://**ms_gw:40007**/v1, FALLBACK_MODEL=**dsv4f0731_ms**, FALLBACK_API_KEY=ms-gw-token (R1248 改; 显式 FALLBACK_API_KEY 覆盖 MS_GW_API_KEY)。

## 上轮
R1247 (40666/nv_gw 各单 fid + integrate 内部兜底, 清理多余 fid, pexec vs integrate 实测, hermes+openclaw 两 agent 链路配置 + 端到端验证; 全通过)
→ **R1248 (4 容器 fallback 统一切 ms_gw:40007 dsv4f0731_ms, 与 NVCF 账号解耦 实现跨供应商真备用; 端到端 + health + env 验证通过, fallback 实地触发待用户密集请求后 DB 复核)**。

## 下一步
1. **用户手动密集请求 → 我拉 DB 复核 fallback**: 查 `nv_requests.fallback_occurred=true` 时 `fallback_to`/`fallback_tiers_used` 是否含 ms_gw / dsv4f0731_ms; `ms_requests` 新增 dsv4f0731 请求 caller 是否来自 4 容器 (非仅 curl)。
2. **fallback 触发率监控**: primary(40666 dsv4f0731) 失败时 fallback 走 ms_gw, 目标触发率 <5%; 各容器 SR 不应恶化。
3. **ms_gw dsv4f0731 SR 稳定**: 该 lane 24h SR 98.8%, 观察密集请求后是否维持; ms 平均 35s 比 NVCF 慢, 关注是否顶 fallback 预算 (hm4104 120s / opclaw 170s / oc4105 300s 均够)。
4. **fid 监控**: 40666 discovery fid 281478d0 与 nv_gw glm5.2 fid 3b9748d8 分布稳定 200 (glm5_2_nv 不再是 4 容器 fallback, 但 nv_gw 内部仍用)。