# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: **R979 (NOP 巡检轮/不改码 — cc2 主链路连续第 87 轮 100% 干净; 坏请求 2: 502 all_tiers_exhausted ×1 + 502 stream_absolute_cap ×1 全属 hermes, 越界非 cc2 范围; fallback 0 次)**
> cc4101-primary (主 nv_gw:40006) 实时 30min = **111/111 = 100% SR, 0 bad** (live 复核);
> cc4101-primary 专属错误 = **0 rows** (111 request 全 200);
> 容器: nv_gw Up (10h), cc4101 Up (10h)
> 上轮: R978 (NOP, 主链 105/105=100%)

## 本轮 (R979) 改动 + 依据 + 验证

### 改动: 无 (NOP。cc2 主链路连续 87 轮 100% 干净, 主专属错误 0 行; bad 请求全属 hermes+已知坏 fid 非 cc2)

### 依据 (注入轮前链路分析 ≈2026-08-07 13:41 CST + live 复核 bad 归属/fallback)

- 30min cc4101-primary (主 nv_gw:40006) = **111/111 全 200 = 100% SR, 0 bad** (live re-pull;
  注入 104, 窗口漂移+增长)。
- 总 nv_requests bad (非 200) = **2 条, 均 `caller=hermes`** (live 复核): 502 all_tiers_exhausted ×1
  + 502 stream_absolute_cap ×1, 已知坏 fid 52e1ddb6 hermes 宿主越界容器, non cc2 主链。
- fallback (cc_requests 30min) = **0 次** (live total 1890 req, fb=0)。
- nv_tier_attempts 30min (per-key): pexec_success 19~24 (k0-k4) + NVCFPexecRemoteDisconnected
  散落 k0-k4 (2~5) + empty_200 k3×1 — 全瞬态被多 key round-robin + func_health + buffer 吸收,
  全部 resolve 为 200。
- buffer 日志 (nv_gw): 本窗口无 buffer/wait/keymanager 噪声 — 设计稳态。

### 本轮数据

| 指标 | 值 | 状态 |
|---|---|---|
| 主 nv_gw(40006) cc4101-primary | **111/111 = 100% SR, 0 bad** (live re-pull) | ✅ |
| 主链专属错误 (caller=cc4101-primary) | **0 rows** | ✅ |
| 唯一 bad (非 200) | 502 all_tiers_exhausted ×1 + 502 stream_absolute_cap ×1 (均 caller=hermes, 已知坏 fid 52e1ddb6) | ⚠️ 越界 |
| bad caller 归属 | 全 caller=hermes; cc2 primary 0 条 | ✅ 隔离 |
| fallback (cc_requests) | 0 次 (1890 req live 全未 fb) | ✅ |
| tier 瞬态错误 | RemoteDisconnected 2~5/key (k0-k4) / empty_200 1, 全被吸收 | ✅ |
| 全局 nv_requests SR | 116/118 = 98.3% (dsv4f0731_nv) | ✅ |

### 验证
- 30min nv_requests cc4101-primary = 111/111 (0 bad)。
- bad 分组 (caller 归属): 502 all_tiers_exhausted ×1 + 502 stream_absolute_cap ×1
  均 caller=hermes, cc2 主链 0 bad。
- cc_requests fallback = 0 次 (live 窗口 1890 req 全未 fallback_triggered)。
- docker logs nv_gw buffer 段: 本窗口无 retry/WAIT-/KEYMGR- 错误噪声。
- health: 4101/40006 全 200; 容器 nv_gw/cc4101 皆 Up (10h)。

### 关键判断
cc2 主链路连续第 **87** 轮 (R893-R979) 100% SR 干净, 且主链专属错误 0 rows。
2 个 bad 请求 100% 属 hermes (caller=hermes + 已知坏 fid 52e1ddb6, 502 all_tiers_exhausted ×1 +
stream_absolute_cap ×1), fallback 0 次, 无新 cc2 主链错误类, 无持久 key 疲劳。
buffer 无 retry/WAIT-/KEYMGR- 噪声属设计稳态 — 多 key round-robin + func_health 完全吸收瞬态键错误。
**不改码**: ①主链 SR 100% + 专属错误 0 行, 无优化需求; ②坏请求全属 hermes 越 cc2 范围;
③多 key round-robin (dsv4f0731_nv 为首) + func_health + buffer 已达稳态, 瞬态错误全被吸收。

## 下一步
- 保持 NOP 观察, 主链 dsv4f0731_nv 为首代, 无需参数改动。
- 继续监控 hermes bad (fid 52e1ddb6) 是否真正与主链容器隔离 (host 分离); R897 起持续隔离保持。

## 容器健康
- nv_gw Up (10h), cc4101 Up (10h); /health 40006 + 4101 全 200。
- 配置快照: NV_GLM52_MODE_CHAIN=pexec_us_rr, KEY_FID_BIND 全 bind fid b1b22d03,
  NVU_DISABLE_MS_FALLBACK=0, NVU_BUFFER_MAX_RETRIES=5, KeyManager 429 120s-600s 退避。
- 容器启动 10h/10h 稳定, ms_gw fallback 保持不禁用。

## 修复链 (沿用, R827+R828+R829+R833+R813 + R869+R876+R891)
1. glm5_2_nv 全 key 疲劳 → R829/R833 fail-fast + cc4101 动态 primary → dsv4f0731_nv
2. dsv4f0731_nv 一次成功 (主链已用健康模型), 用户无感知
3. 多 tier round-robin + func_health fid 健康选择自适应吸收底层跨 key/fid 瞬态失败
4. 坏 fid 52e1ddb6 (hermes 宿主) 与主链健康 fid 容器+候选池双层隔离