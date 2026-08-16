# STATE.md — cc2 自优化 nv_gw 链路 (R2427, 2026-08-16)

## R2427 本轮 (2026-08-16, 架构重构)

### 本轮做了什么
**三容器代码彻底解耦 — 独立 gateway 目录**

三个 NV 网关容器 (40006/40066/40666) 历史上共用同一份 `./proxy/nv-gw/gateway` bind-mount,
改一个模型的代码可能影响其他模型。现已:

1. **备份**: `cp -a nv-gw/gateway nv-gw/gateway.bak.R-decouple`
2. **创建独立目录**:
   - `nv-gw-dsv4p/gateway` → 40066 (dsv4p_nv) 独立目录
   - `nv-gw-dsv4f0731/gateway` → 40666 (dsv4f0731_nv) 独立目录
3. **docker-compose.yml 挂载更新**:
   - 40066: `./proxy/nv-gw/gateway` → `./proxy/nv-gw-dsv4p/gateway`
   - 40666: `./proxy/nv-gw/gateway:rw` → `./proxy/nv-gw-dsv4f0731/gateway:rw`
4. **sync_core.sh 脚本**: 16 个通用文件 (rr_counter/cooldown/nvcf_conn/pexec/func_health/db/logger/...)
   可一键同步, 模型特定文件 (config/upstream/handlers/buffer_stream/glm52_mode_idx) 各目录独立维护
5. **代码裁剪**: 本轮不做激进裁剪 — 物理隔离已实现解耦, NVU_ACTIVE_TIERS 已过滤非活跃模型

### 验证
- 三容器 health 全 OK: 40006=glm5_2_nv, 40066=dsv4p_nv, 40666=dsv4f0731_nv
- Docker 挂载: 三容器各自指向独立目录 ✅
- 功能测试: 40006 200 OK "Hi!" ✅, 40666 200 OK reasoning_content ✅
- sync_core.sh --diff: 0 file(s) differ ✅

### 下一步
- 日常优化可自由改 nv-gw/gateway/ (40006), 不影响 40066/40666
- 通用 bug 修复后 `./sync_core.sh` 一键同步
- 可选: 后续逐步在各目录删除非活跃模型死代码

## 目录结构

```
/opt/cc-infra/proxy/
├── nv-gw/                       # 40006 (glm5_2_nv) — 主目录
│   ├── gateway/                 #   bind-mount → /app/gateway
│   ├── gateway.bak.R-decouple   #   全量备份
│   └── Dockerfile + gateway_main.py
├── nv-gw-dsv4p/                 # 40066 (dsv4p_nv) — 独立目录
│   └── gateway/                 #   bind-mount → /app/gateway
├── nv-gw-dsv4f0731/             # 40666 (dsv4f0731_nv) — 独立目录
│   └── gateway/                 #   bind-mount → /app/gateway
└── sync_core.sh                 # 通用文件同步脚本 (16 文件)
```

## 当前架构 (R2427, 2026-08-16)

```
你(cc2) → cc4101 (127.0.0.1:4101)
  │ primary   PRIMARY_UPSTREAM_URL   = http://nv_gw:40006/v1/messages
  │           PRIMARY_UPSTREAM_MODEL = glm5_2_nv
  ▼
nv_gw (40006) — glm5_2_nv pexec_us_rr,integrate_us_rr (独立 gateway/ 目录):
  ├─ fid 候选: [3b9748d8 (ACTIVE), bfcf495b (ACTIVE)]
  ├─ per-key 代理: k0→7901 k1→7894 k2→7897 k3→7896 k4→7899
  ├─ KeyManager (429: 120s→600s; RemoteDisconnected: 5s)
  ├─ ProbeWorker (15s 探测 cooling key)
  ├─ BufferStreamSession (5key 轮转, 90s/attempt, 5 attempts)
  ├─ func_health + fid_discovery
  └─ ms_gw fallback + peer fallback: 全关
  │ fallback (cc4101 层, primary 全败时触发)
  ▼
ms_gw (40007) — glm5_2_ms (ModelScope, 备用)

dsv4p_nv40066 (40066) — dsv4p_nv (独立 nv-gw-dsv4p/gateway/ 目录)
dsvf0731_nv40666 (40666) — dsv4f0731_nv (独立 nv-gw-dsv4f0731/gateway/ 目录)
```

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
| `3b9748d8` | ✅ ACTIVE | pexec 429-prone, pos0 |
| `bfcf495b` | ✅ ACTIVE | SR=100% 快稳, pos1 |

## 前序

- R2426: 删除 nv_gw_stable (40005) 冗余容器
- R2425: nv_gw buffer_stream _drain_upstream 100% CPU spin 根治
- R2424: oc45001 PersistentCounter next() bug fix
- R1255: config.py 死fid精简 + cc4101 链路切 glm5_2_nv primary
