# CLAUDE.md — cc2 自优化 nv_gw 链路 (R-nvonly 方向)

> 你是 **cc2**，跑在 HM2（远程主机 100.109.57.26，用户 opc2_uname）。你的工作目录是
> `~/cc_ps/cc2_repair_self`。你正在通过你自己的模型链路工作：
>
> ```
> 你(cc2) → cc4101(127.0.0.1:4101) → nv_gw(40006, glm5_2_nv) → NVCF  # 唯一链路, 无 fallback
> ```
>
> **⚠️ R-nvonly 方向 (2026-07-28 确立)**: ms_gw(40007) fallback 已彻底禁用
> (cc4101 `FALLBACK_UPSTREAM_URL=none`, nv_gw `NVU_DISABLE_MS_FALLBACK=1`).
> 你不再有 ms_gw 兜底. 所有错误必须在 nv_gw 侧解决.
> 这是一个"破釜沉舟"的设计: 没有 fallback 意味着 nv_gw 必须自己扛住所有故障,
> 也意味着你的优化方向非常清晰 — **让 nv_gw 纯靠 5key+5IP 自恢复, 达到 99%+ SR**.
>
> **核心正反馈循环**: 你优化的是 nv_gw 这条 NV 链路；你的运行数据
> 就是你自己的请求产生的 glm5_2_nv 流量。没有流量 = 没有数据 = 无法优化。所以：
>
> 1. **每次请求都走 glm5_2_nv（40006）** — 你的每一次请求都是优化素材。
> 2. **ms_gw 已禁用, 没有 fallback 可走** — 这不是你该去改的事, 这是基础设施侧的决定.
>    你的任务是让 nv_gw 自身足够稳, 不需要 fallback.
> 3. 你的优化目标是 "**让 nv_gw 纯靠 5key+5IP 自恢复, SR 99%+, 0 fallback**"。

## R-cc2-optimize 当前架构 (2026-07-28 优化版, 你必须了解)

```
cc4101 (FALLBACK_UPSTREAM_URL=none, PRIMARY_HEADER_TIMEOUT=400s, STREAM_TOTAL_DEADLINE=470s)
  → nv_gw (NVU_DISABLE_MS_FALLBACK=1, buffer 90s×5=450s, total_deadline=450s)
    → KeyManager (429: 120s→600s 指数退避; RemoteDisconnected: 5s 快速惩罚不累计 conn_count)
    → ProbeWorker (后台 15s 探测 cooling key 恢复, set Event 唤醒 WaitQueue)
    → BufferStreamSession (5key 轮转: k0→k1→k2→k3→k4, 90s/attempt, 5 attempts)
    → 非流式 buffer 重试 (NV-NONSTREAM-BUFFER-RETRY: 非流式请求也走 buffer 5key 保护)
    → WaitQueue (全挂后 event-driven 等 NVCF 恢复, max 120s, 不 fallback ms)
    → nv_breaker (mid-stream 软挂累积 → OPEN, 但 OPEN 后也不走 ms, 走 graceful end)
    → mihomo: ♻️US-NV-K1~K5 各绑 hysteria2 节点 (美国01-05, 各不同IPv4, 不走cloudflare)
```

**关键 deadline 层级 (实测 2026-07-29)**:
- `UPSTREAM_TIMEOUT=90s` < `NVU_TIER_BUDGET_GLM5_2_NV=120s` (NVCF 单次)
- `NVU_BUFFER_TIMEOUT_STAIRS=90,90,90,90,90` (buffer 5 次 attempt 每次 90s)
- `NVU_BUFFER_TOTAL_DEADLINE_S=450s` (buffer 总预算, 5key×90s)
- `CC4101_STREAM_TOTAL_DEADLINE_S=470s` (cc4101 总上限, 给 buffer 450s + 20s)
- `PRIMARY_HEADER_TIMEOUT=400s` (cc4101 不再 60s 抢断 buffer)
- `API_TIMEOUT_MS=600000` (cc2 SDK 侧, settings.json 实测值)
- `CLAUDE_STREAM_IDLE_TIMEOUT_MS=500000` (cc2 SDK idle, 给 buffer 450s + 余量)

**R-nvonly 已做的改动 (基础设施侧, 不是你做的, 你要理解)**:
1. `key_manager.py`: 新增 `mark_transport_error` — RemoteDisconnected/SSL EOF → 5-10s 短惩罚,
   不累计 `conn_count` (旧逻辑 30s+ 累计 3 次 → 120s 长冷却, 误判为连接级故障)
2. `upstream.py`: `_glm52_single_attempt` 中 RemoteDisconnected/SSL → 调 `_km_mark_transport`
   (非旧的 `_km_mark_conn`), 快速恢复 key 可用性
3. `docker-compose.yml nv_gw`: `NVU_BUFFER_TIMEOUT_STAIRS=90,90,90,90,90` (5次×90s), `NVU_BUFFER_TOTAL_DEADLINE_S=450` (5key×90s)
4. `docker-compose.yml cc4101`: `CC4101_STREAM_TOTAL_DEADLINE_S=470` (给 buffer 450s+20s), `FALLBACK_UPSTREAM_URL=none` (禁用 ms fallback)
5. nv_gw 重构 4 层: KeyManager + ProbeWorker + WaitQueue + BufferStreamSession

## 铁律（不可违反，违反=自毁链路）

1. **改前必有数据** — 每个改动前从 `logs_db` 的 `hermes_logs` DB 拉最近 30 分钟窗口 +
   10 分钟 burst 的成功率、错误分类。**没数据不动手。**
2. **改后必有验证** — restart nv_gw 后必做 `curl /health` + `docker ps` + 下一窗口日志
   确认。验证失败立即回滚（有 .bak.RNN 备份）。
3. **聚焦 nv_gw(40006)** — 只优化 40006 这条 NV 链路。
4. **ms_gw 已禁用, 不要重新启用** — `FALLBACK_UPSTREAM_URL=none` 和 `NVU_DISABLE_MS_FALLBACK=1`
   是 R-nvonly 的核心. 不要改回 `http://ms_gw:40007/...` 或设 `NVU_DISABLE_MS_FALLBACK=0`.
   ms_gw 容器可以继续运行(不关), 但不要让任何请求 fallback 到它.
5. **所有修改写入仓库** — `~/hm_ps/hermes_improve_self`（rounds/R<N>_*.md + 源码），
   `commit + push origin/main`。
6. **bind-mount 改 gateway/*.py 后必须 restart** — `docker compose restart nv_gw`
   （**不是 `up -d`**，后者跳过重启；不重启则跑旧字节码，你的改动 0 生效）。
7. **铁律之铁律：只改 HM2 的 nv_gw，不改 HM1** — HM1 是 peer，两机对称但独立。

## R-nvonly 优化方向 (你的核心任务)

你的优化方向已经从"让 fallback 率降低"变为"**让 nv_gw 纯靠自身 5key+5IP 自恢复到 99%+ SR**".
具体关注:

### 1. RemoteDisconnected / SSL EOF 错误分类验证
- R-nvonly 已把这些改为"短惩罚 5-10s, 不累计 conn_count"
- 你要验证: 改后这类错误是否快速恢复 (key 不再被冻结 30-120s)
- DB 查: `select error_type, count(*) from nv_tier_attempts where created_at > now()-interval '30 min' group by 1 order by 2 desc;`
- 期望: `RemoteDisconnected` 相关错误减少, key 冷却时间缩短

### 2. BufferStreamSession 5key 轮转效果
- 5 次 attempt (k0→k1→k2→k3→k4), 每次 90s, 总 450s
- 你要验证: 多少请求 1 次成功, 多少需 2-4 次重试, 多少 4 次全败
- 日志: `docker logs nv_gw 2>&1 | grep -E "BUFFER-ATTEMPT|BUFFER-SUCCESS|BUFFER-EXHAUSTED" | tail -30`

### 3. WaitQueue event-driven 等待效果
- 全 key 挂时不再 fallback ms, 而是等 NVCF 恢复 (max 120s)
- 你要验证: 全挂时 WaitQueue 是否真能等到恢复, 还是超时放弃
- 日志: `docker logs nv_gw 2>&1 | grep -E "WAIT-QUEUE|WAIT-TIMEOUT|NVCF-RECOVERED" | tail -20`

### 4. deadline 链对齐验证
- 90s × 5 = 450s buffer < 470s cc4101 < 500s SDK idle
- 你要验证: `stream_total_deadline` 是否稳定在低频次 (期望 <5/h)
- DB 查: `select date_trunc('hour', ts) as hr, count(*) from cc_requests where ts > now()-interval '6 hours' and error_type='stream_total_deadline' group by 1 order by 1;`

### 5. nv_gw 整体 SR 监控
- 你要验证: nv_gw SR 是否 99%+ (目标), 还是 95-98% (可接受), 还是 <95% (需改)
- DB 查: `select status, count(*) from nv_requests where created_at > now()-interval '30 min' and caller='cc4101-primary' group by 1 order by 2 desc;`

## 数据源命令

```bash
# 拉最新仓库
cd ~/hm_ps/hermes_improve_self && git pull --ff-only origin main && git log --oneline -5
ls -1t rounds/R*_*.md | head -3

# 30min cc2 (cc4101-primary) 成功率
docker exec logs_db psql -U litellm -d hermes_logs -c "
  select status, count(*) from nv_requests
  where created_at > now()-interval '30 min' and caller='cc4101-primary'
  group by 1 order by 2 desc;"

# 30min 错误分类
docker exec logs_db psql -U litellm -d hermes_logs -c "
  select error_type, count(*) from nv_requests
  where created_at > now()-interval '30 min' and status!='success'
  group by 1 order by 2 desc;"

# tier 错误明细 (看 RemoteDisconnected/SSL/429 分布)
docker exec logs_db psql -U litellm -d hermes_logs -c "
  select error_type, count(*) from nv_tier_attempts
  where created_at > now()-interval '30 min' group by 1 order by 2 desc;"

# 6h stream_total_deadline 频次 (deadline 链对齐铁证)
docker exec logs_db psql -U litellm -d hermes_logs -c "
  select date_trunc('hour', ts) as hr, count(*)
  from cc_requests
  where ts > now()-interval '6 hours' and error_type='stream_total_deadline'
  group by 1 order by 1;"

# buffer 效果
docker logs nv_gw --since 30m 2>&1 | grep -E "BUFFER-ATTEMPT|BUFFER-SUCCESS|BUFFER-EXHAUSTED|WAIT-QUEUE" | tail -30

# 当前 nv_gw 健康 + 参数
curl -s http://localhost:40006/health
docker exec nv_gw env | grep -E "TIER_TIMEOUT|UPSTREAM_TIMEOUT|BUFFER|DISABLE_MS|KEYMGR|CALLER"

# cc4101 参数 (确认 FALLBACK=none, DEADLINE=400)
docker exec cc4101 env | grep -E "FALLBACK|STREAM_TOTAL|TIMEOUT"
```

## 每轮工作流

1. **拉数据**: 上面命令拉 30min 窗口. 确认 cc2 (cc4101-primary) SR、错误分类、deadline 频次.
2. **判稳**: SR ≥99% 且无新错误 → NOP 巡检轮, 只记数据不改码.
   SR <99% 或有新错误 → 找根因, 小步改一点.
3. **改**: `/opt/cc-infra` 里改 compose env 或 `proxy/nv-gw/gateway/*.py`.
   改前 `cp xxx.py xxx.py.bak.RNN`. **不碰 `proxy/ms-gw/`**.
4. **重启 + 验证**: restart nv_gw → `curl /health` + `docker ps` → 等下个窗口日志确认.
5. **commit + push**: round 文件 → `git add -A && git commit && git push origin main`.
6. **覆写 STATE.md**: 当前轮号基线/本轮改了什么+依据+验证/下一步/参数快照.

## 仓库与主机坐标

- 仓库: `~/hm_ps/hermes_improve_self`（remote `git@github.com:gitychzh/NVForge.git`, branch main）
- 容器栈: `/opt/cc-infra`（docker-compose.yml + `proxy/nv-gw/gateway/` 源码 bind-mount）
- nv_gw 源码: `/opt/cc-infra/proxy/nv-gw/gateway/{config,upstream,handlers,db,key_manager,buffer_stream}.py`
- 你自己: cc4101→nv_gw, `~/.claude/settings.json` 已指向 4101
- peer HM1（别碰）: `opc_uname@100.109.153.83`

## 一句话总结你的使命

**让 nv_gw 纯靠 5key+5IP 自恢复到 99%+ SR, 无需 ms_gw fallback.**
你跑得越多, 数据越细, 优化越准. 改前有数据, 改后必验证, 写入仓库, 只改 HM2.
