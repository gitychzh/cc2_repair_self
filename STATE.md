# STATE — cc2 自优化 nv_gw 链路 (R-nvonly 方向)

## 当前轮基线 (2026-07-29 14:28 CST, R-nvonly-post4 巡检轮)
- 主仓 git HEAD: `f279cfa R-nvonly-post3` (主仓, 外部监督者在 HM1 迭代; cc2 自主线 round 在 worktree)
- **本轮 R-nvonly-post4 (hm2_cc2)**: NOP 巡检 + 恢复期持续爬升确认.
  cc2 30min 52/53→SR98.1% (1×buffer_exhausted 设计消化点); 6h 499/540→SR92.4%
  (41×502+1×499 全 buffer_exhausted/all_tiers 设计消化点). cc4101 fallback=0(6h)→破釜沉舟持续生效.
  transport 短惩罚 30min 8次 (SSLEOF×4/429×3/RemoteDisconnected×1) 全 pexec 内部吸收, 0 冒泡成 cc2 502.
  5key 平时段高效 (全窗口样本 1-attempt SUCCESS). 60min 时序后40min 零 502 → 间歇期已过 SR 爬升中.
  zombie×9+all_tiers×11 属 unknown/other(别的agent,非cc2). 0 改动 0 restart.
- cc2 自主线: …→R-keyretry→(ms_gw禁用/方向转变)→R-nvonly-post1→post2→post3→**R-nvonly-post4(本轮)**

## 当前架构 (2026-07-29 R-nvonly, 实测确认)
```
cc4101 (FALLBACK_UPSTREAM_URL=none, PRIMARY_HEADER_TIMEOUT=400, CC4101_STREAM_TOTAL_DEADLINE_S=470)
  → nv_gw (NVU_DISABLE_MS_FALLBACK=1, 5key×90s=450s buffer, no fallback)
    → KeyManager (429: 120→600s 退避; RemoteDisconnected/SSL: 5-10s 短惩罚不累计 conn_count)
    → ProbeWorker (后台15s探测 cooling key 恢复→Event 唤醒 WaitQueue)
    → BufferStreamSession (5key 轮转 k0→k4, 90s/attempt, 5 attempts, 450s total)
    → WaitQueue (全挂后 event-driven 等 NVCF 恢复, max 120s, 不 fallback ms)
    → mihomo: US-NV-K1~K5 各绑 hysteria2 节点(各不同IPv4)
```
**deadline 链 (实测)**: 90s/buffer-attempt×5=450s buffer < 470s cc4101 < 500s SDK idle < 600s API_TIMEOUT.
顶满, 不可再提 (470 墙留 SDK 600s 墙 30s flush, buffer 450s 留 cc4101 20s).

## R-nvonly 核心铁律 (本轮确认持续生效)
- `NVU_DISABLE_MS_FALLBACK=1` 不可改回 0; `FALLBACK_UPSTREAM_URL=none` 不可改回 ms_gw.
- 破釜沉舟: 6h 41×502+1×499 全在 nv_gw 侧 (buffer_exhausted/all_tiers) 消化, cc4101 fallback=0.
- 没有 fallback 兜底 → nv_gw 必须纯靠 5key+5IP 自恢复, 这是唯一优化方向.

## 本轮关键认知
1. **恢复期持续爬升**: 30min SR 98.1% > post3 97.9% > 6h SR 92.4%. 60min 时序后40min 零 502,
   间歇期已过, SR 单调爬升中.
2. **buffer_exhausted 是"消化终点"非退化**: 1×502 发生在 NVCF 间歇窗口 (5key×90s 全败),
   改 nv_gw 配置无法解决 (基础设施侧问题), 贸然调参撞 deadline 链.
3. **transport 短惩罚机制持续工作**: 30min 8 次 SSLEOF/RemoteDisconnected/429 全 nv_gw 内部 pexec 吸收, 0 冒泡.
4. **5key 平时段高效**: 全窗口样本 1-attempt SUCCESS, 5key 轮转产能仅在 NVCF 间歇全挂时启用.
5. **zombie_empty_completion + all_tiers 仍属 unknown/other caller (别的 agent 非 cc2)**:
   30min 9+6+5=20 次全非 cc2, cc2 自己 0 次. 铁律: 不越权改别的 agent 路径.
6. **stream_total_deadline 未在窗口出现**: 470 墙紧, 长输出走 buffer_exhausted, 不记 deadline.
7. **HM1 仍 R2422 (BIG_INPUT_THRESHOLD 375000 等); HM2 仍 250000/KEY_COOLDOWN_S=60**.
   **铁律: 只改 HM2, 不抄 HM1 参数.**

## 三阈值判稳 (本轮)
| 阈值 | 30min 实测 | 判定 |
|------|-----------|------|
| cc2 (cc4101-primary) SR | 52/53 = 98.1% | ⚠<99% (1×buffer_exhausted 设计消化点) |
| cc4101 真 fallback | 0 (6h 全量) | ✓ |
| 无新错误类型 | zombie/all_tiers 属 unknown/other(非cc2); cc2 仅 buffer_exhausted(已知消化点) | ✓ |
→ 1×502 = 设计预期 (NVCF 间歇全挂, 改码无效不越 deadline 链) → **冻结 NOP, 0 改动 0 restart**

## 数据源命令 (R-nvonly, post4 沿用)
```bash
# 30min cc2 SR
docker exec logs_db psql -U litellm -d hermes_logs -c "
  select status, count(*) from nv_requests
  where created_at > now()-interval '30 min' and caller='cc4101-primary' group by 1 order by 2 desc;"
# 30min 错误分类 (含 caller 归属, 区分 cc2 vs 别的 agent)
docker exec logs_db psql -U litellm -d hermes_logs -c "
  select caller, status, error_type, count(*) from nv_requests
  where created_at > now()-interval '30 min' and status!=200 group by 1,2,3 order by 4 desc;"
# 30min tier transport 错误
docker exec logs_db psql -U litellm -d hermes_logs -c "
  select error_type, count(*) from nv_tier_attempts
  where created_at > now()-interval '30 min' group by 1 order by 2 desc;"
# 6h cc2 SR + 错误分类
docker exec logs_db psql -U litellm -d hermes_logs -c "
  select status, count(*) from nv_requests
  where created_at > now()-interval '6 hours' and caller='cc4101-primary' group by 1 order by 2 desc;"
# 6h fallback 铁证 (R-nvonly 核心: 应恒 0)
docker exec logs_db psql -U litellm -d hermes_logs -c "
  select error_type, count(*) from cc_requests
  where ts > now()-interval '6 hours' and error_type like 'fallback%' group by 1 order by 2 desc;"
# 60min 时序 (恢复期斜率)
docker exec logs_db psql -U litellm -d hermes_logs -c "
  select date_trunc('minute', created_at) as m, status, count(*) from nv_requests
  where created_at > now()-interval '60 min' and caller='cc4101-primary' group by 1,2 order by 1;"
# buffer 轮转效果
docker logs nv_gw --since 30m 2>&1 | grep -E "BUFFER-|WAIT-|NVCF-RECOVERED" | tail -30
# 健康 + env
curl -s http://localhost:40006/health
docker exec nv_gw env | grep -E "DISABLE_MS|BUFFER|TIER|UPSTREAM_TIMEOUT|KEYMGR|CALLER"
docker exec cc4101 env | grep -E "FALLBACK|STREAM_TOTAL|PRIMARY_HEADER"
```

## env 快照 (docker exec 实测, 无漂移, 同 post1/2/3)
```
nv_gw: NVU_DISABLE_MS_FALLBACK=1 | NVU_BUFFER_CALLERS=cc4101-primary | NVU_BUFFER_MAX_RETRIES=5 |
  NVU_BUFFER_TIMEOUT_STAIRS=90,90,90,90,90 | NVU_BUFFER_TOTAL_DEADLINE_S=450 |
  NVU_CALLER_RETRY=0 | NVU_TIER_BUDGET_GLM5_2_NV=120 | UPSTREAM_TIMEOUT=90 |
  NVU_KEYMGR_429_BASE_COOLDOWN=120/MAX_COOLDOWN=600 | NVU_KEYMGR_CONN_BASE_COOLDOWN=30/FAIL_THRESHOLD=3/LONG_COOLDOWN=120 |
  NVU_KEYMGR_CONN_MAX_COOLDOWN=60 | NVU_EMPTY_200_FASTBREAK=3 | TIER_TIMEOUT_BUDGET_S=180/COOLDOWN_S=180 |
  KEY_COOLDOWN_S=60 | NVU_BIG_INPUT_THRESHOLD=250000 (HM1上R2422已改375000, HM2仍此值)
cc4101: FALLBACK_UPSTREAM_URL=none | CC4101_STREAM_TOTAL_DEADLINE_S=470 | PRIMARY_HEADER_TIMEOUT=400
  | UPSTREAM_TIMEOUT=130 / IDLE_TIMEOUT=150
/health: ok, nv_num_keys=5, nv_default_model=glm5_2_nv
容器: nv_gw Up 2h(RC=0) / cc4101 Up 7h / logs_db Up 2d (本轮无 restart)
```

## 下一轮该做什么
1. 继续巡检. 盯 cc2 30min SR 是否回 100% (60min 后40min 零 502, 很可能零 502).
2. 6h SR 是否随恢复期持续爬升 (当前 92.4%, 间歇消化点随时间淡出 6h 窗口).
3. 6h buffer/all_tiers 频次是否持续下降, fallback 是否恒 0.
4. transport 短惩罚是否持续在 pexec 层吸收 (SSLEOF/RemoteDisconnected 不冒泡).
5. 盯 unknown caller zombie_empty_completion 是否扩散到 cc2.
6. 长驻机制: 每30min touch ~/.claude/cc2.heartbeat (watchdog 15min); 改 .py 触发 R-guard(py_compile+restart+health); auto-compact 后从 STATE 接棒.
7. 铁律: 改前数据, 改后验证, 聚焦 40006, 不碰 40007 (NVU_DISABLE_MS_FALLBACK=1 不可改回0), 只改 HM2 (不抄 HM1 参数), 写入仓库, 尽量多走 glm5_2_nv.

## 回滚锚点 (本轮无改动, 无需回滚)
- 未改任何 gateway/*.py, 未改 compose env, 未重启容器.
- R-nvonly 配置锚点: 5key×90s/450s buffer, 470s cc4101, fallback=none, DISABLE_MS_FALLBACK=1.
- cc_s2/cc_s3 快照 (commit 5ec9c7c/d7392cf) 为 R-buffer 前, 不含 buffer_stream.py, 守护待用.

---
## 最近3轮摘要
- **R-nvonly-post4 (hm2_cc2, 本轮)**: NOP 巡检 + 恢复期持续爬升确认. cc2 30min 52/53→SR98.1%
  (1×buffer_exhausted 设计消化点); 6h 499/540→SR92.4% (41×502+1×499 全 nv_gw 侧消化).
  cc4101 fb=0(6h)→破釜沉舟持续生效. transport 短惩罚 30min 8次 (SSLEOF×4/429×3/RemoteDisconnected×1)
  全 pexec 内部吸收, 0 冒泡. 5key 平时段高效 (全窗口 1-attempt SUCCESS). 60min 时序后40min 零 502
  → 间歇期已过 SR 爬升中. zombie×9+all_tiers×11 属 unknown/other(别的agent非cc2). 1×502=设计消化点
  (改码无效不越deadline链 450<470<500) → 冻结 NOP. 0改动0restart.
- R-nvonly-post3 (hm2_cc2): NOP 巡检 + 恢复期趋势确认. cc2 30min 46/47→SR97.9% (1×buffer_exhausted);
  6h 494/535+1×499→SR92.4%. cc4101 fb=0(6h). transport 短惩罚 7次全吸收. 5key 轮转自恢复见效
  (req=d6a0dabb 2-attempt 122s 救回). 30min SR(97.9%)>6h SR(92.4%) 恢复期延续. 0改动0restart.
- R-nvonly-post2 (hm2_cc2): NOP 巡检 + NVCF 间歇恢复期基线. cc2 30min 42/43→SR97.7% (1×buffer_exhausted);
  6h 484/527→SR91.8%. cc4101 fb=0(6h). transport 短惩罚 10次全吸收. 5key 轮转自恢复见效 (req1f968636 3-attempt 救回).
  间歇期09h14×502→14h1×502清零. 0改动0restart.

---
## 长驻 session 设计 (2026-07-24 落地, 沿用)
- 旧 cc2-resume(1min oneshot) stop+disable. cc2-long(8h 长驻 session)就位.
- ~/.config/systemd/user/cc2-long.{timer,service}: 8h 周期换 session.
- ~/.config/systemd/user/cc2-longwatch.{timer,service}: 5min 检心跳, >15min 无更新 kill.
- agent 自循环铁律: 每子任务→Write STATE; 每30min→touch heartbeat; 改.py→py_compile+restart+health; auto-compact 后从 STATE 接棒.
