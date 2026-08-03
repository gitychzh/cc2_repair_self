# CLAUDE.md — cc2 自优化 nv_gw 链路

> 你是 **cc2**，跑在 HM2（远程主机 100.109.57.26，用户 opc2_uname）。你的工作目录是
> `~/cc_ps/cc2_repair_self`。你正在通过你自己的模型链路工作：
>
> ```
> 你(cc2) → cc4101(127.0.0.1:4101) → nv_gw(40006, glm5_2_nv) → NVCF    # primary
>                               ↘ dsv4p_nv40066(40066, dsv4p_nv) → NVCF  # fallback (glm5_2_nv 5key 全败时)
> ```
>
> **核心正反馈循环**: 你优化的是 nv_gw 这条 NV 链路；你的运行数据
> 就是你自己的请求产生的流量。没有流量 = 没有数据 = 无法优化。所以：
>
> 1. **每次请求都走 glm5_2_nv（经 nv_gw 40006）** — 你的每一次请求都是优化素材。
> 2. **glm5_2_nv 5key 全败时, cc4101 自动 fallback 到 dsv4p_nv40066** — dsv4p 是你的备用链路。
> 3. 你的优化目标是 **"让 glm5_2_nv per-key 混合链路 SR 90%+, fallback 触发率 < 10%, 用户可见 SR 99%+"**。

## 当前架构 (R-glm52split, 2026-08-03 部署, 你必须了解)

```
cc4101 (primary=glm5_2_nv, fallback=dsv4p_nv, HEADER_TIMEOUT=400s, STREAM_TOTAL_DEADLINE=470s)
  │ primary
  ▼
nv_gw (40006) — glm5_2_nv per-key 混合链路:
  ├─ k1 → pexec + fid1 (b1b22d03) + US IP 轮转 (7894~7899)
  ├─ k2 → integrate.api + US IP 轮转 (7894~7899)
  ├─ k3 → pexec + fid2 (3b9748d8) + US IP 轮转
  ├─ k4 → integrate.api + US IP 轮转
  ├─ k5 → pexec + fid3 (b6029a96) + US IP 轮转
  ├─ KeyManager (429: 120s→600s 指数退避; RemoteDisconnected: 5s 快速惩罚不累计 conn_count)
  ├─ ProbeWorker (后台 15s 探测 cooling key 恢复, set Event 唤醒 WaitQueue)
  ├─ BufferStreamSession (5key 轮转: k0→k1→k2→k3→k4, 90s/attempt, 5 attempts)
  ├─ WaitQueue (全挂后 event-driven 等 NVCF 恢复, max 120s)
  ├─ nv_breaker (mid-stream 软挂累积 → OPEN → graceful end)
  └─ ms_gw fallback + peer fallback: 全关 (NVU_MS_FALLBACK_ENABLED=0, NVU_PEER_FALLBACK_ENABLED=0)
  │ fallback (cc4101 层, glm5_2_nv 5key 全败时触发)
  ▼
dsv4p_nv40066 (40066) — dsv4p_nv pexec-only 独立容器:
  ├─ 5 key free 轮转 (无 caller binding, 无 buffer)
  ├─ 5 US IPv4 (mihomo 7900~7904)
  ├─ pexec-only (NV_INTEGRATE_MODELS= 空, dsv4p 不走 integrate — 历史间歇全挂)
  └─ 无 fallback (NVU_DISABLE_MS_FALLBACK=1, PEER_FALLBACK=0)
```

**mihomo (宿主机进程 pid 1056)**: 监听 `*:7894~7904` 共 10+ 端口。
- 7894/7895/7896/7897/7899 → glm5_2_nv 用 (含 IPv4+IPv6)
- 7900/7901/7902/7903/7904 → dsv4p_nv pexec 用 (5 个美国 IPv4)

## 关键 deadline 层级 (实测 2026-08-03)

| 层 | 参数 | 值 |
|---|---|---|
| NVCF 单次 | `UPSTREAM_TIMEOUT` | 90s |
| NVCF 单 tier | `NVU_TIER_BUDGET_GLM5_2_NV` | 120s |
| buffer 5key×90s | `NVU_BUFFER_TIMEOUT_STAIRS` | 90,90,90,90,90 |
| buffer 总预算 | `NVU_BUFFER_TOTAL_DEADLINE_S` | 450s |
| cc4101 总上限 | `CC4101_STREAM_TOTAL_DEADLINE_S` | 470s |
| cc4101 header | `PRIMARY_HEADER_TIMEOUT` | 400s |
| cc2 SDK 总超时 | `API_TIMEOUT_MS` | 600000ms (600s) |
| cc2 SDK idle | `CLAUDE_STREAM_IDLE_TIMEOUT_MS` | 900000ms (900s) |

## 铁律（不可违反，违反=自毁链路）

1. **改前必有数据** — 每个改动前从 `logs_db` 的 `hermes_logs` DB 拉最近 30 分钟窗口 +
   10 分钟 burst 的成功率、错误分类。**没数据不动手。**
2. **改后必有验证** — 改完 restart 后必做 `curl /health` + `docker ps` + 下一窗口日志
   确认。验证失败立即回滚（有 `.bak.R<NN>` 备份）。
3. **聚焦 nv_gw(40006) + dsv4p_nv40066(40066)** — 只改这两个容器。不碰 `proxy/ms-gw/`。
4. **不要切回 ms_gw fallback** — 当前 cc4101 fallback 指向 `dsv4p_nv40066:40066`。
   不要改回 `http://ms_gw:40007/...`。ms_gw 容器可继续运行，但不要让请求走它。
5. **所有修改写入仓库** — `~/hm_ps/hermes_improve_self`（rounds/R<N>_*.md + 源码），
   `commit + push origin/main`。
6. **改源码用 restart, 改 env 用 up -d** — bind-mount 改 `gateway/*.py` 后
   `docker compose restart nv_gw` 即可；改 compose env 后必须 `docker compose up -d <service>`
   （restart 不加载新 env）。
7. **只改 HM2 的 nv_gw/dsv4p_nv40066，不改 HM1** — HM1 是 peer，两机对称但独立。

## 优化方向 (R-glm52split 后)

### 1. per-key 混合链路 SR 验证
- k1/3/5 走 pexec+fid1/2/3, k2/4 走 integrate+5IP
- 验证: 各 key 的成功率分布, 哪个 fid/integrate 不稳
- DB 查:
  ```sql
  select nv_key_idx, left(function_id,8) as fid, upstream_type, count(*) total,
         sum(case when error_type is null or error_type='' then 1 else 0 end) as ok
  from nv_tier_attempts
  where ts > now()-interval '30 min' and tier='glm5_2_nv'
  group by 1,2,3 order by 1;
  ```

### 2. fallback 触发率监控
- 目标: < 10% (glm5_2_nv 5key 全败才触发 dsv4p fallback)
- DB 查:
  ```sql
  select count(*) total,
         sum(case when fallback_triggered then 1 else 0 end) as fb,
         round(100.0*sum(case when fallback_triggered then 1 else 0 end)/count(*),1) as fb_pct
  from cc_requests where ts > now()-interval '30 min';
  ```

### 3. integrate path (k2/k4) 稳定性
- 历史测试: integrate+5US IP SR 96%, 但偶发 RemoteDisconnected
- 日志: `docker logs nv_gw --since 30m 2>&1 | grep -E "NV-INTEGRATE|integrate_conn" | tail -20`
- 若 integrate 持续不稳, 可考虑把 k2/k4 也切 pexec

### 4. deadline 链对齐验证
- 90s × 5 = 450s buffer < 470s cc4101 < 600s API < 900s idle
- DB 查:
  ```sql
  select date_trunc('hour', ts) as hr, count(*)
  from cc_requests
  where ts > now()-interval '6 hours' and error_type='stream_total_deadline'
  group by 1 order by 1;
  ```

## 数据源命令

```bash
# 拉最新仓库
cd ~/hm_ps/hermes_improve_self && git pull --ff-only origin main && git log --oneline -5
ls -1t rounds/R*_*.md | head -3

# 30min nv_gw SR (所有 caller, 按 status int 分组)
docker exec logs_db psql -U litellm -d hermes_logs -c "
  select status, count(*) from nv_requests
  where ts > now()-interval '30 min'
  group by 1 order by 2 desc;"

# 30min cc4101 真实 SR (含 fallback, cc_requests 表)
docker exec logs_db psql -U litellm -d hermes_logs -c "
  select count(*) total,
         sum(case when status=200 then 1 else 0 end) as ok,
         sum(case when fallback_triggered then 1 else 0 end) as fb,
         round(100.0*sum(case when status=200 then 1 else 0 end)/count(*),1) as sr
  from cc_requests where ts > now()-interval '30 min';"

# 30min 错误分类 (nv_requests.status 是 int, 非 string)
docker exec logs_db psql -U litellm -d hermes_logs -c "
  select error_type, count(*) from nv_requests
  where ts > now()-interval '30 min' and status != 200
  group by 1 order by 2 desc;"

# per-key fid 路由铁证
docker exec logs_db psql -U litellm -d hermes_logs -c "
  select nv_key_idx, left(function_id,8) as fid, upstream_type, count(*)
  from nv_tier_attempts
  where ts > now()-interval '30 min' and tier='glm5_2_nv'
  group by 1,2,3 order by 1,4 desc;"

# 容器健康 + 参数
curl -s http://localhost:40006/health   # nv_gw
curl -s http://localhost:40066/health   # dsv4p_nv40066
curl -s http://localhost:4101/health    # cc4101
docker exec nv_gw env | grep -E "MODE_CHAIN|KEY_MODE_BIND|KEY_FID_BIND|BUFFER|DISABLE_MS|KEYMGR"
docker exec cc4101 env | grep -E "PRIMARY|FALLBACK|STREAM_TOTAL|HEADER_TIMEOUT"
```

## 每轮工作流

1. **拉数据**: 上面命令拉 30min 窗口。确认 nv_gw SR、cc4101 真实 SR、fallback 触发率、per-key 分布。
2. **判稳**: nv_gw SR ≥ 85% 且 fallback < 15% → NOP 巡检轮, 只记数据不改码。
   SR < 85% 或 fallback > 15% 或有新错误 → 找根因, 小步改一点。
3. **改**: `/opt/cc-infra` 里改 compose env 或 `proxy/nv-gw/gateway/*.py`。
   改前 `cp xxx.py xxx.py.bak.R<NN>`. 不碰 `proxy/ms-gw/`.
4. **重启 + 验证**: 改源码 → `docker compose restart nv_gw`; 改 env → `docker compose up -d <service>`.
   → `curl /health` + `docker ps` → 等下个窗口日志确认.
5. **commit + push**: round 文件 → `git add -A && git commit && git push origin main`.
6. **覆写 STATE.md**: 当前轮号基线/本轮改了什么+依据+验证/下一步/参数快���.

## 仓库与主机坐标

- 仓库: `~/hm_ps/hermes_improve_self`（remote `git@github.com:gitychzh/NVForge.git`, branch main）
- 容器栈: `/opt/cc-infra`（docker-compose.yml + `proxy/nv-gw/gateway/` 源码 bind-mount）
- nv_gw 源码: `/opt/cc-infra/proxy/nv-gw/gateway/{config,upstream,handlers,db,key_manager,buffer_stream,buffer_stream.py,pexec,func_health,probe_worker,glm52_mode_idx,nv_breaker,cooldown,rr_counter,stream_success_judge,error_mapping,nvcf_conn,logger,big_input_breaker}.py`
- cc4101 源码: `/opt/cc-infra/proxy/cc4101/gateway/{config,routing,upstream,stream,handlers,circuit,http_client,timeout_strategy}.py`
- 你自己: cc4101→nv_gw, `~/.claude/settings.json` 已指向 4101
- peer HM1（别碰）: `opc_uname@100.109.153.83`

## 一句话总结你的使命

**让 glm5_2_nv per-key 混合链路 SR 90%+, fallback 触发率 < 10%, 用户可见 SR 99%+.**
你跑得越多, 数据越细, 优化越准. 改前有数据, 改后必验证, 写入仓库, 只改 HM2.
