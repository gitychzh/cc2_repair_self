# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: R851 (NOP 巡检轮 — 近窗 cc4101-primary SR=100% 57×200 零错误, 30-min 残留均风暴旧痕, 不改码, 2026-08-07 04:22 CST)
> 上轮: R850 (NOP — 近窗 34×200 零错误, 不改码)

## 本轮 (R851) 改动 + 依据 + 验证

### 改动: 无 (巡检轮 — 近窗全净, 修复链自适应吸收 30-min 旧痕)

### 本轮数据 (04:22 CST, 实时拉取, DB UTC 对齐)

**最近 15min cc4101-primary (cc2 自己路径) SR = 100% (57×200, 零错误).** nv_gw buffer 全走
dsv4f0731_nv, 每条 attempt=1/5 一次成功, 1-12s, success_tool_call/success_text, 零 buffer_exhausted
零 WAIT. 30min 窗口的 `buffer_exhausted×4`/`client_gone_pre_attempt×2`/glm5_2_nv 502×2
全为窗口早期 glm5_2_nv 风暴旧痕, 已被多 tier round-robin + fail-fast 自适应吸收.

| 指标 | 值 | 状态 |
|---|---|---|
| **最近 15min cc4101-primary SR** | **100% (57×200, 零错误)** | ✅ |
| **primary 目标 tier** | **dsv4f0731_nv** (自适应轮转持有) | ✅ |
| **buffer 日志 (近 20min)** | 每条 attempt=1/5 一次成功, 1-12s, success_tool_call/success_text | ✅ 零 buffer_exhausted |
| **fallback (ms_gw 层)** | 近窗 0 次 | ✅ |

### 30min 硬窗口残留 (缓解释义)

`buffer_exhausted×4 (avg 199s)`, `client_gone_pre_attempt×2`, glm5_2_nv 502×2 全为窗口早期
glm5_2_nv 风暴残留, 最近 20min 逐分钟全 200 (57/57), 与 R844-R850 同型.
glm5_2_nv 仍处退化, cc4101 自适应轮转 pinned dsv4f0731_nv — 修复链设计意图.

## 修复链 (沿用, R827+R828+R829+R833+R813)
1. glm5_2_nv 全 key 疲劳 → R829/R833 fail-fast + cc4101 动态 primary → dsv4f0731_nv
2. dsv4f0731_nv 1-12s 一次成功, 用户无感知
3. 多 tier round-robin (dsv4p/dsv4f/glm5_2_nv) 自适应吸收底层跨 key 瞬态失败

## 健康检查
- `curl localhost:4101/health` → ok ✅ (cc4101, primary=dsv4f0731_nv)
- `curl localhost:40006/health` → ok ✅ (nv_gw, passthrough, 5 keys, nvcf_pexec_models 含 dsv4p_nv/dsv4f_nv/dsv4f0731_nv/glm5_2_nv/kimi_nv)

## 参数快照 (无变化)

```
nv_gw: pexec_us_rr 单模式, KEY_FID_BIND 全 bind b1b22d03, BUFFER 5×90s=450s,
       WAIT max 120s, KeyManager 429→120-600s 指数退避, RemoteDisc→5s 短惩罚,
       TIER_COOLDOWN_S=180, NVU_DISABLE_MS_FALLBACK=0 (ms_gw fallback 已恢复),
       PEER_FALLBACK_ENABLED=0
cc4101: PRIMARY 动态轮转 (风暴时 glm5_2_nv→dsv4f0731_nv),
        FALLBACK=ms_gw:40007 (CC4101_STREAM_TOTAL_DEADLINE_S=470, PRIMARY_HEADER_TIMEOUT=400, UPSTREAM_TIMEOUT=130)
DB tz: UTC (STATE 时间为 CST = UTC+8)
```

## 下一步
- 长期观测。glm5_2_nv 冷却退去后观察 cc4101 primary 是否自动回归 glm5_2_nv (主链路目标)。
- 关注 glm5_2_nv 持续疲劳; 当前 dsv4f0731_nv 全量接管已吸收, 无需动。
- 不改码。修复链充分, 近窗全净。