#!/usr/bin/env python3
"""cc4101 gateway — CC-dedicated glm5.2 透传层 (R1711 透传化后).

R684/R1648/R1711 演进: 从 anth↔oai 双转换器 → 纯透传层.
  - Listens on :4101, serves /v1/messages (Anthropic format).
  - R1711: 不再做 anth→oai 转换, 直接透传 anthropic body 给
    nv_gw/ms_gw 的 /v1/messages (anthropic) 端点. 转换/诊断 (zombie/
    content_filter/recv-fallback) 全下沉 nv_gw ��� (R1704 补齐).
  - cc4101 仅改写 body.model = glm5_2_nv/glm5_2_ms 做路由 (nv_gw
    MODEL_MAP 无 claude-*, 不改会路由到 dsv4p_nv 错误 tier).
  - Primary upstream: nv_gw (40006) /v1/messages glm5_2_nv.
  - Fallback upstream: ms_gw (40007) /v1/messages glm5_2_ms
    (仅 breaker OPEN 时切, 流中途 zombie 不切 — 透传 api_error 给 CC 重试).
  - Breaker 信号纯连接级 (clean EOF=success, 连接级异常=failure).
  - Structured PG logging → hermes_logs.cc_requests (async, best-effort).

Modular structure:
  config.py        — env vars, upstream URLs, MODEL_MAP
  stream.py        — passthrough_stream, passthrough_nonstream (纯透传)
  error_mapping.py — convert_error
  upstream.py      — primary→fallback 两级执行器, 透传 anthropic body
  circuit.py       — primary circuit breaker (纯连接级 record_*)
  db.py            — async PG writer (queue + daemon thread + batch INSERT)
  logger.py        — _log, _log_metrics, _log_error_detail (JSONL + console)
  handlers.py      — ProxyHandler (/v1/messages + /health + /v1/models)
  app.py           — ThreadedHTTPServer + main entry point
"""
