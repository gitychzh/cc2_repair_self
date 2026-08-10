# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: **R1246 (内容改动 — 用户指定 3 任务: ①glm5.2 换 fid 3b9748d8 删 b1b22d03; ②dsv4p 清理; ③同 key pexec→integrate 兜底; 全验证 200 OK 生效)**
> 主链 fid: **281478d0-f307** (dsv4f0731_nv), 现经 **dsvf0731_nv40666 容器** (40666)
> **链路 (R1245+R1246)**: cc → cc4101 (4101) → primary `dsvf0731_nv40666:40666/v1/messages` (dsv4f0731_nv, fid 281478d0) ✅ 200 (~2.6s)
> fallback → `nv_gw:40006/v1/messages` (glm5_2_nv, **fid 3b9748d8**) ✅ 200 (~7s, R1246 新 fid pexec 生效)
> 原 primary (nv_gw:40006 dsv4f0731) → 降为 fallback; 原 fallback (ms_gw:40007) → 移除。
> **glm5_2_nv new fid**: 3b9748d8 (ai-glm-5_2, ACTIVE) 替代死链 b1b22d03 (mn-tp8-b200 INACTIVE 404)。
> **改前数据锚点**: 40666 dsv4f0731 0.7-3.1s / 40006 glm5.2 新 fid ~7s (R1246 实测); dsv4p_nv 已 EOL (NVCF 410 Gone 2026-08-07, 容器保留)。

## 本轮 (R1246) 改动 + 依据 + 验证

### 改动 (3 项, 全执行)
1. **fid 换 3b9748d8**: `docker-compose.yml` 4 处 `NVCF_GLM52_FUNCTION_ID` b1b22d03 → 3b9748d8 (line 85/200/302/406);
   `KEY_FID_BIND=0:0;...` 不变全锁 pos0; `config.py` function_ids 默认 pos0=3b9748d8, pos1=b6029a96 (删 b1b22d03 死链)。
   备份 `docker-compose.yml.bak.R1246`, `config.py.bak.R1246`。
2. **dsv4p 清理**: `NVU_PEER_FB_SKIP_MODELS=glm5_2_nv,dsv4p_nv` → `glm5_2_nv` (删 dsv4p_nv 引用);
   **保留 dsv4p_nv40066 容器**。
3. **源码同 key pexec→integrate 兜底** (upstream.py): buffer/attempt 内 pexec 失败后同 key 转 integrate, 下 key 回 pexec。

### 依据 (DB/catalog 实测)
- b1b22d03: NVCF catalog **INACTIVE**, pexec 404; 08-09 起 7 天 DB all_tiers_exhausted 0% SR → 死链删除。
- 3b9748d8 (ai-glm-5_2): NVCF catalog ACTIVE, pexec 单发 200 (~5-11s)。b6029a96 ACTIVE 备用。
- dsv4p (12acbc62): catalog 全 INACTIVE, pexec 404, integrate 410 EOL 08-07 → 不可恢复, 仅清理引用。

### 验证 (全通过)
| 项目 | 结果 |
|---|---|
| compose config | `docker compose config --quiet` → **CONFIG VALID** |
| 容器 | nv_gw / dsv4p_nv40066 / dsvf0731_nv40666 / cc4101 全 Up healthy |
| nv_gw 直连 glm5_2 | 200, `nvcf_pexec`, **fid=3b9748d8**, 6.1s |
| cc4101 主链 | 200, dsv4f0731_nv, 2.6s (未受影响) |
| cc4101 fallback (停40666) | 200, glm5_2_nv, **fid=3b9748d8**, pexec 7.0s |
| config.py 兜底 | 无 b1b22d03 默认; pos0=3b9748d8 |

**fallback 端到端关键**: caller=cc4101-fallback, 200, fid=3b9748d8 nvcf_pexec 7010ms — 新 fid 在 glm5.2 fallback 链路生效, 比旧 integrate (~110s) 快 ~15 倍。

## 参数快照 (nv_gw + cc4101, R1245 链路 + R1246 fid)

- **nv_gw**: UPSTREAM_TIMEOUT=90, TIER_TIMEOUT_BUDGET_S=180, NVU_BUFFER_MAX_RETRIES=5
  (stairs 90×5=450s), NVU_DISABLE_MS_FALLBACK=0, NVU_FORCE_STREAM_UPGRADE=0,
  KEY_COOLDOWN_S=30, INTEGRATE_KEY_COOLDOWN_S=90, TIER_COOLDOWN_S=180, MIN_OUTBOUND_INTERVAL_S=10,
  NV_INTEGRATE_KEY_COOLDOWN_S=90, NVU_FORCE_STREAM_UPGRADE_TIMEOUT=150,
  NVU_CALLER_KEY_MAP=hermes:2;openclaw:3;opencode:4, **NVU_PEER_FB_SKIP_MODELS=glm5_2_nv** (已删 dsv4p_nv),
  **NVCF_GLM52_FUNCTION_ID=3b9748d8**, KEY_FID_BIND=0:0;1:0;2:0;3:0;4:0 (glm5_2_nv 全锁 pos0=3b9748d8)。
- **cc4101**: PRIMARY_UPSTREAM_MODEL=dsv4f0731_nv, PRIMARY_UPSTREAM_URL=http://dsvf0731_nv40666:40666/v1/messages,
  FALLBACK_UPSTREAM_MODEL=glm5_2_nv, FALLBACK_UPSTREAM_URL=http://nv_gw:40006/v1/messages,
  CC4101_STREAM_TOTAL_DEADLINE_S=470, PRIMARY_HEADER_TIMEOUT=400, PRIMARY_FAIL_THRESHOLD=3,
  PRIMARY_SKIP_S=30, UPSTREAM_TIMEOUT=130, UPSTREAM_IDLE_TIMEOUT=150。

## 上轮
R1245 (cc2 链路切换: primary=dsv4f0731_nv@40666, fallback=glm5_2_nv@40006; 端到端两链路实测 200 OK)
→ **R1246 (glm5.2 fid 换 3b9748d8 删死链 b1b22d03, dsv4p 清理, 同 key pexec→integrate 兜底; 全验证生效)**。

## 下一步
1. **观察 30min/1h 窗口**: glm5_2_nv (nv_gw 40006) SR、fid=3b9748d8 分布、fallback 触发率 (目标 <5%)。
2. **3b9748d8 大上下文监控**: 该 fid 大请求 (200K+) 历史 429 多 — 若 cooldown 频触发,
   考虑 pos1=b6029a96 (200K 同限) 备用切换。
3. **dsv4p_nv40066**: EOL 由 NVCF 侧定 (catalog 全 INACTIVE, 410 Gone), 容器保留不路由。
4. **主链 dsv4f0731_nv@40666** SR 观察 (R1246 实测 dsv4f0731 2.6s, 应保持高 SR 无 fallback)。