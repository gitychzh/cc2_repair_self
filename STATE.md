# STATE — cc2 自优化 nv_gw 链路 (R-nvonly 方向)

## 当前轮基线 (2026-08-02 14:30 CST, R-nvonly-post266 修复轮)
- 本仓 master: 本轮 post266. (主仓 hermes_improve_self main 收 round 文件.)
- **本轮 R-nvonly-post266 (hm2_cc2)**: 修复轮. 发现 buffer 拦截路径硬调
  `_try_glm52_mode_chain` 在 NV_GLM52_MODE_CHAIN 空(设计)时必败 → 8/10 cc2 请求无谓
  ms_gw fallback. 改 `buffer_stream._execute_and_drain`: MODE_CHAIN 空时委托
  `execute_request` (integrate-first 健康路径).
- 改动文件: `/opt/cc-infra/proxy/nv-gw/gateway/buffer_stream.py`
  (备份 `buffer_stream.py.bak.R266`).
- 已 restart nv_gw, /health ok. 功能验证待下个 cc2 流量窗口.

## R-nvonly 核心铁律 (持续生效)
- 只改 HM2 nv_gw (40006), 不碰 HM1, 不碰 ms_gw 源码.
- ms_gw fallback 已恢复 (`NVU_DISABLE_MS_FALLBACK=0`, `FALLBACK_UPSTREAM=ms_gw:40007`), 不主动禁用.
- 改前有数据, 改后必验证, 写入仓库.

## 本轮关键数据 (30min, 14:18 CST 注入 + 14:27 复查)

### 1. cc4101-primary (cc2) 40min 窗口 — 10 req, 8 fallback
- b6f90fbb (13:54) 200 nv-direct k2 70s ✓
- 7cec9420 (14:16) 200 fb kidx=null 175s ✗fallback
- 0c572fd4 (14:16) 200 fb kidx=null 195s ✗fallback
- df4ded73 (14:17) 200 fb kidx=null 167s ✗fallback
- f4447b2f (14:17) 200 fb kidx=null 171s ✗fallback
- aa9e0dcf (14:20) 200 fb kidx=null 168s ✗fallback
- 016b97bb (14:20) 200 fb kidx=null 169s ✗fallback
- 27d7f498 (14:21) 200 nv-direct k3 5s ✓
- 584d81fb (14:23) 200 fb kidx=null 200s ✗fallback
- 43c72521 (14:23) 200 fb kidx=null 203s ✗fallback
- primary 链 SR = 2/10 = 20% (表面 SR=100% 全靠 ms fallback 兜底).

### 2. 日志根因 (8 fallback 请求)
- 全走 `NV-BUF2KEY-INTERCEPT` → `NV-BUFFER-EXEC-FAIL` 5×attempt, attempt1 elapsed=0s,
  all_keys_exhausted=True, **无 NV-GLM52-*/NV-INTEGRATE 日志**.
- `_try_glm52_mode_chain` (upstream.py:1378-1384): `if not modes: all_keys_exhausted=True;
  return` — 无日志, 0s 返回.
- `NV_GLM52_MODE_CHAIN=` (空, docker-compose.yml:97, R-nvonly-post14 设计).
- `execute_request` (upstream.py:1706) 对 glm5_2_nv 已正确门控 (MODE_CHAIN 空跳过 mode chain),
  但 buffer 拦截路径**无条件**调 mode chain → 必败.
- 2 成功请求走 NV-REQ→NV-INTEGRATE (未拦截, 健康).

### 3. 其他 caller (非 cc2)
本轮 dsv4p_nv hermes+other 38req 100% SR (非 cc2 链路, 不介入).

## 健康验证 (14:30 CST, restart 后)
| 验证项 | 结果 |
|--------|------|
| py_compile (ast.parse) | SYNTAX OK ✓ |
| docker compose restart nv_gw | Started ✓ |
| nv_gw /health | ok, passthrough, 5 keys, default glm5_2_nv ✓ |
| docker ps | nv_gw Up, cc4101/nv_gw_stable/ms_gw/logs_db Up ✓ |
| 配置 | NVU_DISABLE_MS_FALLBACK=0, NV_GLM52_MODE_CHAIN= (空, 不变) ✓ |
| 功能验证 | 待下个 cc2 流量窗口 (期望 DELEGATE 命中 + fb=f + dur 5-70s) ⏳ |

## 本轮改动详情
`buffer_stream.py _execute_and_drain`:
```python
if NV_GLM52_MODE_CHAIN:
    chain_result = _try_glm52_mode_chain(...)
else:
    _log("NV-BUFFER-EXEC-DELEGATE", ...)
    chain_result = execute_request(self.handler, self.oai_body, _mapped, _rid, self.metrics, _chain_t_start)
```
+ config 导入 NV_GLM52_MODE_CHAIN.
+ 新增 NV-BUFFER-EXEC-DELEGATE 日志.
备份: buffer_stream.py.bak.R266. round 文件: rounds/R266_buffer_modechain_empty_delegate.md.

## 参数快照 (2026-08-02 14:30 CST, 本轮未改参数, 只改 buffer_stream.py)
- nv_gw: NVU_DISABLE_MS_FALLBACK=0, BUFFER_MAX_RETRIES=5, BUFFER_TIMEOUT_STAIRS=90,90,90,90,90, BUFFER_TOTAL_DEADLINE=450s, TIER_TIMEOUT_BUDGET=180s, TIER_COOLDOWN_S=180s, UPSTREAM_TIMEOUT=90s, KEY_COOLDOWN_S=30, NV_INTEGRATE_KEY_COOLDOWN_S=90, MIN_OUTBOUND_INTERVAL_S=10, NVU_FORCE_STREAM_UPGRADE_TIMEOUT=150, NVU_FORCE_STREAM_UPGRADE=0, NVU_BUFFER_CALLERS=cc4101-primary,openclaw2, NVU_PEER_FB_SKIP_MODELS=glm5_2_nv,dsv4p_nv, NVU_CALLER_KEY_MAP=hermes:2;openclaw:3;opencode:4, NV_GLM52_MODE_CHAIN= (空, R-nvonly-post14 设计)
- cc4101: CC4101_STREAM_TOTAL_DEADLINE_S=470, PRIMARY_HEADER_TIMEOUT=400, UPSTREAM_TIMEOUT=130, UPSTREAM_IDLE_TIMEOUT=150, CC4101_PRIMARY_SKIP_S=30, CC4101_PRIMARY_FAIL_THRESHOLD=3, FALLBACK_UPSTREAM_URL=http://ms_gw:40007/v1/chat/completions, PRIMARY_UPSTREAM_URL=http://nv_gw:40006/v1/messages, PRIMARY_UPSTREAM_MODEL=glm5_2_nv, FALLBACK_UPSTREAM_MODEL=glm5_2_ms

## 下一步
1. 等下个 cc2 glm5_2_nv 流量窗口, 确认 NV-BUFFER-EXEC-DELEGATE 命中 + fallback_occurred=f
   + nv_key_idx 填充 + dur 回到正常 (5-70s). 验证修复生效.
2. 若仍 fallback, 检查 execute_request 内部是否走了 nv_breaker/big_input breaker 短路到 ms.
3. 路由差异 (部分 cc2 请求进 buffer, 部分进 NV-REQ) 悬而未决, 待流量样本增多后定位.
