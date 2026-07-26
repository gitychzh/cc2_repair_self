#!/usr/bin/env python3
"""Error response formatting for ms_gw.

Returns structurally-valid OpenAI error responses so agent OpenAI clients
can handle them via standard error paths (not bare HTTP 503).
"""
import json


def _openai_error(status, message, error_type="ms_proxy_error", code=None):
    """Build a structurally valid OpenAI-style error response body."""
    return {
        "error": {
            "message": message,
            "type": error_type,
            "code": code or error_type,
            "param": None,
        }
    }


def all_keys_exhausted_error(model, attempt_summary=""):
    """All 7 keys × 10 variants exhausted — return 503 + OpenAI error."""
    msg = (f"ms_gw: all keys exhausted for model={model}. "
           f"Attempted: {attempt_summary}" if attempt_summary
           else f"ms_gw: all keys exhausted for model={model}")
    return 503, _openai_error(503, msg, error_type="ms_all_keys_exhausted",
                              code="all_keys_exhausted")


def model_not_found_error(model):
    return 404, _openai_error(404, f"ms_gw: model '{model}' not found. "
                              f"Available: see /v1/models",
                              error_type="ms_model_not_found", code="model_not_found")


def model_disabled_error(model):
    return 501, _openai_error(501, f"ms_gw: model '{model}' is declared but "
                              "not implemented yet",
                              error_type="ms_model_not_implemented",
                              code="not_implemented")


def auth_error():
    return 401, _openai_error(401, "ms_gw: missing or invalid Authorization. "
                              "Expected: Bearer <MSU_GATEWAY_API_KEY>",
                              error_type="ms_auth_error", code="auth_required")


def bad_request_error(msg):
    return 400, _openai_error(400, f"ms_gw: {msg}",
                              error_type="ms_bad_request", code="bad_request")


def upstream_error(status, body_text, model):
    """Pass-through upstream error when we can't cycle further."""
    return status, _openai_error(status, f"ms_gw upstream error for {model}: {body_text}",
                                 error_type="ms_upstream_error", code="upstream_error")
