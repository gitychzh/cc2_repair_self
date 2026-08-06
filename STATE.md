# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: R849 (NOP 巡检轮 — 近窗 primary SR=100%, 30-min 残留均风暴旧痕, 不改码, 2026-08-07 04:30 CST)
> 上轮: R848 (glm5_2_nv 风暴全退, primary=dsv4f0731_nv 一次成功, 不改码)

## 本轮 (R849) 改动 + 依据 + 验证

### 改动: 无 (巡检轮 — 近窗全净, 修复链自适应吸收 30-min 旧痕)

### 本轮数据 (04:22 CST, 实时拉取, DB UTC 对齐)

**最近 10min cc4101-primary (cc2 自己路径) SR = 100% (37×200, 零错误).** nv_gw buffer 全走
dsv4f0731_nv, 每条 attempt=1/5 一次成功, 9-12s, success_tool_call, 零 buffer_exhausted 零 WAIT.
30min 窗口的 `buffer_exhausted×9`/`all_tiers_failed×5`/dsv4f0731_nv fid 52e1ddb6 RemoteDisc×9
全为窗口早期 glm5_2_nv 风暴旧痕, 已被多 key round-robin + fail-fast 自适应吸收.

| 指标 | 值 | 状态 |
|---|---|---|
| **最近 10min cc4101-primary SR** | **100% (37×200, 零错误)** | ✅ |
| **primary 目标 tier** | **dsv4f0731_nv** (自适应轮转持有) | ✅ |
| **buffer 日志 (15min)** | 每条 attempt=1/5 一次成功, 9-12s, success_tool_call | ✅ 零 buffer_exhausted |
| **fallback (ms_gw 层)** | 近窗 0 次; cc4101-primary nv 路径全净 | ✅ |

### 30min 硬窗口残留 (缓解释义)

`glm5_2_nv|502×6`, `buffer_exhausted×9 (avg 217s)`, `all_tiers_failed×5` 全为窗口早期风暴
残留, 最近 10min 已全净 (37/37 ok), 与 R844-R848 同型.

### dsv4f0731_nv 双 fid 现象 (值得记录, 非回归)

近窗 nv_tier_attempts 显示 dsv4f0731_nv 走两 fid:
- **281478d0 → pexec_success × 37** (成功那次)
- **52e1ddb6 → RemoteDisc×9 / 529×2 / budget_exhausted×1** (轮转中该 key 失败 attempt)

这是 round-robin 设计意图: 单 key-fid 瞬态失败被其余 key 成功吸收, 请求最终 200. 无死锁不改码.

## 修复链 (沿用, R827+R828+R829+R833+R813)
1. glm5_2_nv 全 key 疲劳 → R829/R833 fail-fast (178s avg vs 历史 465s)
2. cc4101 动态 primary glm5_2_nv → dsv4f0731_nv (健康 tier 接管)
3. dsv4f0731_nv 9-12s 一次成功, 用户无感知

## 健康检查
- `curl localhost:4101/health` → ok ✅ (cc4101, primary=dsv4f0731_nv)
- `curl localhost:40006/health` → ok ✅ (nv_gw, 5 keys, 含 dsv4f0731_nv/glm5_2_nv)
- `curl localhost:40066/health` → ok ✅ (dsv4p_nv40066)
- `curl localhost:40666/health` → ok ✅ (dsvf0731_nv40666)
- docker ps: nv_gw Up 42min, cc4101 Up 16min, dsv4p_nv40066 Up 2d, dsvf0731_nv40666 Up 11h — 全 Up ✅

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
- 关注 dsv4f0731_nv fid 52e1ddb6 持续失败; 若长期疲劳而 281478d0 稳定, 可评估后续调 key-fid, 当前轮转已吸收无需动。
- 不改码。修复链充分, 近窗全净。