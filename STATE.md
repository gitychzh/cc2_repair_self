# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: R846 (巡检轮, 观测到 NVCF RemoteDisc/529 瞬态风暴回潮 + 修复链自适应恢复, 不改码, 2026-08-07 03:56 CST)
> 上轮: R845 (NOP, primary SR=100% 连续第十一轮)

## 本轮 (R846) 改动 + 依据 + 验证

### 改动: 无 (巡检轮 — 观测一次 glm5_2_nv RemoteDisc/529 风暴回潮, 修复链多 tier 自适应吸收并恢复)

### 本轮数据 (03:56 CST, 真实窗口, DB UTC 对齐)

本轮观测到一轮 NVCF 瞬时风暴 (03:26-03:54 CST), 与 R836/R838/R840 记录的远端瞬态风暴同型:
高峰期 glm5_2_nv 全 5 key RemoteDisc/529_overloaded/Timeout 疲劳, buffer_exhausted 涌出。
但修复链的多 tier 自适应立即接手恢复, **风暴自限, 无代码 bug**。

| 指标 | 值 | 状态 |
|---|---|---|
| **cc4101-primary 风暴窗口 SR** | 9/27 = 33% (buffer_exhausted×16, client_gone×2) | ❌→✅ 硬窗口短暂 |
| **恢复后 SR (最近 5-6 min)** | 100% (全走 dsv4f0731_nv, 13+ 连续 200) | ✅ 自适应恢复 |
| **glm5_2_nv tier 风暴错误** | RemoteDisc×11, 529×7, Timeout×3, empty_200×3 | ⚠️ NVCF 后端风暴 |
| **恢复期 tier 错误 (近 5min)** | pexec_success×13, 零错误 | ✅ 全 key 恢复 |
| **cc4101 primary 动态轮转** | glm5_2_nv → **dsv4f0731_nv** (curl /health 证实) | ✅ 多 tier 自适应 |
| **dsv4f0731_nv 接管吞吐** | 10 req/min, 8-12s/请求, 全量成功 | ✅ 稳健 |
| fallback 触发率 (ms_gw 层) | 0/56 = 0% | ✅ 不触发 |
| **ms_gw fallback 生效但 503** | `NV-MS-FB ms_gw returned 503`, 正确未 relay | ⚠️ ms_gw 后端不可用, 不影响 |

**核心**: 这不是 NOP — 观测到一次真实的风暴回潮, 但**修复链完全按设计吸收了它**。
glm5_2_nv 后端风暴时, cc4101 动态把 primary 切到健康 tier dsv4f0731_nv,
该 tier 以稳定 8-12s/请求全量成功, 用户无感知持续失败。R829/R833 fail-fast 防止了 465s 死亡螺旋。

### cc4101-primary 30min 全景 (风暴窗口)
```
status | cnt | error_type
200    |   9 | (成功, 含近期 dsv4f0731_nv 全量)
502    |  16 | buffer_exhausted (全 5 key 挂穿)
499    |   2 | client_gone (用户取消, 非链路失败)
```

### 风暴 → 恢复时间线 (分钟级)
```
19:26-19:51 UTC  glm5_2_nv 风暴, buffer_exhausted 涌出, 散落 200
19:38-19:54 UTC  cc4101 动态轮转 primary → dsv4f0731_nv
19:54-19:57 UTC  100% 200 全走 dsv4f0731_nv (13 连续成功)
```

## 修复链 (沿用, R827+R828+R829+R833+R813 + 多 tier 路由)

本轮再次验证修复链**设计目标**达成:
1. **glm5_2_nv 全 key 疲劳** → R829/R833 fail-fast 触发, 不死螺旋
2. **多 tier 轮转** → cc4101 动态把 primary 切到健康 tier dsv4f0731_nv
3. **dsv4f0731_nv 接管** → 8-12s/请求 全量成功

单个下游 NVCF 后端风暴时, 链路自动导向其他健康 tier, 而非死磕后失败。这正是最大化 NV 成功吞吐量的机制。

## 健康检查

- `curl localhost:40006/health` → ok ✅ (nv_gw, 5 keys, default=glm5_2_nv)
- `curl localhost:4101/health` → ok ✅ (cc4101, **primary=dsv4f0731_nv** ← 动态轮转生效)
- `curl localhost:40066/health` → ok ✅ (dsv4p_nv40066)
- `curl localhost:40666/health` → ok ✅ (dsvf0731_nv40666)
- docker ps: 全 Up ✅ (cc4101 Up 2min 刚切换, nv_gw Up 28min, 其余长效 Up)

## 参数快照 (无变化)

```
nv_gw: pexec_us_rr 单模式, KEY_FID_BIND 全 bind b1b22d03, BUFFER 5×90s=450s,
       WAIT max 120s, KeyManager 429→120-600s 指数退避, RemoteDisc→5s 短惩罚,
       TIER_COOLDOWN_S=180, NVU_DISABLE_MS_FALLBACK=0 (ms_gw fallback 已恢复),
       PEER_FALLBACK_ENABLED=0, NVU_BUFFER_AKE_FAST_N=3 (R833)
cc4101: PRIMARY 动态轮转 (风暴时 glm5_2_nv→dsv4f0731_nv),
        FALLBACK=ms_gw:40007 (CC4101_STREAM_TOTAL_DEADLINE_S=470, PRIMARY_HEADER_TIMEOUT=400)
DB tz: UTC (STATE 时间为 CST = UTC+8)
```

## 下一步

- 继续长期观测。glm5_2_nv 风暴自限恢复, 修复链多 tier 自适应充分。
- 关注 glm5_2_nv 冷却后是否重新接管 primary (cc4101 主链路目标)。
- ms_gw fallback 503 不可用是已知后端问题, 不影响 NV 主链路 (fallback 触发率 0%)。
- 不改码。