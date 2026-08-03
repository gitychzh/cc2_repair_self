# STATE.md — cc2 自优化 nv_gw 链路 (HM2)

> 当前轮: R713b (OpenClaw 模型配置系统性修复, 2026-08-03 19:35 CST)
> 上轮: R713 (NOP, cc2 零流量 dsv4p_nv SR94.1% glm5_2_nv SR0% NVCF上游退化)

## 本轮 (R713b) 改了什么 + 依据 + 验证

### 改动: OpenClaw 配置修复 (非 nv_gw/dsv4p_nv40066 容器改动)

#### Fix 1: models.json 模型定义修正
**文件**: `~/.openclaw/agents/main/agent/models.json` + `~/.openclaw/openclaw.json`
- `dsv4p_nv` name 从 "GLM 5.2 (ai-glm-5_2 3b9748d8...)" 修正为 "DeepSeek V4 Pro (deepseek-ai/deepseek-v4-pro 12acbc62, reasoning_content)"
- `dsv4p_nv` 移除 `thinkingFormat: "zai"` (DeepSeek 用标准 reasoning_content, 非 GLM 的 zai format)
- 新增 `glm5_2_nv` model 定义 (opclaw4103 FALLBACK_MODEL=glm5_2_nv, 需要在 provider models 列表里定义)
- alias 更新: opclaw4103/glm5_2_nv → "GLM 5.2 (via opclaw4103 adapter, fallback model when dsv4p_nv fails)"

#### Fix 2: config symlink
- `~/.openclaw/config/models.json` → symlink to `~/.openclaw/agents/main/agent/models.json`
- 让 agent 即使尝试 `~/.openclaw/config/models.json` 路径也能读到正确配置

#### Fix 3: MEMORY.md 路径前缀修复
- 去掉项目路径表中的 "workspace/" 前缀 (5处 + 1处编排架构文档)
- 修复 ENOENT double workspace path: `/home/opc2_uname/.openclaw/workspace/workspace/openclaw2_improve_self/openclaw.md`

### 依据
- 用户报告 OpenClaw 报错 "Exec failed: show ~/.openclaw/config/models.json"
- Trajectory 分析: agent (小二) 用 exec 工具尝试 "show ~/.openclaw/config/models.json", "show" 非有效命令, 路径不存在
- DB 验证: `curl http://localhost:4103/v1/chat/completions -d '{"model":"dsv4p_nv"...}'` 返回 `model: deepseek-ai/deepseek-v4-pro`, `reasoning_content` 字段 — 确认是 DeepSeek V4 Pro 非 GLM 5.2
- 日志验证: ENOENT double workspace path 来自 MEMORY.md 路径表用 "workspace/" 前缀, agent read 工具拼接 workspaceDir + path 产生 double workspace

### 验证
- `systemctl --user restart openclaw-gateway` → 重启成功
- `curl http://127.0.0.1:18789/health` → `{"ok":true,"status":"live"}`
- 日志确认: `"agent model: opclaw4103/dsv4p_nv (thinking=medium, fast=off)"`
- 日志确认: `"config hot reload applied (models.providers.opclaw4103.models)"`
- 日志确认: `"feishu[default]: WebSocket client started"` — feishu 连接正常
- 重启后无 ENOENT 或 Exec failed 错误

## 下一步
- 观察 openclaw agent 下一轮自我优化是否正常工作
- 确认 agent 能正确读取 models.json (现在有 symlink)
- 持续监控 cc2 SR + fallback 触发率 (目标 SR99%+ fb<10%)
- glm5_2_nv NVCF 上游持续退化中, 依赖 dsv4p 兜底, 非 nv_gw 可控

## 参数快照 (无变化, 沿用 R661)
- nv_gw: NVU_DISABLE_MS_FALLBACK=1, buffer 5×90s=450s, UPSTREAM_TIMEOUT=90, TIER_COOLDOWN_S=180
  - per-key FID bind: NV_GLM52_KEY_FID_BIND=0:0;2:1;4:2 (k0/k2/k4 pexec fid1/2/3)
  - per-key mode bind: NV_GLM52_KEY_MODE_BIND=0:pexec_us_rr;1:integrate_us_rr;2:pexec_us_rr;3:integrate_us_rr;4:pexec_us_rr
- cc4101: PRIMARY=glm5_2_nv→nv_gw:40006, FALLBACK=dsv4p_nv→dsv4p_nv40066:40066, STREAM_TOTAL=470, HEADER=400, UPSTREAM_IDLE=150
- opclaw4103: PRIMARY=dsv4p_nv→dsv4p_nv40066:40066, FALLBACK=glm5_2_nv→nv_gw:40006, FALLBACK_ENABLED=1
- deadline 链: 90s×5=450s buffer < 470s cc4101 < 600s API < 900s idle
