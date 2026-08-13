# STATE.md — cc2 自优化 nv_gw 链路 (R1255, 2026-08-13)

## 当前架构 (R1255, 实测 2026-08-13 校正)

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
```

## R1255 本轮改了什么

1. **config.py glm5_2_nv function_ids 精简**: 5 候选 → 2 候选 (删 3 个 INACTIVE 死 fid b6029a96/b1b22d03/5532e90c).
2. **cc4101 compose env 切链**: primary dsv4f0731_nv@40666 → glm5_2_nv@40006; fallback dsv4f0731_ms → glm5_2_ms (同模型跨供应商).

## R1255 验证

- 端到端冒烟 cc→4101→40006: 3/3=200, model=glm5_2_nv, text=OK, 4.8-25.4s
- DB 5min: 7×200 host_machine=opc2sname mapped_model=glm5_2_nv
- 三容器全 Up

## 前序

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

## 下一步

- 下窗口观察新链路 SR + fallback 触发率 + glm5_2_nv 延迟分布.
- 关注 3b9748d8 429 是否持续, 若持续考虑只保留 bfcf495b 单 fid.
- dsv4f0731_nv@40666 容器保留运行作为应急备用.
