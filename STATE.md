# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: R829 (全 key cooling fail-fast 部署, 2026-08-05 ~19:30 CST)
> 上轮: R828 (nv_breaker 5consec→ms_gw fallback)

## 本轮 (R829) 改动 + 依据 + 验证

### 改动: buffer_stream.py 全 key cooling fail-fast

**问题**: R828 后 6h 数据显示 14 个 buffer_exhausted 平均 465s, 浪费 108min。
**根因**: buffer 固定跑 5 次 attempt + WaitQueue 180s, 即使全 key 都在 cooling 也继续无谓重试。
**修复**: 
1. for 循环中 `_execute_and_drain` 返回后检查 `_KeyManager.is_available()` 全 key → 全 cooling → break
2. WaitQueue 前检查全 key 长冷却 (>30s) → 跳过 WaitQueue, 直接 ms_gw fallback

### 优化方向变更

**旧目标**: SR 90%+, fallback < 10%, 用户可见 SR 99%+
**新目标**: **最大化单位时间 NV 成功请求数** (NV-only, ms fallback 不计入成功)
  - 每小时 NV 成功请求数 (越高越好)
  - 失败请求时间消耗比 (< 20%)
  - 失败请求平均耗时 (< 120s, R829 后预期 < 30s)
  - ms_fallback 触发率 (< 5%)
  - per-call SR (参考, 非首要目标)

### 验证

- [x] syntax OK (py_compile)
- [x] docker compose restart nv_gw → OK
- [x] curl /health → ok, 5 keys
- [x] Python introspection: ALL-COOLING=True, SKIP-WAIT=True, _KeyManager=True
- [x] E2E: curl cc4101 /v1/messages → 200 OK in 4.7s (不回归)
- [ ] 下一窗口日志确认 NV-BUFFER-ALL-COOLING 或 NV-BUFFER-SKIP-WAIT 触发 (待观察)

## 指标对比

| 指标 | R829 目标 | R828 实测 | 状态 |
|---|---|---|---|
| NV 成功请求数/h | 越高越好 | ~20-30/h | 待验证 |
| 失败请求 avg 耗时 | < 30s | 465s | 待验证 |
| 失败请求时间消耗比 | < 20% | > 50% | 待验证 |
| ms_fallback 触发率 | < 5% | ~1.3% | ✅ |
| per-call SR | 90%+ (参考) | 92.2% | ✅ |

## 健康检查

- `curl localhost:40006/health` → ok, 5 keys, pexec models 含 glm5_2_nv
- `curl localhost:4101/health` → ok, primary=glm5_2_nv
- docker ps: nv_gw Up, cc4101 Up, dsv4p_nv40066 Up

## 参数快照

无新增参数。R828 的 breaker + R829 的 fail-fast 使用 KeyManager 现有 API。
全 cooling 判定: `KeyManager.is_available(model, k)` 全 false → break
WaitQueue 跳过: `KeyManager.get_state(model, k)["cooldown_remaining_s"]` 全 > 30s → skip

## 下一步

- 观察 R829 在下次 NVCF 风暴时的表现
- 确认 NV-BUFFER-ALL-COOLING / NV-BUFFER-SKIP-WAIT 日志出现
- 确认失败请求 avg 耗时降到 < 30s
- 若效果好, 继续关注: 能否进一步缩短成功请求的 avg 耗时 (当前 45s)
