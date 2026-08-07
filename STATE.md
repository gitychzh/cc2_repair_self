# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: **R991 (NOP 巡检轮/不改码 — cc2 主链路连续第 99 轮 100% 干净; 唯一坏 5: all_tiers_exhausted ×4 + zombie_empty_completion ×1 全属 hermes, 越界非 cc2 范围; fallback 0 次)**
> cc4101-primary (主 nv_gw:40006) 实时 30min = **125/125 = 100% SR, 0 bad** (live 复核);
> cc4101-primary 专属错误 = **0 rows** (125 request 全 200);
> 容器: nv_gw Up, cc4101 Up (health 全 200)
> 上轮: R990 (NOP, 主链 127/127=100%)

## 本轮 (R991) 改动 + 依据 + 验证

### 改动: 无 (NOP。cc2 主链路连续 99 轮 100% 干净, 主专属错误 0 行; 唯一 bad 全属 hermes+已知坏 fid 52e1ddb6 线)

### 依据 (live 复核 2026-08-07 + 注入轮前链路分析)

- 30min cc4101-primary (主 nv_gw:40006) = **125/125 全 200 = 100% SR, 0 bad** (live re-pull)。
- 总 nv_requests bad (非 200) = **5 条, 全 caller=hermes 线** (live 复核):
  all_tiers_exhausted ×4 + zombie_empty_completion ×1, 已知坏 fid 52e1ddb6 hermes
  宿主越界容器, non cc2 主链。
- fallback (cc_requests 30min) = **0 次** (live total 125 req, fb=0)。
- nv_tier_attempts 30min: pexec_success 主导 (125) + 瞬态
  (NVCFPexecRemoteDisconnected×16 / Timeout×3 / empty_200×3) 散落, 全被多 key round-robin +
  func_health + buffer 吸收, 无泄漏为 200 以外。
- buffer 日志 (nv_gw live): 所有 cc2 primary 请求 attempt=1 一次成功 (elapsed 9-16s,
  verdict=success_text/success_tool_call), **无 502 泄漏给 CC**。

### 本轮数据

| 指标 | 值 | 状态 |
|---|---|---|
| 主 nv_gw(40006) cc4101-primary | **125/125 = 100% SR, 0 bad** (live re-pull) | ✅ |
| 主链专属错误 (caller=cc4101-primary) | **0 rows** | ✅ |
| 唯一 bad (非 200) | 5 条, 全 caller=hermes 线 (all_tiers×4 + zombie×1) | ⚠️ 越界 |
| bad caller 归属 | 100% hermes 线; cc2 primary 0 条 | ✅ 隔离 |
| fallback (cc_requests) | 0 次 (125 req 全未 fb) | ✅ |
| tier 瞬态错误 | RemoteDisconnected(16)/Timeout(3)/empty_200(3), 全被吸收 | ✅ |
| 容器 | nv_gw Up, cc4101 Up, health 全 200 | ✅ |

### 验证
- 30min nv_requests cc4101-primary = 125/125 (0 bad)。
- bad 分组 (by caller×err_type): hermes 线 all_tiers_exhausted ×4 + zombie_empty_completion ×1 (fid 52e1ddb6) —
  全 hermes, cc2 主链 0 bad。
- cc_requests fallback = 0 次 (125 req 全未 fallback_triggered)。
- health: 4101/40006 全 200; 容器 nv_gw/cc4101 皆 Up。
- buffer: cc2 侧全 attempt=1 一次成功, 无泄漏 502。

### 关键判断
cc2 主链路连续第 **99** 轮 (R893-R991) 100% SR 干净, 且主链专属错误 0 rows。
唯一 5 个 bad 请求 100% 属 hermes 线 (caller=hermes + 已知坏 fid 52e1ddb6, all_tiers ×4 +
zombie ×1), fallback 0 次, 无新 cc2 主链错误类, 无持久 key 疲劳。
buffer 全一次成功, 多 key round-robin (dsv4f0731_nv 为首) + func_health 完全吸收瞬态键错误。
**不改码**: ①主链 SR 100% + 专属错误 0 行, 无优化需求; ②唯一 bad 全属 hermes 越 cc2 范围;
③多 key round-robin + func_health + buffer 已达稳态, 瞬态错误全被吸收, 无参数可调。

## 下一步
- 保持 NOP 观察, 主链 dsv4f0731_nv 为首代, 无需参数改动。
- 继续监控 hermes bad (fid 52e1ddb6) 是否真正与主链容器隔离 (host 分离); R897 起持续隔离保持。

## 容器健康
- nv_gw Up, cc4101 Up; /health 40006 + 4101 全 200。
- 配置快照: PRIMARY_UPSTREAM_MODEL=dsv4f0731_nv, nv_gw nv_default_model=glm5_2_nv,
  NVU_DISABLE_MS_FALLBACK=0, NVU_BUFFER_MAX_RETRIES=5, KeyManager 429 120s-600s 退避,
  NVU_BUFFER_CALLERS=cc4101-primary,openclaw2。ms_gw fallback 保持不禁用。

## 修复链 (沿用, R827+R828+R829+R833+R813 + R869+R876+R891)
1. glm5_2_nv 全 key 疲劳 → R829/R833 fail-fast + cc4101 动态 primary → dsv4f0731_nv
2. dsv4f0731_nv 一次成功 (主链已用健康模型), 用户无感知
3. 多 tier round-robin + func_health fid 健康选择自适应吸收底层跨 key/fid 瞬态失败
4. 坏 fid 52e1ddb6 (hermes 宿主) 与主链健康 fid 容器+候选池双层隔离