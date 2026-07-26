"""cx4102 — Codex Responses API ↔ Chat Completions 适配层.

职责 (严格分层, 模块化铁律):
  - 仅做 Responses API ↔ Chat Completions 格式互转 (request/response/stream)
  - fallback 编排: primary(nv_gw) 5xx/超时/all_tiers_exhausted → fallback(ms_gw)
  - 给 agent 发"重要提醒但不中断任务" (在 response 里插入)
  - 不持 key, 不做 cooldown, 不处理 429/空响应 (那些在 nv_gw/ms_gw)

代码来源: 抄 /opt/cc-infra/proxy/legacy-codex/gateway/codex.py 的转换函数,
砍掉 key 轮转逻辑, 改成无状态 httpx 转发 + fallback.
"""
