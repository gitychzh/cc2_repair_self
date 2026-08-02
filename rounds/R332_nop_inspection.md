# R332 — NOP 巡检轮 (cc2 0req, dsv4p_nv SR=50% 5/10, 根因不变)

**日期**: 2026-08-02 ~19:00 CST
**方向**: R-nvonly (cc2 自优化 nv_gw)
**改动**: 0 | **重启**: 0 | **回滚**: 0

## 本轮数据 (30min 实时链路分析注入 ~18:57 CST)

### cc2 (cc4101-primary) 30min
- 0 req. session 间歇空闲, 链路空闲健康.
- 0 fallback, 0 stream_total_deadline.
- buffer/wait 日志 (BUFFER-/WAIT-) 30min 空.

### dsv4p_nv 30min 全 caller SR=50.0% (5/10)
| caller | model | status | count |
|---|---|---|---|
| hermes | dsv4p_nv | 200 | 5 |
| hermes | dsv4p_nv | 429 | 5 |

- per-key (dsv4p): key2 → 5×200 (avg_dur 9327); 空 key → 5×429 (avg_dur 1488, KEYMGR 阶段即拦).
- per-egress: 203.10.96.139 → 5×100% (key2 成功路径); 空 IP → 5×0 (429 路径无 egress).
- 分钟趋势: 10:30-10:50 一波 429×5 (每 5min 1 发, NVCF function 配额周期) → 10:55-10:56 恢复 5×200.
- fallback 0/10. finish_reason: tool_calls×5 (200 路径正常).
- 200 延迟: avg_dur 9327, max 14760, min 5388, avg_ttfb 9166 (dsv4p_nv 正常高延迟特性).

### 错误分类
- 5 错误: 5× all_tiers_exhausted (sub=all_tiers_failed_in_mapped_tier, avg_dur 1488).
- 本轮无 NVStream_IncompleteRead (R325 有 1, 历史偶发 mid-stream 软挂单发, 非新错误类型).
- 错误类型集合与 R268-R331 一致, 无新增.
- tier_attempts 30min 0 行 (429 在 NVCF 侧, 未进入 nv_gw tier 重试).
- buffer/wait 日志空.

### 健康检查 (沿用 R331, 本轮 0 改动 0 restart)
- /health 200: nv_num_keys=5, default glm5_2_nv, pexec_models=[kimi_nv, dsv4p_nv, glm5_2_nv].
- 容器全 Up: nv_gw 4h+, cc4101 5h+, nv_gw_stable 17h, ms_gw/logs_db 3d+.

## 根因 (沿用 R278-R331 分析, 本轮数据再次验证)
- dsv4p_nv 5key (k0-k4) 全绑同一 NVCF function. NVCF 429 配额是 function 级:
  function 配额耗尽时 5key 同时收 429 → all_tiers_exhausted.
- 本轮 10:30-10:50 一波 429×5 → 10:55-10:56 恢复 5×200, 证明是 NVCF function 配额周期自恢复,
  非 nv_gw 代码缺陷. KEYMGR 指数退避正常工作, 配额恢复后 ProbeWorker 探测唤醒.
- buffer 5key 轮转设计假设 "单 key 429 切下一 key 绕过", 对 function 级 429 是已知盲区
  (5key 全打同一 function → 同时 429). 这是设计盲区非代码缺陷.
- 非 nv_gw 代码缺陷, 无需本轮改码. NVCF function 级配额是上游硬限制.

## 判稳
- **NOP 巡检轮**. cc2 primary 0 req, 链路空闲健康, 0 fallback 0 deadline.
- dsv4p_nv 本轮 SR=50.0% (5/10): 窗口命中 1 波 429×5 后自恢复 5×200, 根因不变 (NVCF function 配额周期).
- 错误类型无新增, 与 R268-R331 一致.
- 六十五轮一致 R268-R332.

## 下一步
- 继续 NOP 巡检, 等 cc2 流量恢复后观察 dsv4p_nv SR.
- 关注是否出现新错误类型 (非 all_tiers_exhausted/NVStream_IncompleteRead) 或 key/IP 级故障, 再决定是否介入.

## 参数快照 (R332, 沿用主仓, 无改动)
- cc4101: FALLBACK_UPSTREAM_URL=http://ms_gw:40007/v1/chat/completions, CC4101_STREAM_TOTAL_DEADLINE_S=470, PRIMARY_HEADER_TIMEOUT=400, PRIMARY_UPSTREAM_MODEL=dsv4p_nv, UPSTREAM_TIMEOUT=130.
- nv_gw: NVU_DISABLE_MS_FALLBACK=0, UPSTREAM_TIMEOUT=90, TIER_TIMEOUT_BUDGET_S=180, TIER_COOLDOWN_S=180, KEY_COOLDOWN_S=30, NVU_BUFFER_MAX_RETRIES=5 (5×90s=450s), NVU_BUFFER_TOTAL_DEADLINE_S=450, NV_INTEGRATE_KEY_COOLDOWN_S=90, NVU_BUFFER_CALLERS=cc4101-primary,openclaw2.
- deadline 链: 90s/buffer-attempt × 5 = 450s buffer < 470s cc4101 < 500s SDK idle (API_TIMEOUT_MS=600000).
