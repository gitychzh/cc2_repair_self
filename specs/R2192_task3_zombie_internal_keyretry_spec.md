# R2192 任务3 实施 Spec: nv_gw 内部 zombie 换 key 重试 (撤40007 路径核心步)

> 目标 (用户原话): "在 nv_gw 内部对 zombie 换 key 重试 (命中 zombie 不立刻注 content_filter 下沉, 而是换下一个 NV key 重打一轮, 全 key 都 zombie 才下沉 ms_gw), 这样 openclaw/opclaw4103 无感, 40007 调用直接下降. 最终目的是撤掉40007也能稳定运行."
> 本 spec 由 CC 基础设施侧 (本会话) 调研写就, 骨架见同目录 `task3_skeleton_passthrough.py` 与 `task3_skeleton_to_anth.py`. cc2 执行时 cat 这两个文件, 审查后落盘到 /opt/cc-infra, 验证, commit.
> 改动范围: HM2 only. nv_gw (proxy/nv-gw/gateway/handlers.py + upstream.py + config.py). 两路径都改.

## 0. 调研修正记录 (我第一版 spec 纠正过头, 这是最终版)

我 (CC 本会话) 第一版 spec 错判 "to_anth 主循环 zombie 不能重试 (双 message_start)". 核证 converter 源码后**纠正**: converter 有 `message_start_sent` 守卫 (oai_to_anth.py:116), 换 key 重放新流**不会**重发 message_start. cc2 CLAUDE.md 任务3 原设计是对的. 但 converter 还有 `next_block_idx` 递增计数器 + `active_block_type` 无守卫 — 故**必须限制只在 content_chars==0 且 reasoning_chars==0 的 zombie 重试** (此时 converter 状态干净: 可能 message_start_sent=True 但没开任何 content_block, next_block_idx=0, active_block_type=None; 换 key 新流首块 content → content_block_start(0) 合法).

## 1. 安全可重试的精确范围 (实测数据支撑)

**只对 content_chars==0 且 reasoning_chars==0 的 zombie 做内部换 key 重试.**

近24h实测分布:
- to_anth 路径 (cc2 自己): 14 次 content=0c reasoning=0c (干净, 可重试), 其余有 reasoning/content 不安全. → **14/约24 = 58% 可重试覆盖**.
- passthrough 路径 (hermes/openclaw): content_chars=0 的几乎都带大量 reasoning (5048/4811/3679/3356, glm5.2 thinking 答案写进思考) → reasoning_chars>0 → **不可重试** (已发 thinking block, 换 key 重放会重复 thinking + active_block_type=thinking 会 drop 新流 reasoning). 纯 content=0 reasoning=0 的 passthrough zombie 几乎没有 (数据仅见 content_chars 12-49 的).

**结论**:
- to_anth 路径: 主循环 zombie 命中, 若 content==0 且 reasoning==0 → 可重试 (覆盖 58%).
- passthrough 路径: 几乎无可重试 zombie (content=0 的都带 reasoning). 但仍加守卫逻辑 — 万一出现 content=0 reasoning=0 的也兜住. 主要受益方是 to_anth (cc2 自己), 但 task3 本意是给 hermes/openclaw 减 fallback — 需预期: passthrough 路径 fallback 不会显著降 (数据没素材), 真正降的是 to_anth 路径 (cc2 自身) 的 fallback. 这与"撤40007 让 openclaw 稳"有偏差 — 见第7节风险.

## 2. converter 状态安全条件 (to_anth 路径, 必须全满足才重试)

重试前 converter 必须满足 (全满足才安全):
1. `message_start_sent` 可为 True (守卫防重发, 见上) — OK
2. `content_chars == 0` (没发过任何 content_block_start text) — 守卫
3. `reasoning_chars == 0` (没发过任何 content_block_start thinking) — 守卫 (R852b 注释: thinking 答案写进思考是 zombie, 但这种 reasoning>0 不能重试)
4. `saw_tool_calls == False` (没发过 tool_use block) — 守卫
5. `next_block_idx == 0` (没开过 block) — 由 2/3/4 保证

满足 1-5 → converter 状态等同 "只发了 message_start", 换 key 重放新流从 content_block_start(0) 开始, 合法.

## 3. to_anth 骨架 (handlers.py `_stream_openai_to_anth` L1509 zombie 命中块)

当前 (L1509-1527): zombie 命中 → set zombie_detected → 走 finish(zombie=True) graceful end → 下沉.
改造: zombie 命中 → 先判 converter 状态是否干净 (第2节) + 换 key 次数剩余 → 干净则换 key 重放新 resp, 续 feed 同一 converter (不重置 converter!), 全 key 耗尽才 finish(zombie=True) 下沉.

关键: **不重置 converter** (保留 message_start_sent=True, 让新流不重发). 只关旧 conn + 调 `_zombie_retry_next_key` (新增, 镜像 `_peek_retry_next_key`) 拿新 resp + swap resp/conn + 重置流式循环的 deadline/poll_sock/sse_buffer. 详见 `task3_skeleton_to_anth.py`.

## 4. passthrough 骨架 (handlers.py `_stream_openai_passthrough` L2057)

passthrough 无 converter, openai 透传. content==0 且 reasoning==0 的 zombie: 下游只收到 SSE 头/空 delta, 换 key 重放新流首块真 content 直接续上, 无重复. 逻辑同 to_anth 但更简单 (无 converter 状态约束, 只看 content_chars==0 && reasoning_chars==0). 详见 `task3_skeleton_passthrough.py`.

## 5. 新增 upstream.py 函数 (镜像 _peek_retry_next_key, L492 附近)

```
def _zombie_retry_next_key(oai_body, tier_model, request_id, metrics, t_start,
                           is_stream, prior_cycle_attempts, start_key_idx,
                           upstream_timeout_override=None):
    """R2192 task3: 主循环 zombie 命中后内部换 ONE 个 NVCF key 整流重放 (不 advance RR).
    镜像 _peek_retry_next_key. 传 start_key_idx_override 给 _try_tier_keys."""
    return _try_tier_keys(oai_body, tier_model, request_id, metrics, t_start,
                         is_stream, prior_cycle_attempts,
                         upstream_timeout_override=upstream_timeout_override,
                         start_key_idx_override=start_key_idx,
                         max_attempts_override=1)
```

## 6. 新增 knob (config.py, env 可调)

- `NVU_ZOMBIE_KEYRETRY_KEYS` = int(env('NVU_ZOMBIE_KEYRETRY_KEYS','2')) — 换 key 次数, 默认 2. 0=关闭(回滚).
- `NVU_ZOMBIE_KEYRETRY_BUDGET_S` = float(env('NVU_ZOMBIE_KEYRETRY_BUDGET_S','0')) — 总 budget, 0=单次 upstream_timeout.

## 7. 风险与预期 (必读)

- **预期偏差**: task3 原意"给 hermes/openclaw 减 fallback", 但实测 passthrough 路径几乎无可重试 zombie (content=0 的都带 reasoning). 真正受益的是 to_anth (cc2 自身) 的 58% 干净 zombie. 若目标是降 openclaw fallback, 可能效果不达预期 — 需 shadow 后用数据确认.
- **重试有 budget 成本**: 每次 zombie 重试 = 一次新 pexec 请求 (~1-5s + TTFB). 2 次重试最多加 ~10s. 需确认不超 TIER_TIMEOUT_BUDGET_S. knob `NVU_ZOMBIE_KEYRETRY_BUDGET_S` 兜底.
- **content重复风险 (低)**: content==0 才重试, 守卫严格. 但 reasoning 模式 (glm5.2 thinking) zombie 的 reasoning>0 不重试 → 这类仍走 content_filter 下沉, 是正确取舍.
- **不碰 R2252 peek-retry**: peek 阶段 (send_response 前) 的软挂重试已由 R2252 处理, task3 只补主循环 zombie 命中点 (send_response 后).

## 8. 验证清单 (cc2 执行后必跑)

1. 语法: `docker exec nv_gw python -c "import gateway.handlers; import gateway.upstream"`.
2. 备份: `cp handlers.py handlers.py.bak.RNN_task3; cp upstream.py upstream.py.bak.RNN_task3; cp config.py config.py.bak.RNN_task3`.
3. restart: `cd /opt/cc-infra && docker compose restart nv_gw` (改 .py 必须 restart 非 up -d).
4. health: `curl -s http://localhost:40006/health`.
5. 三看 (R1695): docker inspect StartedAt 变 + 日志 Listening + 新标记 `NV-ZOMBIE-KEYRETRY-*` 出现.
6. shadow 2-6h: 观察 `NV-ZOMBIE-KEYRETRY-RESCUE` 计数 > 0 且这些请求 status=200 (非 502) + cc4101 fallback 计数下降 (对比基线).
7. 无退化: 成功请求 SR 不降, 无新错误类型, 无双 message_start 解析失败 (查 cc2 jsonl 无 "tool call could not be parsed").
8. 回滚: `NVU_ZOMBIE_KEYRETRY_KEYS=0` + restart, 或 .bak 恢复.

## 9. 铁律约束

- HM2 only. 不碰 ms_gw 源码. 不碰 HM1. 不碰 format/ 包 (converter 不改, 只复用守卫). 不碰 agent 模型选择.
- 改前必有数据 (第1节实测分布是素材). 改后必有验证 (第8节). 写入仓库 (rounds/R<N>_*.md + commit).
- 骨架是参考实现, cc2 落盘时必须按当前行号重新定位 (骨架行号基于 2026-07-23 快照, 落盘前 `grep -n` 核实).
