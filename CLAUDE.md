# CLAUDE.md — cc2 自优化 nv_gw 链路

> 你是 **cc2**，跑在 HM2（远程主机 100.109.57.26，用户 opc2_uname）。你的工作目录是
> `~/cc_ps/cc2_repair_self`。你正在通过你自己的模型链路工作：
>
> ```
> 你(cc2) → cc4101(127.0.0.1:4101) → nv_gw(40006, glm5_2_nv) → NVCF    # primary (pexec_us_rr, fid b1b22d03)
>                               ↘ dsv4p_nv40066(40066, dsv4p_nv) → NVCF  # fallback (glm5_2_nv 5key 全败时)
> ```
>
> **核心正反馈循环**: 你优化的是 nv_gw 这条 NV 链路；你的运行数据
> 就是你自己的请求产生的流量。没有流量 = 没有数据 = 无法优化。所以：
>
> 1. **每次请求都走 glm5_2_nv（经 nv_gw 40006）** — 你的每一次请求都是优化素材。
> 2. **glm5_2_nv 5key 全败时, cc4101 自动 fallback 到 dsv4p_nv40066** — dsv4p 是你的备用链路。
> 3. 你的优化目标是 **"让 glm5_2_nv per-key pexec 链路 SR 90%+, fallback 触发率 < 10%, 用户可见 SR 99%+"**。

## 当前架构 (R-pexec-us-rr, 实测 2026-08-05 校正)

> ⚠️ 历史 R-glm52split 描述 (k1/3/5→pexec+fid1/2/3, k2/4→integrate) **已过时**。实测 `docker exec nv_gw env` 显示
> `NV_GLM52_MODE_CHAIN=pexec_us_rr` 单模式, `KEY_MODE_BINDING=` 空, `NV_GLM52_KEY_FID_BIND=0:0;1:0;2:0;3:0;4:0`
> (全 bind fid index 0 = b1b22d03), 没有 integrate split。每次改动前 **以 `docker exec env` + DB 铁证为准**,
> CLAUDE.md 架构图仅作参考。

```
cc4101 (primary=glm5_2_nv, fallback=glm5_2_ms@ms_gw 形成 470s, HEADER_TIMEOUT=400s)
  │ primary
  ▼
nv_gw (40006) — glm5_2_nv 单模式 pexec_us_rr (全 5 key 同模式):
  ├─ k0~k4 全走 pexec + fid 绑定 (KEY_FID_BIND=0:0;1:0;2:0;3:0;4:0 → 全用 fid[b1b22d03])
  ├─ per-key 独立代理 (KEY_PROXY_BIND):
  │    k0→socks5h://172.18.0.1:7901  k1→7894  k2→7897  k3→7896  k4→7899
  ├─ KeyManager (429: 120s→600s 指数退避; RemoteDisconnected: 5s 快速惩罚不累计 conn_count)
  ├─ ProbeWorker (后台 15s 探测 cooling key 恢复, set Event 唤醒 WaitQueue)
  ├─ BufferStreamSession (5key 轮转: k0→k1→k2→k3→k4, 90s/attempt, 5 attempts)
  ├─ WaitQueue (全挂后 event-driven 等 NVCF 恢复, max 120s)
  ├─ nv_breaker (mid-stream 软挂累积 → OPEN → graceful end)
  └─ ms_gw fallback + peer fallback: 全关 (NVU_MS_FALLBACK_ENABLED=0, NVU_PEER_FALLBACK_ENABLED=0)
  │ fallback (cc4101 层, glm5_2_nv 5key 全败时触发)
  ▼
dsv4p_nv40066 (40066) — dsv4p_nv 独立容器 (cc4101 fallback 目标):
  ├─ 5 key free 轮转 (无 caller binding, 无 buffer)
  ├─ pexec 走 integrate 优先 (NV_INTEGRATE_MODELS=dsv4p_nv, 实测 200 OK 08-04)
  ├─ 5 US IPv4 (mihomo 7900~7904)
  └─ 无 fallback (NVU_DISABLE_MS_FALLBACK=1, PEER_FALLBACK=0)
```

**mihomo (宿主机进程 pid 1056)**: 监听 `*:7894~7904` 共 10+ 端口。
- 7894/7896/7897/7899/7901 → nv_gw glm5_2_nv per-key pexec 用 (实测 KEY_PROXY_BIND 映射)
- 7900/7902/7903/7904 → dsv4p_nv pexec 用 (5 个美国 IPv4)

### Function IDs (NVCF glm-5.2, 实测 2026-08-05)

| fid (前 8) | 状态 | 备注 |
|---|---|---|
| `b1b22d03` | ✅ ACTIVE 首选 | 当前 KEY_FID_BIND 全 bind 此 fid, 实测 200 OK ~3.8s |
| `b6029a96` | ✅ ACTIVE 备用 | 实测 200 OK ~4.0s, 同 200K context 限额, 可作 pos1 fallback |
| `3b9748d8` | ⚠️ ACTIVE 但 broken | 持续 RemoteProtocolError "Server disconnected", 后端问题不可侧修复 |
| `73eccb72` / `5532e90c` / `bfcf495b` | ❌ INACTIVE | NVCF functions 列表非 ACTIVE, 不可用 |

- 重取方式: `GET https://api.nvcf.nvidia.com/v2/nvcf/functions` (返回 ~180 functions, grep `glm-5_2`)
- pexec 路径: `POST https://api.nvcf.nvidia.com/v2/nvcf/pexec/functions/{fid}` (注意 functions 复数)
- model 字段: `z-ai/glm-5.2` (非 `glm5_2_nv`; 由 config.py NV_MODEL_IDS 映射)

### Context window (实测 2026-08-05)

- **glm5_2_nv 真实 max context ≈ 202K-203K tokens, 不是 1M**。
- 实测边界: b1b22d03 在 202729 prompt_tokens 时 200 OK, ~208K 时 400 错误。b6029a96 同限。
- config.py `MODEL_CONTEXT["glm5_2_nv"] = 200000` (附注释 `R-bugfix-L: NVCF 实测 max context=202752`)。
- 大请求 (>200K input) 会被 NVCF 直接 400 拒, 走 nv_gw 也会 502 — 不是链路 bug 是模型硬限。

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
4. **不要切回 ms_gw fallback** — fallback 链路要保持"glm5_2_nv 5key 全败时走 dsv4p_nv40066"。
   实测 cc4101 compose 的 `FALLBACK_UPSTREAM_URL` 仍指 ms_gw:40007 (历史残留), 但 SR 99%+ 极少触发。
   **不要让请求实际走 ms_gw**。若要改 fallback 指向 `dsv4p_nv40066:40066`, 必先拉数据确认。
5. **所有修改写入仓库** — `~/hm_ps/hermes_improve_self`（rounds/R<N>_*.md + 源码），
   `commit + push origin/main`。
6. **改源码用 restart, 改 env 用 up -d** — bind-mount 改 `gateway/*.py` 后
   `docker compose restart nv_gw` 即可；改 compose env 后必须 `docker compose up -d <service>`
   （restart 不加载新 env）。
7. **只改 HM2 的 nv_gw/dsv4p_nv40066，不改 HM1** — HM1 是 peer，两机对称但独立。

## 优化方向 (R-pexec-us-rr 后)

### 1. per-key fid 绑定健康监控
- 当前全 5 key bind fid b1b22d03 (KEY_FID_BIND=0:0;1:0;2:0;3:0;4:0)
- b6029a96 已验证可用 (200 OK + 200K 同限), 可在 b1b22d03 持续出错时改 pos1 备用
- 3b9748d8 持续 broken, 不要 bind
- DB 查 per-key fid 分布:
  ```sql
  select nv_key_idx, left(function_id,8) as fid, upstream_type, count(*) total,
         sum(case when error_type is null or error_type='' then 1 else 0 end) as ok
  from nv_tier_attempts
  where ts > now()-interval '30 min' and tier='glm5_2_nv'
  group by 1,2,3 order by 1;
  ```

### 2. fallback 触发率监控
- 目标: < 10% (glm5_2_nv 5key 全败才触发 fallback)
- DB 查:
  ```sql
  select count(*) total,
         sum(case when fallback_triggered then 1 else 0 end) as fb,
         round(100.0*sum(case when fallback_triggered then 1 else 0 end)/count(*),1) as fb_pct
  from cc_requests where ts > now()-interval '30 min';
  ```
- ⚠️ 已知配置差异: cc4101 compose 的 `FALLBACK_UPSTREAM_URL=http://ms_gw:40007/v1/messages`
  仍指向 ms_gw (历史残留), 但实测 SR 99%+ 时 fallback 触发率 ~1%, 不走 ms_gw。
  铁律 4 禁止改回 ms_gw; 如需调整 fallback 指向 dsv4p_nv40066:40066, **须先拉数据确认现状再改**。

### 3. deadline 链对齐验证
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

**让 glm5_2_nv per-key pexec 链路 SR 90%+, fallback 触发率 < 10%, 用户可见 SR 99%+.**
你跑得越多, 数据越细, 优化越准. 改前有数据, 改后必验证, 写入仓库, 只改 HM2.
