# R648 — NOP + 拓扑纠偏轮 (2026-08-03 15:13 CST)

## 本轮改了什么 + 依据 + 验证
- **改动**: 无代码改动 (NOP). 但发现 STATE.md R626-R647 历史轮记录的 env 快照与实际容器不符 — 注入的"轮前链路分析"配置段过时, 把 HM2 描述成旧 R-nvonly + dsv4p_nv primary + ms_gw fallback 拓扑, 实际容器跑的是 **R-glm52split** 架构.
- **依据 (实测 docker exec env, 非注入快照)**:
  - cc4101: `PRIMARY_UPSTREAM_MODEL=glm5_2_nv` (非 dsv4p_nv), `PRIMARY_UPSTREAM_URL=http://nv_gw:40006/v1/messages`, `FALLBACK_UPSTREAM_URL=http://dsv4p_nv40066:40066/v1/messages` (非 ms_gw!), `FALLBACK_UPSTREAM_MODEL=dsv4p_nv`, `CC4101_STREAM_TOTAL_DEADLINE_S=470`, `PRIMARY_HEADER_TIMEOUT=400`
  - nv_gw: `NVU_DISABLE_MS_FALLBACK=1` (非 0), `NVU_MS_FALLBACK_ENABLED=0`, `NVU_PEER_FALLBACK_ENABLED=0`, `NVU_PEER_FALLBACK_URL=http://100.109.153.83:40006` (HM1 peer 但关), `UPSTREAM_TIMEOUT=90`, `TIER_COOLDOWN_S=180`, `NVU_BUFFER_TOTAL_DEADLINE_S=450`, `NVU_CALLER_KEY_MAP=hermes:2;openclaw:3;opencode:4`
  - 新增容器 `dsv4p_nv40066` (port 40066, 独立 dsv4p nv_gw, cc4101 fallback 目标), `nv_gw_stable` (40005, 37h 长稳 standalone)
  - cc2 自己的流量 = `caller=cc4101-primary` + `mapped_model=glm5_2_nv` (PRIMARY 已切 glm5_2_nv); hermes caller 走 dsv4p_nv 是 hm 直接打 nv_gw 的另一路流量
- **验证 (实测 30min DB, 14:43-15:13 CST 窗口)**:
  - nv_requests 30min: 33 req = 29×200 + 3×429 + 1×502 (SR=87.9%)
  - 拆分: cc4101-primary/glm5_2_nv=3×200 (SR 100%, cc2 自己流量健康); hermes/dsv4p_nv=25×200+3×429+1×502 (SR=86.2%, 配额型); openclaw/dsv4p_nv=1×200
  - per-key: k2=27×200+1×502 (主力), k0=1×200, k3=1×200, 空 key=3×429
  - per-egress: 203.10.96.139=25×200+1×502 (主力 96%), 134.195.101.193/194/195=各 1-2×200
  - 错误分类 2 类无新模式: `all_tiers_exhausted` ×3 (429 配额, peer-fb skip→本地 502→cc4101 fallback dsv4p_nv40066 兜底); `NVStream_IncompleteRead` ×1 (连续 6 轮单发 R644→R648, 阈值 >=3/30min 未触及, 持续观察点)
  - nv_tier_attempts 30min: pexec_success ×3, integrate_conn_RemoteDisconnected ×1 (hermes 路径)
  - cc_requests stream_total_deadline 6h: 0 (deadline 链健康, 铁证)
  - 容器: nv_gw Up 40s (刚 restart, 原因非本轮, 可能外部编排), cc4101 Up 39s, dsv4p_nv40066 Up 2min, nv_gw_stable Up 37h, ms_gw Up 4d, logs_db Up 4d
  - /health ok: nv_num_keys=5, nvcf_pexec_models=[kimi_nv,dsv4p_nv,glm5_2_nv], nv_default_model=glm5_2_nv

## 基线 (R648 实测, 14:43-15:13 CST)
- cc2 (cc4101-primary/glm5_2_nv) 30min: 3 req, 3×200 (SR=100%, 小样本, 流量恢复中)
- dsv4p_nv (hermes caller) 30min: 29 req, 25×200+3×429+1×502 (SR=86.2%, +1.6pp vs R647 84.6%, 仍在 R617-R647 正常波动区间 37-91% 内)
- 6h 趋势: 29-91% 波动, 本轮 86.2% 接近上沿, 配额型故障模式未变 (NVCF 账户级配额耗尽, 429 无 retry-after, 全 5key 429→TIER_COOLDOWN 180s)
- 错误分类 2 类 (无新模式, 同 R644-R647):
  - `all_tiers_exhausted` ×3 (持平 R647, 正常区间 3-6 下沿, 趋势向好)
  - `NVStream_IncompleteRead` ×1 (连续 6 轮单发, 阈值未触及, 连续性强化为持续观察点)
- deadline 链: stream_total_deadline 6h=0 (健康)

## 关键纠偏记录 (本轮核心发现)
STATE.md R626-R647 的 env 快照 (`NVU_DISABLE_MS_FALLBACK=0`, `FALLBACK_UPSTREAM_URL=http://ms_gw:40007/...`, `PRIMARY_UPSTREAM_MODEL=dsv4p_nv`) 与实际容器不符. 那些轮的"轮前链路分析"注入的配置快照是过时的, 描述的是旧 R-nvonly 拓扑, 但容器实际已切 R-glm52split (cc4101 primary=glm5_2_nv, fallback=dsv4p_nv40066 独立容器, 非 ms_gw; NVU_DISABLE_MS_FALLBACK=1).

后续轮 STATE env 快照一律以 `docker exec env` 实测为准, 不抄注入快照. 已写 memory `r-glm52split-topology-2026-08-03` 固化.

## 下一步
- **本轮 NOP, 不改码**: 链路实测健康 (cc2 自己 3/3=100%, deadline 链 0 触发, 配额型故障模式未变非 nv_gw 可改)
- **持续观察点**:
  1. dsv4p_nv 配额型 429 全挂 (24h+ 持续, 单 egress IP 203.10.96.139 主力, NVCF 无 retry-after 头)
     - 若 SR 持续 <55% (连续 3+ 小时) 或 exhausted>=8 → 评估切 PRIMARY 回 dsv4p_nv (但当前 PRIMARY 已是 glm5_2_nv, 此阈值需重新审视)
  2. NVStream_IncompleteRead 连续性演变 (R644→R648 连续 6 轮 1 例/30min)
     - 当前阈值 >=3/30min 未触及, 但连续 6 轮单发 = 子类型稳定存在非偶发
     - 若升级为 >=3/30min 或 avg_dur 持续 >36s → 评估 NVCF 慢响应根因 / buffer 不完整流读处理
- **建议维持: 联系 NVCF 侧评估 dsv4p_nv 账户配额扩容 / 提供 retry-after 头 / 慢响应根因**
- 等 cc2 流量 (cc4101-primary/glm5_2_nv) 恢复更多样本后观察 buffer 路径行为

## 参数快照 (R648 实测, 以 docker exec env 为准)
- nv_gw: NVU_DISABLE_MS_FALLBACK=1, NVU_MS_FALLBACK_ENABLED=0, NVU_PEER_FALLBACK_ENABLED=0,
  NVU_PEER_FALLBACK_URL=http://100.109.153.83:40006 (HM1 peer, ENABLED=0), UPSTREAM_TIMEOUT=90,
  TIER_COOLDOWN_S=180, KEY_COOLDOWN_S=30, NV_INTEGRATE_KEY_COOLDOWN_S=90,
  MIN_OUTBOUND_INTERVAL_S=10, NVU_FORCE_STREAM_UPGRADE=0, NVU_FORCE_STREAM_UPGRADE_TIMEOUT=150,
  NVU_BUFFER_MAX_RETRIES=5, NVU_BUFFER_TIMEOUT_STAIRS=90,90,90,90,90,
  NVU_BUFFER_TOTAL_DEADLINE_S=450, NVU_BUFFER_CALLERS=cc4101-primary,openclaw2,
  NVU_PEER_FB_SKIP_MODELS=glm5_2_nv,dsv4p_nv, NVU_CALLER_KEY_MAP=hermes:2;openclaw:3;opencode:4,
  NVU_KEYMGR_429_BASE_COOLDOWN=120, NVU_KEYMGR_429_MAX_COOLDOWN=600,
  TIER_TIMEOUT_BUDGET_S=180, NVU_TIER_BUDGET_DSV4P_NV=180
- cc4101: PRIMARY_UPSTREAM_URL=http://nv_gw:40006/v1/messages, PRIMARY_UPSTREAM_MODEL=glm5_2_nv,
  FALLBACK_UPSTREAM_URL=http://dsv4p_nv40066:40066/v1/messages (非 ms_gw), FALLBACK_UPSTREAM_MODEL=dsv4p_nv,
  CC4101_STREAM_TOTAL_DEADLINE_S=470, PRIMARY_HEADER_TIMEOUT=400,
  CC4101_PRIMARY_SKIP_S=30, CC4101_PRIMARY_FAIL_THRESHOLD=3,
  UPSTREAM_TIMEOUT=130, UPSTREAM_IDLE_TIMEOUT=150
- 链路: cc2(cc4101:4101) → nv_gw(40006, glm5_2_nv) → 5key(k0-k4)×5 US IP(hysteria2) → NVCF
  cc4101 fallback → dsv4p_nv40066(40066, 独立 dsv4p 容器) → NVCF
- deadline 链: UPSTREAM_TIMEOUT=90s < NVU_TIER_BUDGET=120-180s < buffer 90s×5=450s < cc4101 470s < SDK 500s idle
- 注: STATE R626-R647 env 快照过时 (写 NVU_DISABLE_MS_FALLBACK=0/PRIMARY=dsv4p_nv/ms_gw fallback), 实际 R-glm52split 已是 glm5_2_nv primary + dsv4p_nv40066 fallback, 本轮起 STATE 纠正
