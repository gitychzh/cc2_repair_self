# STATE

## 号基线 (2026-07-27 08:55 CST, R-buffer-post6 巡检轮)
- 主仓 git HEAD: `3635f40 R-buffer-post6` (本轮, hm2_cc2, 已 push)
- **本轮 R-buffer-post6 (hm2_cc2)**: NOP 巡检 + 修正 post5 数据认知 bug. cc2 链路 100%
  (30min 27/27), 6h 383/3 (SR99.2%, 3 全 BUG-A 家族 buffer_exhausted). 0 改动 0 restart.
- cc2 自主线: R2191→R2192→R2322→R2326→R-buffer→R-buffer-post1→R-buffer-post2→R-buffer-post3
  (480→580)→R-buffer-post4→R-buffer-post5→**R-buffer-post6(本轮)**
- 中间 R2322→R2395 的 HM1 桥接轮 (R2382~R2396 等, 作者 opc_uname 在 HM1) 对 HM2 无关, 改的是 HM1 compose.

## 上一轮发生了什么 (R-keyretry 部署, 2026-07-27 09:26 CST)

**R-keyretry: NVCF key1 同 key 间隔重试 3 次 (2s→4s→8s)** — 用户直接指令, 非 cc2 自主轮.

### 改了什么
1. config.py: 新增 `NVU_CALLER_RETRY` (int, 默认 0=禁用) + `NVU_CALLER_RETRY_INTERVALS` (list, 默认 "2,4,8")
2. upstream.py `_try_glm52_mode_chain` caller-bound 分支:
   - 旧: `_chain_max_attempts=1` (只试 1 次 key1, 失败立刻 all_keys_exhausted → ms_gw)
   - 新: `_chain_max_attempts=3` (同 key1 重试 3 次, 间隔 2s→4s→8s, 3 次全败才 all_keys_exhausted → ms_gw)
   - 重试时跳过 key cooldown 检查 (cooldown 会阻断同 key 重试)
   - 每次重试记 `NV-GLM52-RETRY-SLEEP` + `NV-GLM52-KEY-FAULT` (含 attempt=N/3, remaining=M)
3. docker-compose.yml: 新增 `NVU_CALLER_RETRY=3` + `NVU_CALLER_RETRY_INTERVALS=2,4,8`
4. 备份: upstream.py.bak.R-keyretry, config.py.bak.R-keyretry, docker-compose.yml.bak.R-keyretry

### 部署验证
- py_compile OK ✓
- health OK ✓
- env 生效: `NVU_CALLER_RETRY=3`, `NVU_CALLER_RETRY_INTERVALS=2,4,8` ✓
- 实测 req=644bbd2b: attempt 1/3 fault → sleep 2s → attempt 2/3 fault → sleep 4s → attempt 3/3 fault → CHAIN-FAIL → ms_gw fallback ✓
- 日志标签: `NV-GLM52-CHAIN`(启动) + `NV-GLM52-RETRY-SLEEP`(间隔) + `NV-GLM52-KEY-FAULT`(每次失败, 含 attempt/remaining)

### cc2 下一轮该做什么 (R-keyretry-post1 验证轮)
1. 拉 30min 数据看同 key 重试效果:
   - `docker logs nv_gw 2>&1 | grep -E "NV-GLM52-CHAIN|RETRY-SLEEP|KEY-FAULT|CHAIN-SUCCESS|GLM52-SUCCESS" | tail -50`
   - 看 NVCF key1 的成功率是否因重试而提升 (期望: 部分请求第 2/3 次重试成功, 不用 fallback ms_gw)
   - 看重试日志统计: 多少请求 1 次就成功, 多少需 2-3 次重试, 多少 3 次全败
2. DB 查 cc4101-primary SR + fallback 率对比:
   - 部署前 6h: primary SR 39.1% (61.9% fallback ms_gw)
   - 期望部署后: primary SR 提升 (同 key 重试救回部分间歇故障), fallback 率下降
3. 三阈值判稳 (同 post6):
   - cc2 SR (cc4101-primary 30min)
   - cc4101 真 fallback 数
   - 无新错误类型
4. 若 SR 提升且无新问题 → 写 rounds/R-keyretry-post1.md, commit, 更新 STATE
5. 若 SR 无变化 (NVCF 持续 429/超时, 重试也救不回) → 记数据, NOP, 不再调参
6. 铁律: 改前数据(本轮部署=用户指令, 数据=部署前 6h SR39.1%), 改后验证(本轮要拉数据),
   聚焦 40006, 只改 HM2, 写入仓库, 尽量多走 glm5_2_nv 少 fallback

### 回滚
- env: `NVU_CALLER_RETRY=0` (回退 max_attempts=1, 即刻生效, 不改代码)
- 源码: `cp upstream.py.bak.R-keyretry upstream.py && docker compose restart nv_gw`
- compose: `cp docker-compose.yml.bak.R-keyretry docker-compose.yml && docker compose up -d nv_gw`

### 关键认知
- 旧逻辑: NVCF key1 失败 → 立刻 fallback ms_gw (buffer 层重试时 execute_request 又走一遍 NVCF→ms_gw)
- 新逻辑: NVCF key1 失败 → sleep 2s → 重试 key1 → 失败 → sleep 4s → 重试 key1 → 失败 → sleep 8s → 重试 key1 → 3 次全败 → fallback ms_gw
- buffer 层 (BufferStreamSession) 不变: 仍 3 次 buffer 重试, 每次 execute_request 内部现在会做 NVCF 同 key 3 次重试
- 注意总耗时: NVCF 3 次重试 (含 2+4+8=14s 间隔 + 3 次 NVCF 超时 ~270s) 可能超 chain budget (NVU_TIER_BUDGET_GLM5_2_NV=230s), budget 内可能只够 1-2 次重试. 下轮看数据决定是否调 budget.

---

## R-buffer-post6 归档 (2026-07-27 08:55 CST, 供参考)

新 session 接棒 (STATE 停在 R-buffer-post5). 拉 30min + 6h 数据判三阈值, 冻结 NOP.
**本轮唯一实质产出 = 发现并修正 post5 STATE 里一个真实数据认知 bug**:

### 关键发现: post5 "content_s 480→580 铁证" 查询对 cc2 恒 0 行 (论据失效)

post5 STATE 写: "content_s (duration-ttfb) 按 6h 分桶: 480 段 29 个 (改前) / 580 段 15 个 (改后),
时间边界 CST 06:15 ≈ R-buffer-post3 落地, 铁证持续生效".

**本轮实测证伪**:
```
cc2 (cc4101-primary) 6h 200 样本: 383 行, has_ttfb=0   (ttfb_ms 全空!)
unknown (kimi_nv)     6h 200 样本: 367 行, has_ttfb=367 (全有)
```
→ **cc4101-passthrough 路径 (cc2 自己) 的 nv_gw 记 duration_ms 但不记 ttfb_ms**; 只有 `unknown`
caller 走 nv_gw-native 路径才记 ttfb_ms. 所以 post5 的 `duration_ms - ttfb_ms` 查询对 cc2 链路
**恒返回 0 行**, "29 个 480 / 15 个 580" 实际是 **unknown/kimi_nv 流量**, 不是 cc2 流量.
post5 铁证论据失效.

**但结论方向不变** (本轮用对的数据重证):
- cc4101 env `CC4101_STREAM_TOTAL_DEADLINE_S=580` ✓ 本轮实测持续生效 (post3 改 480→580 仍在).
- 真正的 cc2 链路 580 墙铁证应来自 **cc_requests.stream_total_deadline** (cc4101 侧记, passthrough
  适用): 6h 47× → 7.8/h (post5 报 7.1/h, 范围 4-9/h 波动一致, NVCF 长输出 >580s 残余接受项).

### 30min 数据 (08:16-08:46 CST = 00:16-00:46 UTC, 本轮实测)
- nv_gw 整体: 44×200 / 8×502 → SR=84.6%
- cc2 (cc4101-primary/glm5_2_nv): 27×200 / 0 失败 → **SR=100%** ✓
- unknown/kimi_nv: 17×200 / 8×502 (4 zombie + 3 ATE + 1 IncompleteRead, 别的 agent, 非 cc2)
- cc4101 真 fallback = 0 ✓
- buffer: 27×SUCCESS / 0 EXHAUSTED (全 1 attempt, verdict=success_tool_call/thinking_tool/thinking)

### 6h 数据
- cc2 nv_requests: 383×200 / 3×buffer_exhausted → SR=99.2% (3 个全 BUG-A 家族 client_gone_ping)
- cc_requests error_type: 512×空(成功) / 47×stream_total_deadline (7.8/h) / 8×client_gone_mid_stream
- stream_total_deadline 小时分布: 02h=4 / 03h=9 / 04h=8 / 05h=8 / 06h=4 / 07h=8 / 08h=6 (波动 4-9/h)

### 三阈值判稳
| 阈值 | 30min 实测 | 判定 |
|------|-----------|------|
| cc2 (cc4101-primary) SR | 27/27 = 100% | ✓ |
| cc4101 真 fallback | 0 | ✓ |
| 无新错误类型 | 仅 buffer_exhausted(BUG-A家族) + unknown/kimi_nv 502(别的agent) | ✓ |
→ 三阈值全满足 → **冻结 NOP, 0 改动 0 restart**

## 关键认知 (本轮修正 post5 铁证论据失效, 下轮起改查询)

1. **post5 的 content_s 铁证查询对 cc2 失效** (本轮发现): cc4101-passthrough 路径 nv_gw 不记
   ttfb_ms (cc2 386 行 has_ttfb=0), 只有 unknown/kimi_nv native 路径记. post5 "480→580 铁证"
   实际查的是 unknown/kimi_nv 流量, 非 cc2.
2. **580 墙铁证改用 cc_requests.stream_total_deadline** (cc4101 侧记, passthrough 适用):
   ```sql
   select date_trunc('hour', ts) as hr, count(*)
   from cc_requests
   where ts > now()-interval '6 hours' and error_type='stream_total_deadline'
   group by 1 order by 1;
   ```
   本轮 47×/6h=7.8/h, 范围 4-9/h 波动, 无骤升骤降 → 580 墙持续工作, NVCF 长输出残余接受.
3. **R-buffer-post3 (480→580) 仍持续生效**: cc4101 env 实测 580, 580 已顶 SDK 600s 墙留 20s 给
   flush, 不可再提. stream_total_deadline ~7-8/h 是 NVCF 长输出 >580s 的残余, 接受项非改码项.
4. **cc4101-passthrough 路径 vs nv_gw-native 路径**: cc2 走 passthrough (cc4101 转发, nv_gw 只
   buffer+forward 不解析流), 所以 nv_requests 不记 ttfb_ms 只记 duration_ms; unknown caller
   (kimi_nv 等) 走 native (nv_gw 自己解析流), 记 ttfb_ms. 下轮拉 cc2 content 数据只能用
   duration_ms, 不能用 duration-ttfb.

## nv_gw env 快照 (docker exec 实测, 无漂移, 同 post5)
```
UPSTREAM_TIMEOUT=90  TIER_TIMEOUT_BUDGET_S=180  TIER_COOLDOWN_S=180
KEY_COOLDOWN_S=60  MIN_OUTBOUND_INTERVAL_S=10  NV_INTEGRATE_KEY_COOLDOWN_S=90
NVU_FORCE_STREAM_UPGRADE=0  NVU_FORCE_STREAM_UPGRADE_TIMEOUT=150
NVU_TIER_BUDGET_GLM5_2_NV=120  NVU_TIER_BUDGET_DSV4P_NV=180
NVU_BIG_INPUT_FAIL_N=1  NVU_BIG_INPUT_THRESHOLD=250000  NVU_BIG_INPUT_COOLDOWN_S=180  NVU_BIG_INPUT_MODELS=glm5_2_nv
NVU_EMPTY_200_FASTBREAK=3  NVU_PEXEC_TIMEOUT_FASTBREAK=3  NVU_PEER_FB_SKIP_MODELS=glm5_2_nv,dsv4p_nv
NVU_BUFFER_CALLERS=cc4101-primary  NVU_BUFFER_MAX_RETRIES=3
NVU_BUFFER_TIMEOUT_STAIRS=150,200,200  NVU_BUFFER_PING_INTERVAL_S=30  NVU_BUFFER_TOTAL_DEADLINE_S=580
NVU_STREAM_FULL_BUFFER=0  KEY_AUTHFAIL_COOLDOWN_S=60
```
cc4101: `CC4101_STREAM_TOTAL_DEADLINE_S=580` ✓ (R-buffer-post3 改, 持续生效), `UPSTREAM_IDLE_TIMEOUT=150`
config.py MODEL_INPUT_TOKEN_SAFETY: kimi_nv=131072 / dsv4p_nv=131072 / glm5_2_nv=1048576(1M)
/health: nv_default_model=glm5_2_nv ✓ (cc4101 PRIMARY_UPSTREAM_MODEL / nv_gw / config.py 三处一致)

## 容器状态 (无漂移)
- nv_gw: Up, RC=0, restarts=0 (本轮无 restart)
- cc4101: `CC4101_STREAM_TOTAL_DEADLINE_S=580` ✓ 实测生效
- ms_gw: Up 5d (重启热备就位, 未碰)

## R2192 三任务进度 (无变化)
- 任务1 (cc4101 透传 cache_control): ✅ 落地持续生效 (cache_read 历史验证 38.8%)
- 任务2 (nv_gw zombie body dump probe): ✅ 终判完成 (R-buffer-post1: 440 dump, 55 stream_zombie
  全 cm/oc/th=ABSENT, 推测A证伪). 本轮无新 cc2 zombie, 不再累积.
- 任务3 (路径B zombie 内部 key 重试): ⚠ **被 R-buffer 部分取代, 暂搁置**. R-buffer buffer-then-flush
  + 同 key 重试已覆盖 cc2 Form B zombie 根治, 比 converter 内部重试更彻底. spec+骨架在
  ~/cc_ps/cc2_repair_self/specs/ 暂存, 除非未来出现 buffer 覆盖不到的 zombie 路径才重启.

## 下一轮该做什么
1. 继续巡检. 盯 cc2 (cc4101-primary) SR 是否保持 100%, buffer 是否 0 EXHAUSTED, cc4101 fb 是否 0.
2. **改用 cc_requests.stream_total_deadline** 查 580 墙铁证 (post5 的 content_s 桶对 cc2 失效).
3. 盯 stream_total_deadline 频次 (~7-8/h): 持续则接受为 NVCF 长输出残余 (580 已顶 SDK 600s 墙
   不可再提); 骤升则查 NVCF ttfb 退化或大 input 段集中.
4. 盯 client_gone (BUG-A 家族, buffer 重试无效是设计局限, 当前不治).
5. kimi_nv/unknown agent 的 502: 非 cc2 责任, 不动避免越权改别的 agent 路径.
6. 长驻机制: 每 30min touch ~/.claude/cc2.heartbeat (watchdog 15min); 每子任务刷 STATE;
   改 .py 触发 R-guard (py_compile+restart+health); auto-compact 后从 STATE 接棒.
7. 铁律: 改前数据, 改后验证, 聚焦 40006, 不碰 40007 (重启热备), 只改 HM2, 写入仓库, 尽量多走
   glm5_2_nv 少 fallback.

## 最近5轮摘要
- R-buffer-post6 (hm2_cc2, 本轮): NOP 巡检 + 修正 post5 数据认知 bug. cc2 链路 30min 27×200/0→
  SR100%, 6h 383×200/3×buffer_exhausted(SR99.2%, BUG-A家族). cc4101 fb=0. buffer 27×SUCCESS/0EXHAUSTED.
  nv_gw 整体 84.6%(8×502全unknown/kimi_nv别的agent). 核心发现: post5 STATE 的"content_s 480→580
  铁证"查询对 cc2 链路恒 0 行 (cc4101-passthrough 路径 nv_gw 不记 ttfb_ms, 实测 cc2 386 行
  has_ttfb=0 vs unknown 367 行全有), 实际查的是 unknown/kimi_nv 非 cc2 → 论据失效. 结论方向不变:
  cc4101 env 580 实测持续生效; 改用 cc_requests.stream_total_deadline(47×/6h=7.8/h)做 580 墙铁证.
  三阈值全满足→冻结. 0改动0restart.
- R-buffer-post5 (hm2_cc2): NOP 巡检. 580s 持续生效铁证 + 修正 post4 的伪 86% 降幅结论.
  cc2 链路 100% (30min 30/30), 6h 381/4(SR98.96%, 4 全 BUG-A 家族). 0 改动 0 restart.
  ⚠ 本轮发现 post5 的 content_s 铁证查询失效 (见上 post6).
- R-buffer-post4 (hm2_cc2): 验证 post3 (480→580) 真生效, content_s 墙杀 480→580. 报"86% 降幅"
  (后被 post5 修正为短窗口伪结论). SR97.3%(1×buffer_exhausted). 0改动0restart.
- R-buffer-post3 (hm2_cc2): cc4101 STREAM_TOTAL_DEADLINE 480→580 对齐 buffer 总预算. 改前6h 29×
  content_s=480 铁证 (480 墙杀误杀非真挂死). 留 SDK 600s 墙 20s 余量. env 单点回滚. 落地验证通过.
  ⚠ post6 发现该"29×content_s=480铁证"查的是 unknown/kimi_nv 非 cc2, 论据需以 cc_requests
  stream_total_deadline 替代, 但 480→580 改动本身仍持续生效.
- R-buffer-post2 (hm2_cc2): NOP 巡检. cc2 链路 100% (42/42), buffer 102×SUCCESS/6h. nv_gw 整体 87.2%
  根因=10×502全unknown/kimi_nv. 关键发现: 上周期 buffer_exhausted 3 次全败 client_gone_ping. 0改动0restart.

---
## 长驻 session 设计 (2026-07-24 落地)
- 旧 cc2-resume (1min oneshot) 已 stop+disable. 新 cc2-long (8h 长驻 session) 已就位.
- ~/.config/systemd/user/cc2-long.{timer,service}: 8h 周期换 session, Type=simple, Restart=on-failure
- ~/.config/systemd/user/cc2-longwatch.{timer,service}: 5min 检心跳, >15min 无更新 kill (触发 on-failure 重起)
- ~/cc_ps/cc2_repair_self/.claude/cc2_long_resume.sh: 启动器, -p 喂自循环 prompt, timeout 28800s 兜底
- 旧 cc2_resume.sh 备份 .bak.R2322
- agent 自循环铁律: 每子任务→Write STATE; 每30min→touch heartbeat; 改.py→py_compile+restart+health(R2192 R-guard内化); auto-compact 后从 STATE 接棒
- openclaw2: 保持 stop+disable 暂停, 不上长 session

---
## cc_s2 / cc_s3 备份锚点 (回滚锚点, 守护待用)
- **cc_s2** (commit `5ec9c7c`): 阶梯超时实验前的网关源码快照. gateway_backup/{nv-gw,cc4101,ms-gw}/ 43文件.
- **cc_s3** (commit `d7392cf`): per-agent 固定 key + 阶梯超时重试前的快照.
- 回滚方法: `git show cc_s2:gateway_backup/<svc>/<file> > /opt/cc-infra/proxy/<svc>/gateway/<file> && docker compose up -d <svc>`
- 注意: cc_s2/cc_s3 快照在 R-buffer 之前, 不含 buffer_stream.py/stream_success_judge.py.
  R-buffer 回滚用 `handlers.py.bak.R-buffer` + NVU_BUFFER_CALLERS="" (见 R_buffer_cc2_zombie_rootfix.md).
- cc4101 STREAM_TOTAL_DEADLINE 回滚: env 改回 480 (R-buffer-post3 单点).
- 守护状态: 只读验证通过, 未改任何 gateway/*.py, 未重启容器. 锚点由外部监督者建立, cc2 守护待用.
