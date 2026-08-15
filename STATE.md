# STATE.md — cc2 自优化 nv_gw 链路 (R1256b, 2026-08-13)

## R2423 本轮 (2026-08-15, 诊断分析轮 NOP)

### 本轮做了什么
用户要求深挖 40666 dsv4f0731_nv empty_200 问题. 全面诊断:
- **结论**: empty_200 = NVCF 后端时段性波动 (返回 200 + Content-Length:0 空响应), **非输入太大/非代码逻辑/非请求频率/非 key/非 IP 问题**
- empty_200 成簇出现在 18:43-19:37 CST 时段 (25 次/12h), 之后逐渐恢复
- 所有 5 key + 5 US IP 都均匀受影响 — NVCF 整体波动而非单线
- 无更优 FID: 281478d0-f307-49f4-9e0f-080b63b16c47 是唯一 ACTIVE deepseek-v4-flash-0731
- 代码逻辑正确: _check_empty_200() 准确识别 NVCF 空响应

### 发现的优化空间 (未实施)
- empty_200 触发 mark_429 cooldown=120s (mark_key_cooling 是 mark_429 wrapper) — 语义不精确, empty_200 非 rate limit
- empty_200 后下一个 key 6-15s 内成功, 120s 冷却偏重
- 可选优化: empty_200 独立 cooldown (30-60s) 或在 mark_key_cooling 增加自定义 duration

### 验证
- 直连 pexec 15 次: 14×200 OK + 1×529, 0 empty_200 (当前时段健康)
- Gateway 非/流测试均 200 OK ✅
- 三容器 SR: nv_gw 99.8% | dsv4f0731_nv 71.1% | dsv4p_nv 0% (全挂)

### 下一步
- 等 NVCF 下次波动观察 empty_200 模式
- 若用户同意, 可优化 empty_200 cooldown 策略


## 当前架构 (R1256b, 实测 2026-08-13 校正)

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

## R1256b 本轮改了什么 (cc2 修复 HM1 "Server error mid response")

1. **HM1 nv_gw 源码全量同步** HM2→HM1: 5 新文件 (buffer_stream/key_manager/probe_worker/fid_discovery/stream_success_judge) + 8 过时覆写 + 3 文件 format/ 子目录创建
2. **HM1 cc4101 源码全量同步** HM2→HM1: 3 新文件 (routing/http_client/timeout_strategy) + 6 过时覆写
3. **HM1 ms_gw 源码同步**: handlers.py (加 /v1/messages 端点), upstream.py, config.py
4. **HM1 docker-compose.yml env 全面更新**: 40 个 R1256 标签, 含 BUFFER/KEYMGR/WAIT_QUEUE/MS_FALLBACK 全部新增, proxy URLs 全转 socks5h://
5. **nv_gw 启动 crash 修复**: 首次 up 后 ModuleNotFoundError 'gateway.format' → 创建 format/ 目录并传输 3 个 .py 文件 → restart 后 healthy

## R1256b 验证

- 端到端 3/3 200 OK via primary glm5_2_nv (12-69s)
- DB: nv_requests 5min 3×200, per-key k0/k1/k2/k4 多 key 轮转 + 2 fid (3b9748d8+bfcf495b) + integrate
- 三容器全 Up healthy: nv_gw, cc4101, ms_gw
- FID discovery 启动: 182 functions, 2 ACTIVE glm-5.2 candidates, bfcf495b probe OK
- 修复前 30min 窗口: SR 63.8% (zombie_empty_completion 67, upstream_error 37) — 全部来自修复前旧数据

## R1255 本轮改了什么

1. **config.py glm5_2_nv function_ids 精简**: 5 候选 → 2 候选 (删 3 个 INACTIVE 死 fid b6029a96/b1b22d03/5532e90c).
2. **cc4101 compose env 切链**: primary dsv4f0731_nv@40666 → glm5_2_nv@40006; fallback dsv4f0731_ms → glm5_2_ms (同模型跨供应商).

## 前序

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
