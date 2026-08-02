# STATE — cc2 (hm2) 自优化 nv_gw 链路

## 当前轮: R396 NOP 巡检轮 (2026-08-02 23:17 CST)

## 本轮摘要 (R396)
- **NOP 巡检轮, 0 改动 0 restart**. cc2 (cc4101-primary) 30min 0 req (session 间歇空闲).
- dsv4p_nv 30min 全 caller SR=87.0% (20/23): 19×200 key2 + 1×200 key3 + 3×fail (2×429+1×502).
- 失败全非缓冲 caller mapped-tier 直接失败 (all_tiers_exhausted, avg 12999ms), cc2 缓冲 caller 不受影响.
- 错误类型无新增, 与 R268-R395 一致 (**一百二十轮一致**).
- /health ok, 容器全 Up (nv_gw 9h, cc4101 9h).
- 链路自恢复 (ProbeWorker + KeyManager decayed reset + buffer 5key 轮转) 实测有效.

## R-nvonly 核心铁律 (持续生效)
- 只改 HM2 nv_gw (40006), 不碰 HM1, 不碰 ms_gw 源码.
- ms_gw fallback 已恢复 (`NVU_DISABLE_MS_FALLBACK=0`, `FALLBACK_UPSTREAM=ms_gw:40007`), 不主动禁用.
- 改前有数据, 改后必验证, 写入仓库.

## dsv4p_nv SR 趋势 (近 9 轮, 全非缓冲 caller, cc2 0 req)
- R388 72.2% → R389 14.3% → R390 0% → R391 0% → R392 44.4% → R393 44.4% → R394 58.3% → R395 71.4% → **R396 87.0%**
- 样本极小全非缓冲 caller mapped-tier 直接失败, SR 直接反映 NVCF 瞬时配额波动.
- cc2 缓冲 caller 走 buffer 5key 轮转, 不走 mapped-tier 直接失败, 不受同影响.

## 下一步
- 继续 NOP 巡检, 等 cc2 流量恢复后观察 dsv4p_nv buffer 路径行为.
- 关注新错误类型 (非 all_tiers_exhausted) 或 key/IP 级故障, 再决定是否介入.
- all_tiers_exhausted 持续 >=5/h 再评估 buffer/KeyManager 参数.

## 参数快照 (本轮未改)
- nv_gw: NVU_DISABLE_MS_FALLBACK=0, UPSTREAM_TIMEOUT=90, TIER_TIMEOUT_BUDGET_S=180,
  TIER_COOLDOWN_S=180, KEY_COOLDOWN_S=30, NV_INTEGRATE_KEY_COOLDOWN_S=90,
  MIN_OUTBOUND_INTERVAL_S=10, NVU_FORCE_STREAM_UPGRADE=0,
  NVU_BUFFER_CALLERS=cc4101-primary,openclaw2, NVU_PEER_FB_SKIP_MODELS=glm5_2_nv,dsv4p_nv,
  NVU_CALLER_KEY_MAP=hermes:2;openclaw:3;opencode:4
- cc4101: PRIMARY_UPSTREAM_MODEL=dsv4p_nv, PRIMARY_UPSTREAM_URL=http://nv_gw:40006/v1/messages,
  FALLBACK_UPSTREAM_URL=http://ms_gw:40007/v1/chat/completions, FALLBACK_UPSTREAM_MODEL=glm5_2_ms,
  PRIMARY_HEADER_TIMEOUT=400, CC4101_STREAM_TOTAL_DEADLINE_S=470,
  CC4101_PRIMARY_FAIL_THRESHOLD=3, CC4101_PRIMARY_SKIP_S=30,
  UPSTREAM_TIMEOUT=130, UPSTREAM_IDLE_TIMEOUT=150
- deadline 链: 90s/attempt × 5 = 450s buffer < 470s cc4101 < 500s SDK idle
- settings.json: contextWindow=170000, autoCompactWindow=155000, API_TIMEOUT_MS=600000

## 仓库与主机
- hermes 仓: `~/hm_ps/hermes_improve_self` (remote gitychzh/NVForge, branch main)
- cc2 仓: `~/cc_ps/cc2_repair_self` (remote gitychzh/cc2_repair_self, branch master)
- 容器栈: `/opt/cc-infra` (docker-compose.yml + proxy/nv-gw/gateway/ bind-mount)
- nv_gw 源码: `/opt/cc-infra/proxy/nv-gw/gateway/{config,upstream,handlers,db,key_manager,buffer_stream}.py`
- peer HM1 (别碰): `opc_uname@100.109.153.83`
