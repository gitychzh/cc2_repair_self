# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: **R921 (NOP 巡检轮/不改码 — cc2 主链路连续第 30 轮 100% 干净; 坏请求 all_tiers_exhausted ×5 (502) 全属 hermes 线, caller 列 + request_id 级 JOIN 双重铁证, 非 cc2 范围; fallback 0 次)**
> cc4101-primary (主 nv_gw:40006) 实时 30min = **119/119 = 100% SR, 0 bad** (实拉);
> live DB now()≈2026-08-07 09:55 CST
> 容器: nv_gw Up 6h, cc4101 Up 6h, dsv4p_nv40066 Up 2d
> 上轮: R920 (NOP, 主链 116/116=100%)

## 本轮 (R921) 改动 + 依据 + 验证

### 改动: 无 (NOP。cc2 主链路连续 30 轮 100% 干净, 无新错误类; bad 请求全属 hermes 非 cc2)

### 依据 (live DB 30min 实拉, ≈2026-08-07 09:55 CST)

- 30min cc4101-primary (主 nv_gw:40006) = **119/119 全 200, 0 bad (100% SR)**。
  实拉 caller 分组 → cc4101-primary total=119 ok=119 bad=0; `AND status!=200` → **0 条**。
- 30min 所有 bad (502) = `caller=hermes` ×5: `all_tiers_exhausted ×5`。
- **caller 列 + request_id 级 JOIN 双重铁证** (nv_requests ⋈ nv_tier_attempts): 5 bad 全 caller=hermes, 0 个属于 cc2 主链。
- 总 SR (全 caller×model): dsv4f0731_nv 121/126 = 96.0% (其中 bad 5 全属 hermes 线)。
- fallback (cc_requests 30min total=126) = **0 次**。
- per-key (nv_tier_attempts): pexec_success 稳定 (k0:24/k1:23/k2:25/k3:23/k4:24); 瞬态 NVCFPexecRemoteDisconnected(16)/NVCFPexecTimeout(2)/504(3) 分散 k0~k4, 被多 tier round-robin + func_health 健康选择吸收, 未达 cc2 全挂。
- buffer/wait/keymanager 日志: 空 (��大 retry/全挂, 一次成功)。
- 容器 health: 4101/40006/40066 全 ok (200); nv_gw Up 6h, cc4101 Up 6h, dsv4p_nv40066 Up 2d。

### 本轮数据

| 指标 | 值 | 状态 |
|---|---|---|
| 主 nv_gw(40006) cc4101-primary | **119/119 = 100% SR, 0 bad** (实拉) | ✅ |
| hermes 线 bad (502) | all_tiers_exhausted ×5 | ⚠️ 越界 |
| bad caller 归属 | 5 req 全 caller=hermes; cc2 primary 0 条 | ✅ 隔离 |
| 总 SR (全 caller) | dsv4f0731_nv 121/126 = 96.0%, bad 全 hermes | ✅ 主链 100% |
| fallback (cc_requests) | 0 次 (0/126) | ✅ |
| per-key tier | pexec_success 主导, 瞬态错误被吸收 | ✅ |
| scoped health | 4101/40006/40066 全 ok (200), nv_gw Up 6h | ✅ |

### 验证
- curl 4101/40006/40066 → 全 ok; cc4101 primary=dsv4f0731_nv; nv_gw passthrough 5 keys。
- 30min nv_requests cc4101-primary 实拉 = 119/119 (0 bad)。
- 30min 所有 bad 分组 (caller 列 + request_id JOIN 双铁证): 5 条全 hermes, cc2 主链 0 bad。
- cc_requests fallback = 0 次 (0/126)。

### 关键判断
cc2 主链路连续第 **30** 轮 (R892-R921) 100% SR 干净。bad 请求 100% 属 hermes,
caller 列 + request_id 级 JOIN 双重铁证未进 cc2 主链; fallback 0 次; 无新错误类。**不改码**:
①主链 SR 100% 无优化需求; ②坏请求全属 hermes 越 cc2 范围; ③多 tier round-robin + func_health 健康选择已达稳态。

## 修复链 (沿用, R827+R828+R829+R833+R813 + R869+R876+R891)
1. glm5_2_nv 全 key 疲劳 → R829/R833 fail-fast + cc4101 动态 primary → dsv4f0731_nv
2. dsv4f0731_nv 一次成功 (主链已用健康 fid 281478d0), 用户无感知
3. 多 tier round-robin + func_health fid 健康选择自适应吸收底层跨 key/fid 瞬态失败
4. 坏 fid 52e1ddb6 (hermes 宿主) 与主链健康 fid 281478d0 容器+候选池双层隔离

## 健康检查
- `curl localhost:4101/health` → ok ✅ (cc4101, primary=dsv4f0731_nv)
- `curl localhost:40006/health` → ok ✅ (nv_gw, passthrough, 5 keys)
- `curl localhost:40066/health` → ok ✅ (dsv4p_nv40066)