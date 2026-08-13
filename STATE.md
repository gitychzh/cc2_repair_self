# STATE.md — cc2 自优化 nv_gw 链路 (R1256c, 2026-08-13)

## 当前架构 (R1256c, 实测 2026-08-13 校正)

```
你(cc2, claude-opus-5) → cc4101 (127.0.0.1:4101)
  │ primary   PRIMARY_UPSTREAM_URL   = http://nv_gw:40006/v1/messages
  │           PRIMARY_UPSTREAM_MODEL = glm5_2_nv
  ▼
nv_gw (40006) — glm5_2_nv pexec_us_rr,integrate_us_rr (5 key, 2 ACTIVE fid 候选):
  ├─ fid 候选 (R1255 精简): [3b9748d8 (ACTIVE 429-prone), bfcf495b (ACTIVE 快稳)]
  ├─ per-key 代理: k0→7901 k1→7894 k2→7897 k3→7896 k4→7899
  ├─ KeyManager (429: 120s→600s; RemoteDisconnected: 5s)
  ├─ ProbeWorker (15s 探测 cooling key)
  ├─ BufferStreamSession (5key 轮转, 90s/attempt, 5 attempts)
  ├─ func_health (per-fid 健康度, 动态切换)
  ├─ fid_discovery (30min 后台, 2 ACTIVE 候选 PROBE-OK)
  └─ ms_gw fallback + peer fallback: 全关
  │ fallback (cc4101 层, primary 全败时触发)
  ▼
ms_gw (40007) — glm5_2_ms (ModelScope 中国, 7 key, 10 variant):
  └─ DEFAULT_MODEL=glm5_2_ms, 同模型跨供应商真备用

opclaw4103 (port 4103) — 独立 cc-adapter (openclaw 客户端):
  ├─ Primary:   ms_gw:40007  → glm5_2_ms  (ModelScope, OpenAI SSE, 92% SR)
  ├─ Fallback:  nv_gw:40006 → glm5_2_nv  (NVCF pexec, NVCF 降级时备用)
  ├─ PRIMARY_HEADER_TIMEOUT=90, FALLBACK_HEADER_TIMEOUT=70
  └─ API keys: NV_GW_API_KEY=ms-gw-token (primary), FALLBACK_API_KEY=nv-gw-token (fallback)
```

## R1256c 本轮改了什么 (opclaw4103 "primary 和 fallback 均不可用" 修复)

1. **根因**: opclaw 原 primary=dsv4f0731_nv@40666 (NVCF fid 281478d0) pexec 87% 超时降级;
   fallback=dsv4f0731_ms@ms_gw 偶发 70s 超时; 双链同时失败致 "均不可用"
2. **修复**: opclaw primary→ms_gw(40007) glm5_2_ms (OpenAI SSE 原生, 92% SR, TTFB 1-20s);
   fallback→nv_gw(40006) glm5_2_nv (NVCF pexec, ms_gw 降级时备用)
3. **API key 调整**: NV_GW_API_KEY=ms-gw-token (primary 用), FALLBACK_API_KEY=nv-gw-token (fallback 用)
4. **timeout**: PRIMARY_HEADER_TIMEOUT=90, FALLBACK_HEADER_TIMEOUT=70, 90+70=160<170 PROXY_TIMEOUT

## R1256c 验证

- 流式无 tools: 200 OK ~2s (ms_gw primary 直接成功)
- 流式 with tools: primary ms_gw 90s 超时 (429 风暴) → fallback nv_gw 成功 (无 "均不可用")
- 非流式: 200 OK 6.5s
- opclaw 日志: 无 PRIMARY-FAIL/CIRCUIT-OPEN (ms_gw 稳定时)

## R1256b 前轮改了什么 (cc2 修复 HM1 "Server error mid response")

1. HM1 nv_gw/cc4101/ms_gw 源码全量同步 HM2→HM1
2. HM1 docker-compose.yml env 全面更新 (40 个 R1256 标签)
3. nv_gw 启动 crash 修复 (format/ 子目录)

## 前序

- R1256b: HM1 源码全量同步 + nv_gw crash 修复
- R1255: config.py 死fid精简 + cc4101 链路切 glm5_2_nv primary + glm5_2_ms fallback
- R1254: NVU_ACTIVE_TIERS 白名单 (40006=glm5_2_nv, 40666=dsv4f0731_nv, 40066=dsv4p_nv)
- R1253: KEY_FID_BIND 清空 + func_health 动态切换 + fid_discovery probe 修复

## 关键 deadline 层级

| 层 | 参数 | 值 |
|---|---|---|
| NVCF 单次 | UPSTREAM_TIMEOUT | 90s |
| buffer 5key×90s | NVU_BUFFER_TIMEOUT_STAIRS | 90,90,90,90,90 |
| buffer 总预算 | NVU_BUFFER_TOTAL_DEADLINE_S | 450s |
| cc4101 总上限 | CC4101_STREAM_TOTAL_DEADLINE_S | 470s |
| cc4101 header | PRIMARY_HEADER_TIMEOUT | 400s |
| cc2 SDK 总超时 | API_TIMEOUT_MS | 600000ms (600s) |

## Function IDs (NVCF glm-5.2, 实测 2026-08-13)

| fid (8) | 状态 | 备注 |
|---|---|---|
| `3b9748d8` | ✅ ACTIVE | pexec 429-prone (配额满载), 当前 pos0 |
| `bfcf495b` | ✅ ACTIVE | 实测 SR=100% 15/15 p50 1.8s, 当前 pos1 |
| `b6029a96` | ❌ INACTIVE | NVCF functions 列表 INACTIVE, pexec 404, 已删 |
| `b1b22d03` | ❌ INACTIVE | 同上, 已删 |
| `5532e90c` | ❌ INACTIVE | 同上, 已删 |

## HM1 状态 (R1256b 后)

- HM1 nv_gw/cc4101/ms_gw 源码已与 HM2 对齐 (2026-08-13)
- HM1 docker-compose env 已补齐 (40 个 R1256 标签)
- HM1 备份: /tmp/hm1_{nv_gw,cc4101,ms_gw}_backup_R1256/
- HM1 SSH: `ssh -p 222 opc_uname@100.109.153.83`
- HM1 特有配置保留: mihomo 5端口(7894/5/6/7/9, 无7901), 独立 US IPs, host.docker.internal proxy

## 下一步

- 等 HM1 cc 产生新流量, 观察 30min 窗口 SR + "Server error mid response" 是否消失
- HM2 本地下窗口 NOP 巡检 (R1255 链路 glm5_2_nv primary + glm5_2_ms fallback)
- 关注 3b9748d8 429 是否持续, 若持续考虑只保留 bfcf495b 单 fid
