# STATE.md — cc2 自优化 nv_gw 链路 (R1259, 2026-08-15)

## 当前架构 (R1259, 实测 2026-08-15 校正)

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
  ├─ Primary:   oc45001:45001 → big-pickle (opencode zen 免费模型, 29 IP 轮转池)
  ├─ Fallback:  nv_gw:40006 → glm5_2_nv  (NVCF pexec, NVCF 降级时备用)
  ├─ PRIMARY_HEADER_TIMEOUT=90, FALLBACK_HEADER_TIMEOUT=70
  └─ API keys: NV_GW_API_KEY=oc-proxy-token (primary), FALLBACK_API_KEY=nv-gw-token (fallback)

hm4104 (port 4104) — cc-adapter (hermes 客户端):
  ├─ Primary:   oc45001:45001 → big-pickle (opencode zen 免费模型, 29 IP 轮转池)
  ├─ Fallback:  dsv4f0731_nv40666:40666 → dsv4f0731_nv (NVCF pexec, R1264 修正)
  ├─ API keys: NV_GW_API_KEY=oc-proxy-token (primary), FALLBACK_API_KEY=nv-gw-token (fallback)
  └─ R1259: oc45001 死 IP 清理 (64→29) + ttfb_ms 修复 + compose 注释清理
```

## R1259 本轮改了什么 (openclaw BUG 排查与修复)

1. **架构核实**: opclaw4103 primary=oc45001(big-pickle), fallback=nv_gw(40006,glm5_2_nv).
   dsv4f0731_nv40666 是 hm4104/oc4105 的 fallback, 不是 opclaw4103 的.
2. **BUG #2 修复**: oc_requests.ttfb_ms 永远 NULL → handlers.py 加 `request_row["ttfb_ms"] = attempt_row.get("ttfb_ms")`
3. **BUG #3 修复**: docker-compose.yml opclaw4103 注释清理 (ms_gw→oc45001, depends_on 修正)
4. **BUG #4 修复**: 从 OZ_PROXY_LIST 移除 34 个 0% SR 死 IP (64→29 有效 IP)
5. **IP 轮转核实**: 确认 itertools.count() 按顺序轮流, 429 时顺序切下一个
6. **dsv4f0731_nv40666 5key 健康度**: key3 最优(96.3% SR, 0 次重试), key0 最差(84.8%, 5x exhausted)
7. **文件**: handlers.py, oc-proxy/docker-compose.yml, docker-compose.yml
8. **应用**: up -d oc45001 (env 改动); opclaw4103 compose 注释改动无需重启

## R1259 验证

- 容器: oc45001 Up healthy ✅, opclaw4103/hm4104/oc4105 Up ✅
- oc45001 IP 列表: 29 个有效 IP 加载 ✅ (原 64 个, 移除 34 死 IP)
- handlers.py: ttfb_ms 同步到 request_row ✅ (DB 新请求 ttfb_ms 有值: 2377/3087/4518ms)
- status=200: 新请求正确记录 ✅ (R1258 已修复, 本轮验证确认)
- 烟雾测试: opclaw4103 → 200 OK, big-pickle "Hello" ✅
- compose 注释: opclaw4103 注释与实际链路一致 ✅

## R1258 前轮改了什么 (pacer_queue_timeout 系统性修复)

1. **问题**: oc45001 pacer (`MAX_CONCURRENCY=1`, `QUEUE_TIMEOUT_S=20`) 在长请求 (50-60s) 占满
   唯一并发闸时, 新请求等 20s 后返回 429 `pacer_queue_timeout`. hm4104 forwarder 归为
   `client_4xx` 不触发 fallback → 用户直接看到错误.
2. **与 ChatGPT 系统讨论后方案**:
   - **forwarder.py**: 新增 `_is_pacer_queue_timeout()` 函数, 429 + pacer_queue_timeout
     归为 `server_5xx` → 触发 fallback 到 dsv4f0731_nv40666 (NVCF)
   - **oc45001 compose**: `QUEUE_TIMEOUT_S` 20→10 (fail-fast; 必须 > MIN_INTERVAL_S=8)
   - **不改**: 不 bypass pacer, 不在 oc45001 内做 fallback, 不改 MAX_CONCURRENCY
3. **文件**: forwarder.py (cc-adapter bind-mount, 3 容器共享), oc-proxy compose
4. **应用**: restart opclaw4103 hm4104 oc4105 (源码), up -d oc45001 (env)

## R1258 验证

- 容器: oc45001/hm4104/opclaw4103/oc4105 全 Up ✅
- env: OZ_QUEUE_TIMEOUT_S=10 ✅
- forwarder: `_is_pacer_queue_timeout` × 2 引用 ✅
- health: 4 容器 ok ✅
- 烟雾测试: hm4104 → 200 OK, big-pickle "2", 2826ms ✅

## R1264 前轮改了什么 (hm4104 fallback 修正: ms_gw→dsv4f0731_nv40666)

1. **根因**: hm4104 compose 的 FALLBACK_URL 历史残留指向 ms_gw:40007 (model=dsv4f0731_ms),
   用户要求 fallback 应为 dsv4f0731_nv40666 (model=dsv4f0731_nv, NVCF pexec)
2. **修复**: docker-compose.yml hm4104 service 3 处编辑:
   - FALLBACK_URL: ms_gw:40007 → dsv4f0731_nv40666:40666
   - FALLBACK_MODEL: dsv4f0731_ms → dsv4f0731_nv
   - 新增 FALLBACK_API_KEY=nv-gw-token (dsv4f0731_nv40666 入站 Bearer)
3. **应用**: `docker compose up -d hm4104` (env 改动用 up -d 非 restart)

## R1264 验证

- 容器: hm4104 Up ✅
- env: FALLBACK_URL=http://dsv4f0731_nv40666:40666/v1, FALLBACK_MODEL=dsv4f0731_nv, FALLBACK_API_KEY=nv-gw-token ✅
- health: status=ok, primary=oc45001/big-pickle, fallback=dsv4f0731_nv40666/dsv4f0731_nv ✅
- primary 烟雾测试: POST /v1/chat/completions → 200 OK, model=big-pickle ✅

## R1263 前轮改了什么 (oc45001 64 IP 轮转池 + 6 BUG 修复)

1. hermes 已将 mihomo 64 个 IP 节点 (端口 7910,7914-7915,7918-7978) 加入 oc45001 OZ_PROXY_LIST
2. DB 验证: 重启后 20+ distinct proxy_idx 分布, IP 轮转生效
3. 6 BUG 修复 (handlers.py + pacer.py):
   - BUG 1: report_ok 无条件调用 → 仅 status=200 无 error 时调用 (保护指数退避)
   - BUG 2: 成功时 status 未设 200 → 在 return 前显式设 status=200
   - BUG 3: _send_json 不支持 extra_headers → 添加 extra_headers 参数 (Retry-After 排序)
   - BUG 4: Retry-After 调用点未用 extra_headers → pacer_timeout + all-429 两处修正
   - BUG 5: _proxy_counter 非线程安全 (全局 int) → 改为 itertools.count (原子自增)
   - BUG 6: 删除死代码 _proxy_error_body (未使用)
   - pacer: 信号量过早释放 → acquire 不释放, 新增 release() 在 handler finally 调用

## 前序

- R1263: oc45001 64 IP 轮转池 + 6 BUG 修复
- R1256c: opclaw4103 primary→ms_gw glm5_2_ms, fallback→nv_gw glm5_2_nv
- R1255: cc4101 链路切 glm5_2_nv primary + glm5_2_ms fallback

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

- 观察 hm4104 fallback 触发率 (目标 < 5%, oc45001 SR 99%+ 时极少触发)
- 如 fallback 实际触发, 验证 dsv4f0731_nv40666 端到端 200 OK
- HM2 本地下窗口 NOP 巡检 (cc4101 链路 glm5_2_nv primary)

## R1257 oc45001 pacer 信号量泄漏修复 (2026-08-15)

- **问题**: oc45001 hermes 报错 `queue timeout: global concurrency gate busy (pacer_queue_timeout)`
- **根因**: `handlers.py` pacer 超时路径 `finally` 块无条件 `pacer.release()` 释放从未 acquire 的 sem → 信号量泄漏, 每次 pacer 超时 sem 计数 +1, MAX_CONCURRENCY=1 失效
- **修复**: 新增 `sem_acquired` flag, 仅在成功 acquire 后 release; 删除 pacer error 路径重复 `db.enqueue`
- **验证**: restart 后 10min 9/9 200 OK, 无新 pacer timeout
