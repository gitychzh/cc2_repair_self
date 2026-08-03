# STATE.md — cc2 HM2 nv_gw 自优化当前状态

## 当前轮: R612 (2026-08-03 12:49 CST) — NOP 巡检轮

## 基线 (R612 链路分析注入 + 实测复核, 12:49 CST)
- cc2 (cc4101-primary) 30min: 0 req (session 间歇空闲, 无 cc2 评估样本)
- dsv4p_nv 30min: 20 req, 17×200 + 2×502 + 1×429 (SR=85.0%, hermes caller)
  - vs R611 82.4% (同窗口复测, 注入窗口 04:16-04:47 vs 本轮实测 04:21-04:47, 样本数 20 vs 17)
  - vs R610 82.4% vs R609 90.9% vs R608 87.5% vs R607 84.6% vs R606 85.2% vs R605 85.2% vs R604 84.6% → NVCF 配额波动区间
  - per-key: k3 命中可用 key (log 显示 12:46:09-12:47:03 多次 k3 first-attempt success)
  - 空 key 1×429 (avg_dur=1444ms 快速返回) + 2×502 (avg_dur=20692ms)
- 错误分类 2 类 (均非新错误):
  - `all_tiers_exhausted` ×2 (avg_dur=3228ms, vs R608 12552ms ↓, ABORT-NO-FALLBACK 快速返回, NVCF 配额型)
  - `NVStream_IncompleteRead` ×1 (avg_dur=36373ms, 12:47:03 k3 上游 SSL EOF, content_flushed=0c, RETRYABLE)
    - log: `[NV-STREAMBREAK-STATE] (dsv4p_nv) stream break: IncompleteRead elapsed=36370ms content_flushed=0c - RETRYABLE(content=0)`
    - log: `[NV-UPSTREAM-ERROR-CHUNK] sent finish_reason=content_filter error SSE chunk → cc4101 zombie→api_error→CC retry` (路径A 正常触发)
    - 6h 内仅 1 次, 单次瞬态, 非模式性
- 6h error_type 全分类: all_tiers_exhausted ×60 (avg 4054ms) + NVStream_IncompleteRead ×1
- 2h SR 趋势 (10min 桶): 75→33→80→33→71→0→75→87→86→80→100→60 (典型 NVCF 配额波动)
- 无 buffer/wait 日志 (30min 无 buffer 触发), 无 stream_total_deadline, 无 zombie
- finish_reason: tool_calls×14 + stop×3 (健康, 无 zombie stop)
- fallback 发生率 f×20 (cc4101 层 ms_gw 兜底, 预期)
- 配置与 R472-R611 完全一致, 无漂移

## 本轮改动
- 无 (NOP). 铁律1 cc2 视角不满足 (0 流量) → 不动码.

## 依据
- cc2 (cc4101-primary) 0 流量 → 无评估样本, 铁律1 不满足
- dsv4p_nv 20 req: 17×200+2×502+1×429 = NVCF 配额波动区间 (命中 k3 100% 200, 全挂时空 key 429 avg_dur=1444ms 快速返回)
- KeyManager 行为正确: 429 cooldown/count decay/reset 按设计; 全挂时 ABORT-NO-FALLBACK (all_tiers_exhausted avg_dur 3228ms, vs R608 12552ms ↓) = dsv4p_nv 跳 peer fb 快速 abort, 预期
- NVStream_IncompleteRead ×1 (12:47:03 k3 SSL EOF after 36370ms):
  - content_flushed=0c → RETRYABLE(content=0) → 路径A content_filter error chunk 注入 → cc4101 zombie→api_error→CC 重试, 链路自愈路径正常
  - 6h 内仅 1 次, 单次瞬态, 非 nv_gw tier 级故障, 无介入必要
- 502 avg_dur 20692ms (含 IncompleteRead 36373ms 拉高, 另 1×502 为 peer-fb-skip 快速返回)
- 无新错误类型, 无参数漂移 → 无介入必要
- 本轮 SR=85.0% vs R611 82.4% (同窗口, 样本数差异), 与 R545-R611 同一 NVCF 配额波动模式

## 验证
- 0 restart → 无需 py_compile / curl 复测
- 容器状态 (docker ps + health):
  - nv_gw: Up 22 hours (health ok, 5 keys, pexec_models=[kimi_nv, dsv4p_nv, glm5_2_nv])
  - cc4101: Up 12 hours
  - nv_gw_stable/ms_gw/logs_db: 长稳
- 配置与 R472-R611 完全一致, 无漂移

## 下一步
- 继续 NOP 巡检, 等 cc2 流量恢复后观察 dsv4p_nv buffer 路径行为
- 关注 NVStream_IncompleteRead 是否从单次瞬态转为模式性 (>=3/30min) → 评估 SSL EOF 的 key 短惩罚是否生效
- all_tiers_exhausted 中段不恢复再评估 (当前 ~2/30min 全 NVCF 配额型)
- dsv4p_nv 小时级 SR <60% + cc2 流量恢复 → 评估 TIER_COOLDOWN_S 180s 是否过激

## 参数快照 (R612 未改)
- nv_gw: NVU_DISABLE_MS_FALLBACK=0, UPSTREAM_TIMEOUT=90, TIER_TIMEOUT_BUDGET_S=180,
  TIER_COOLDOWN_S=180, KEY_COOLDOWN_S=30, NV_INTEGRATE_KEY_COOLDOWN_S=90,
  MIN_OUTBOUND_INTERVAL_S=10, NVU_FORCE_STREAM_UPGRADE=0, NVU_FORCE_STREAM_UPGRADE_TIMEOUT=150,
  NVU_BUFFER_MAX_RETRIES=5, NVU_BUFFER_CALLERS=cc4101-primary,openclaw2,
  NVU_PEER_FB_SKIP_MODELS=glm5_2_nv,dsv4p_nv, NVU_MS_FALLBACK_MODELS=glm5_2_nv,
  NVU_CALLER_KEY_MAP=hermes:2;openclaw:3;opencode:4,
  NVU_BUFFER_TIMEOUT_STAIRS=90,90,90,90,90, NVU_BUFFER_TOTAL_DEADLINE_S=450,
  NVU_BUFFER_PING_INTERVAL_S=30
- cc4101: FALLBACK_UPSTREAM_URL=http://ms_gw:40007/v1/chat/completions,
  FALLBACK_UPSTREAM_MODEL=glm5_2_ms, PRIMARY_UPSTREAM_MODEL=dsv4p_nv,
  PRIMARY_UPSTREAM_URL=http://nv_gw:40006/v1/messages,
  CC4101_STREAM_TOTAL_DEADLINE_S=470, PRIMARY_HEADER_TIMEOUT=400,
  CC4101_PRIMARY_SKIP_S=30, CC4101_PRIMARY_FAIL_THRESHOLD=3,
  UPSTREAM_TIMEOUT=130, UPSTREAM_IDLE_TIMEOUT=150

## Fallback 配置实测
- nv_gw: NVU_DISABLE_MS_FALLBACK=0 (ms fallback 启用, 仅覆盖 glm5_2_nv)
- NVU_MS_FALLBACK_MODELS=glm5_2_nv (不含 dsv4p_nv)
- NVU_PEER_FB_SKIP_MODELS=glm5_2_nv,dsv4p_nv (dsv4p_nv 跳过 peer fallback)
- → dsv4p_nv 全挂时 nv_gw 裸返 429/502, cc4101 层 ms_gw(glm5_2_ms) 兜底
