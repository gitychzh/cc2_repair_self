# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: **R995 (NOP 巡检轮/不改码 — cc2 主链路连续第 103 轮 100% 干净; 主链专属错误 0 rows; fallback 0 次)**
> cc4101-primary (主 nv_gw:40006) 实时 30min = **121/121 = 100% SR, 0 bad** (live 复核);
> cc4101-primary 专属错误 = **0 rows** (121 request 全 200);
> 容器: nv_gw Up, cc4101 Up (health 全 200)
> 上轮: R994 (NOP, 主链 117/117=100%)

## 本轮 (R995) 改动 + 依据 + 验证

### 改动: 无 (NOP。cc2 主链路连续 103 轮 100% 干净, 主专属错误 0 rows; 本轮 window 内 nv_requests 无任何 bad)

### 依据 (live 复核 2026-08-07 + 注入轮前链路分析)

- 30min cc4101-primary (主 nv_gw:40006) = **121/121 全 200 = 100% SR, 0 bad** (live re-pull)。
- 主链专属错误 (caller=cc4101-primary, status!=200) = **0 rows** (error_type 分组为空)。
- 本轮 window 内 nv_requests 无任何非 200 请求 (比 R994 更干净, R994 有 2 条 hermes 越界 bad)。
- fallback (cc_requests 30min) = **0 次** (121 req 全未 fallback_triggered)。
- nv_tier_attempts: 5 key 全 pexec_success (21–27/key), 瞬态 RemoteDisconnected/Timeout
  被 multi-key round-robin 吸收, 无 all_tiers_exhausted。
- buffer 日志全 attempt=1 一次成功 (flush 1.2–4.2KB, elapsed 2–13s); 无 WAIT 停滞, 无多 attempt 泄漏。

### 本轮数据

| 指标 | 值 | 状态 |
|---|---|---|
| 主 nv_gw(40006) cc4101-primary | **121/121 = 100% SR, 0 bad** (live re-pull) | ✅ |
| 主链专属错误 (caller=cc4101-primary) | **0 rows** | ✅ |
| nv_requests 总 bad (非 200) | 0 条 (本轮 window 无任何非 200) | ✅ |
| 30min fallback (cc_requests) | 0 次 (121 req 全未 fb) | ✅ |
| buffer/wait | 全 attempt=1 一次成功, flush 1.2–4.2KB, 无 WAIT 停滞 | ✅ |
| nv_tier_attempts | 5 key 全成功, 瞬态错误被 RR 吸收, 无 all_tiers_exhausted | ✅ |
| 容器 | nv_gw Up 11h, cc4101 Up 11h, health 全 200 | ✅ |

### 验证
- 30min nv_requests cc4101-primary = 121/121 (0 bad)。
- 主链专属错误分组 = 空 (0 rows)。
- cc_requests fallback = 0 次 (121 req 全未 fallback_triggered)。
- nv_tier_attempts: 5 key 全 pexec_success, 无 key 全挂。
- buffer 日志: NV-BUFFER-START/VARDICT/SUCCESS 全 attempt=1, 无 BUFFER-ATTEMPT>1。
- health: 4101/40006 全 200; 容器 nv_gw/cc4101 皆 Up。

### 关键判断
cc2 主链路连续第 **103** 轮 (R893-R995) 100% SR 干净, 主链专属错误 0 rows。
本轮 window 内 nv_requests 无任何 bad (R994 的 2 条 hermes 越界 bad 本轮消失), fallback 0 次,
无新 cc2 主链错误类, 无持久 key 疲劳。buffer 全一次成功 + multi-key round-robin + func_health
完全吸收瞬态键错误。
**不改码**: ①主链 SR 100% + 专属错误 0 行, 无优化需求; ②本轮无 bad 请求, 更无根因可查;
③ multi-key round-robin + func_health + buffer 已达稳态, 无参数可调。

## 下一步
- 保持 NOP 观察, 主链 dsv4f0731_nv 为首代, 无需参数改动。
- 后续窗口继续确认 hermes 越界 bad (fid 52e1ddb6) 是否持续与主链隔离 (host 分离保持)。

## 容器健康
- nv_gw Up 11h, cc4101 Up 11h; /health 40006 + 4101 全 200。
- 配置快照: PRIMARY_UPSTREAM_MODEL=dsv4f0731_nv, nv_gw nv_default_model=glm5_2_nv,
  NVU_DISABLE_MS_FALLBACK=0, NVU_BUFFER_MAX_RETRIES=5, KeyManager 429 120s-600s 退避,
  NVU_BUFFER_CALLERS=cc4101-primary,openclaw2。ms_gw fallback 保持不禁用。

## 修复链 (沿用, R827+R828+R829+R833+R813 + R869+R876+R891)
1. glm5_2_nv 全 key 疲劳 → R829/R833 fail-fast + cc4101 动态 primary → dsv4f0731_nv
2. dsv4f0731_nv 一次成功 (主链已用健康模型), 用户无感知
3. 多 tier round-robin + func_health fid 健康选择自适应吸收底层跨 key/fid 瞬态失败
4. 坏 fid 52e1ddb6 (hermes 宿主) 与主链健康 fid 容器+候选池双层隔离