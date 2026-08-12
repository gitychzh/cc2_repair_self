# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: **R1249 (内容改动 — ① glm5_2_nv FID 动态健康切换: 5 候选 fid 全展开 + KEY_FID_BIND 清空 + discovery 开启 + probe 404 修复; ② NVU_ACTIVE_TIERS 模型白名单: 40006 只留 glm5_2_nv, 40666 只留 dsv4f0731_nv, 40066 只留 dsv4p_nv)**
> 主链 fid: **281478d0-f307** (dsv4f0731_nv), 现经 **dsvf0731_nv40666 容器** (40666)
> **链路 (R1248)**: cc → cc4101 (4101) → primary `dsvf0731_nv40666:40666/v1/messages` (dsv4f0731_nv, fid 281478d0, 单 fid + integrate 内部兜底) ✅ 200 (~2.6s)
> fallback → `ms_gw:40007/v1/messages` (**dsv4f0731_ms**, modelscope 7key 10variant, **SR 98.8%** 实测) ✅ 200 (ttfb ~1.3s)
> **agent 链路 (R1247 起, R1248 改 fallback)**: hermes→hm4104(4104)+openclaw→opclaw4103(4103)+opencode→oc4105(4105) → primary 40666(dsv4f0731) + fallback **ms_gw:40007(dsv4f0731_ms)**
> **R1249 动机**: ① 用户要求 glm5.2 fid 动态选择 (正在用的 fid 不可用 → 自动换健康 fid); 根因 KEY_FID_BIND 全钉 pos0 短路 func_health. ② 用户指定 40006 只部署 glm5_2_nv, dsv4f0731 只在 40666.
> **glm5_2_nv fid 候选 (R1249 全展开)**: pos0=3b9748d8(ai-glm-5_2), pos1=b6029a96, pos2=b1b22d03(回归 ACTIVE, 实测最快 1.6s), pos3=5532e90c, pos4=bfcf495b(实测稳 2.8s). KEY_FID_BIND 已清空, func_health 动态选健康 fid.
> **改前数据锚点**: 40006(host opc2sname) 30min 只有 glm5_2_nv 流量(1条) — dsv4f0731 定义是冗余残留; 40666 dsv4f0731 6h 161 条全 dsv4f0731; 40066 30min 0 流量(历史遗留).

## 本轮 (R1249) 改动 + 依据 + 验证

### 改动 1: FID 动态健康切换 (R1253)
- **config.py**: glm5_2_nv `function_ids` 3 候选 → **5 个 ACTIVE fid** (pos0-pos4, env 可覆盖).
- **upstream.py:1878**: KEY_FID_BIND 命中也检查 `func_health.is_healthy`, 绑定 fid surge/429 时自动 `select_healthy_function` 切到健康候选 (不再短路).
- **docker-compose.yml**: `NV_GLM52_KEY_FID_BIND=` 清空 (原 `0:0;1:0;2:0;3:0;4:0` 全钉 pos0); 加 FUNCTION_ID2~5 env; 开 `NVU_FID_DISCOVERY_ENABLED=1` (1800s, model=glm5_2_nv, match=glm).
- **fid_discovery.py bug**: `_probe_fid` 硬编码 dsv4f model + 直连 → 对 glm 候选全 404. 修复: model 从 `NV_MODEL_IDS[DISCOVERY_MODEL]` 动态取 + 复用 `nvcf_conn._make_nvcf_proxy_conn` 走 per-key mihomo.

### 改动 2: NVU_ACTIVE_TIERS 模型白名单 (R1254)
- **背景**: 40006/40066/40666 三容器 bind-mount **共用一份 config.py**, 原本全量暴露 5 模型. 直接删 dsv4f0731 会打挂 40666 主链.
- **config.py**: 新增 `NVU_ACTIVE_TIERS` env (逗号分隔; 空=全部), 过滤 NVCF_PEXEC_MODELS/NV_MODEL_TIERS/NV_MODEL_IDS/MODEL_MAP; DEFAULT 不在白名单自动切第一个.
- **compose**: 40006=`glm5_2_nv`, 40666=`dsv4f0731_nv`, 40066=`dsv4p_nv`.
- **依据**: 40006 30min 只有 glm5_2_nv 流量 (dsv4f0731 是冗余残留); 40666 专职 dsv4f0731; 40066 专职 dsv4p_nv.

### 验证 (全部通过)
| 项目 | 结果 |
|---|---|
| compose config --quiet | ✅ OK |
| config.py py3.12 ast.parse | ✅ OK |
| 40006 health | ✅ `['glm5_2_nv']` default=glm5_2_nv |
| 40666 health | ✅ `['dsv4f0731_nv']` default=dsv4f0731_nv |
| 40066 health | ✅ `['dsv4p_nv']` default=dsv4p_nv |
| 40666 dsv4f0731 冒烟 | ✅ 200 in 11s (主链正常) |
| 40006 glm5_2_nv 冒烟 | ✅ 200 in 29s |
| 40006 收 dsv4f0731 请求 | ✅ `mapped_model=glm5_2_nv` (白名单外 fallback DEFAULT) 200 in 7s |

## 参数快照 (R1249: FID 动态 + 白名单, 实测 env)

- **nv_gw (40006)**: `NVU_ACTIVE_TIERS=glm5_2_nv` (**只部署 glm5_2_nv**), `NV_GLM52_KEY_FID_BIND=` (清空),
  `NV_GLM52_FUNCTION_ID2~5` (4 个候选), `NVU_FID_DISCOVERY_ENABLED=1` MODEL=glm5_2_nv NAME_MATCH=glm,
  `NV_GLM52_MODE_CHAIN=pexec_us_rr,integrate_us_rr`, `NVCF_GLM52_FUNCTION_ID=3b9748d8`,
  `NV_INTEGRATE_MODELS=glm5_2_nv`, NVU_PEER_FB_SKIP_MODELS=glm5_2_nv,
  TIER_TIMEOUT_BUDGET_S=180, NVU_BUFFER_MAX_RETRIES=5 (stairs 90×5=450s),
  NVU_CALLER_KEY_MAP=hermes:2;openclaw:3;opencode:4。
- **dsvf0731_nv40666 (40666)**: `NVU_ACTIVE_TIERS=dsv4f0731_nv` (专职), `NVU_FID_DISCOVERY_ENABLED=1`,
  MODEL=dsv4f0731_nv, NAME_MATCH=deepseek-v4-flash, fid 281478d0 自动发现;
  TIER_TIMEOUT_BUDGET_S=180, BUFFER_MAX_RETRIES=5, BUFFER_CALLERS=cc4101-fallback。
- **dsv4p_nv40066 (40066)**: `NVU_ACTIVE_TIERS=dsv4p_nv` (专职), NVU_FID_DISCOVERY 各参数保留。
- **cc4101**: PRIMARY_UPSTREAM_MODEL=dsv4f0731_nv, PRIMARY_UPSTREAM_URL=http://dsvf0731_nv40666:40666/v1/messages,
  FALLBACK_UPSTREAM_MODEL=dsv4f0731_ms, FALLBACK_UPSTREAM_URL=http://ms_gw:40007/v1/messages, FALLBACK_UPSTREAM_TOKEN=ms-gw-token,
  CC4101_STREAM_TOTAL_DEADLINE_S=470, PRIMARY_HEADER_TIMEOUT=400, PRIMARY_FAIL_THRESHOLD=3,
  PRIMARY_SKIP_S=30, UPSTREAM_TIMEOUT=130, UPSTREAM_IDLE_TIMEOUT=150。
- **hm4104/opclaw4103/oc4105**: primary dsv4f0731_nv@40666, fallback dsv4f0731_ms@ms_gw:40007 (ms-gw-token)。

## 上轮
R1248 (4 容器 fallback 统一切 ms_gw:40007 dsv4f0731_ms, 与 NVCF 账号解耦 实现跨供应商真备用; 端到端 + health + env 验证通过, fallback 实地触发待用户密集请求后 DB 复核)
→ **R1249 (① glm5_2_nv FID 动态健康切换: 5 候选全展开 + KEY_FID_BIND 清空 + discovery 开启 + probe 404 修复; ② NVU_ACTIVE_TIERS 白名单: 40006 只留 glm5_2_nv, dsv4f0731 只在 40666; 三容器 health + 冒烟 + fallback 行为全验证通过)**。

## 下一步
1. **FID discovery probe 修复后观察**: 下个窗口日志确认 discovery 能探测到 ACTIVE glm 候选 (不再 404), 后台 30min 自动发现新 fid.
2. **延迟加权候选**: 用户方案提到"自动读取 DB 延迟数据动态选低延迟 fid", 本次实现健康切换 + discovery; 延迟排序可作为 func_health 增强 (avg(elapsed_ms) 择优).
3. **长期观察**: 40006 白名单后 30min SR 应保持 glm5_2_nv 纯流, 无 dsv4f0731 泄漏; 40666 dsv4f0731 主链 SR 不受影响.
4. **fallback 实地触发复核 (R1248 遗留)**: 用户密集请求后查 `nv_requests.fallback_occurred=true` 时 fallback_to 是否含 ms_gw / dsv4f0731_ms.