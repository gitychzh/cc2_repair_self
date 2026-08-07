# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: **R927 (NOP 巡检轮/不改码 — cc2 主链路连续第 36 轮 100% 干净; 坏请求 all_tiers_exhausted ×4 + zombie_empty_completion ×1 (502) 全属 hermes 线, caller 列实拉铁证, 非 cc2 范围; fallback 0 次)**
> cc4101-primary (主 nv_gw:40006) 实时 30min = **119/119 = 100% SR, 0 bad** (实拉);
> cc4101-primary 专属错误 30min = **0 rows** (119 request 全 200);
> 容器: nv_gw Up 7h, cc4101 Up 6h, dsv4p_nv40066 Up 2d
> 上轮: R926 (NOP, 主链 114/114=100%)

## 本轮 (R927) 改动 + 依据 + 验证

### 改动: 无 (NOP。cc2 主链路连续 36 轮 100% 干净, 主专属错误 0 行; bad 请求全属 hermes 非 cc2)

### 依据 (live DB 30min 实拉 ≈2026-08-07 CST)

- 30min cc4101-primary (主 nv_gw:40006) = **119/119 全 200, 0 bad (100% SR)**。
- 30min **cc4101-primary 专属错误 = 0 rows** (status != 200 AND caller='cc4101-primary' 全空)。
- 30min 所有 bad (502) = `caller=hermes` ×5: `all_tiers_exhausted ×4` + `zombie_empty_completion ×1`。
- **caller 列实拉铁证**: 5 bad 全 caller=hermes, 0 个属于 cc2 主链 (host-separated)。
- fallback (cc_requests 30min) = **0 次**。
- tier 层 NVCFPexecRemoteDisconnected ×17 + timeout ×4 + 504 ×3 全被多 tier round-robin 吸收, 未浮现为 cc2 primary bad。
- 容器 health: 4101/40006/40066 全 ok (200); nv_gw Up 7h, cc4101 Up 6h, dsv4p_nv40066 Up 2d。

### 本轮数据

| 指标 | 值 | 状态 |
|---|---|---|
| 主 nv_gw(40006) cc4101-primary | **119/119 = 100% SR, 0 bad** (实拉) | ✅ |
| 主链专属错误 (caller=cc4101-primary) | **0 rows** | ✅ |
| hermes 线 bad (502) | all_tiers_exhausted ×4 + zombie_empty_completion ×1 | ⚠️ 越界 |
| bad caller 归属 | 5 req 全 caller=hermes; cc2 primary 0 条 | ✅ 隔离 |
| fallback (cc_requests) | 0 次 | ✅ |
| scoped health | 4101/40006/40066 全 ok (200), nv_gw Up 7h | ✅ |

### 验证
- curl 4101/40006/40066 → 全 ok (200); nv_gw Up 7h, cc4101 Up 6h, dsv4p_nv40066 Up 2d。
- 30min nv_requests cc4101-primary 实拉 = 119/119 (0 bad); 专属错误 0 rows。
- 30min 所有 bad 分组 (caller 列铁证): 5 条全 hermes, cc2 主链 0 bad。
- cc_requests fallback = 0 次。

### 关键判断
cc2 主链路连续第 **36** 轮 (R892-R927) 100% SR 干净, 且 30min 主链专属错误实拉 0 rows。
bad 请求 100% 属 hermes (caller 列实拉铁证未进 cc2 主链), fallback 0 次, 无新错误类。
**不改码**: ①主链 SR 100% + 专属错误 0 行, 无优化需求; ②坏请求全属 hermes 越 cc2 范围;
③多 tier round-robin + func_health 健康选择已达稳态。

## 修复链 (沿用, R827+R828+R829+R833+R813 + R869+R876+R891)
1. glm5_2_nv 全 key 疲劳 → R829/R833 fail-fast + cc4101 动态 primary → dsv4f0731_nv
2. dsv4f0731_nv 一次成功 (主链已用健康 fid 281478d0), 用户无感知
3. 多 tier round-robin + func_health fid 健康选择自适应吸收底层跨 key/fid 瞬态失败
4. 坏 fid 52e1ddb6 (hermes 宿主) 与主链健康 fid 281478d0 容器+候选池双层隔离

## 健康检查
- `curl localhost:4101/health` → ok ✅ (cc4101, primary=dsv4f0731_nv)
- `curl localhost:40006/health` → ok ✅ (nv_gw, passthrough, 5 keys)
- `curl localhost:40066/health` → ok ✅ (dsv4p_nv40066)