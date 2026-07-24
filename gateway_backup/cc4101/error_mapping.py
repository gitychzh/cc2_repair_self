#!/usr/bin/env python3
"""Error format conversion for cc4101 (OpenAI error → Anthropic error).

R684: Adapted from legacy-cc/gateway/error_mapping.py. cc4101 serves CC
(Anthropic format), so only the Anthropic error path is needed.

CC error-type semantics (must respect — wrong mapping breaks CC):
  - authentication_error → CC hard-stops (fatal)
  - invalid_request_error → CC stops (client error)
  - rate_limit_error → CC retries with backoff
  - api_error → CC retries (server error, recoverable)

Mapping strategy (key points, see convert_error docstring for detail):
  - 429 quota/rate → rate_limit_error (CC backoff, correct for both)
  - 400 "inappropriate content" → invalid_request_error (not recoverable, CC stops)
  - 400 input overflow "Range of input length" → invalid_request_error (CC stops, no compact)
  - 401/403 auth → api_error (NOT authentication_error, to prevent CC freeze)
  - everything else → api_error (CC retries)
"""
import json

from .logger import _log


def convert_error(error_json, request_model):
    """Convert OpenAI error format → Anthropic error format.

    See module docstring for the CC error-type semantics that drive each branch.
    """
    err = error_json.get("error", error_json)
    msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
    msg_lower = msg.lower()
    err_type = "api_error"

    err_code = ""
    if isinstance(err, dict):
        err_code = (err.get("code") or "").lower()
    is_quota_exhausted = (
        "insufficient_quota" in err_code
        or ("quota" in msg_lower and "exceeded" in msg_lower)
        or ("exceeded your current quota" in msg_lower)
    )

    if is_quota_exhausted:
        err_type = "rate_limit_error"
        _log("QUOTA-MAP", f"insufficient_quota → rate_limit_error (msg: {msg[:100]})")
    elif "rate limit" in msg_lower or "rate_limit" in msg_lower or "429" in msg_lower:
        # R690 cc2 red-team: bare "rate" matches "operate", "moderate", "generate",
        # mis-mapping generic api_errors as rate_limit_error. Tighten to phrases that
        # actually indicate a rate limit. (insufficient_quota handled above.)
        err_type = "rate_limit_error"

    elif "inappropriate content" in msg_lower:
        err_type = "invalid_request_error"
        _log("CONTENT-MAP", f"inappropriate content → invalid_request_error (msg: {msg[:100]})")

    elif (("range of input length" in msg_lower)
          or ("invalidparameter" in msg_lower and ("input length" in msg_lower or "input token" in msg_lower or "exceeds" in msg_lower))):
        err_type = "invalid_request_error"
    return {"type": "error", "error": {"type": err_type, "message": msg}, "model": request_model}


def get_upstream_status_for_client(upstream_status):
    """Map upstream HTTP status → client-facing status. 429 passes through."""
    return upstream_status


def is_input_overflow(error_json, resp_status):
    """Detect upstream 400 input-token overflow."""
    err_lower = json_to_str_lower(error_json)
    return (
        resp_status == 400
        and (
            ("exceeds" in err_lower and ("token" in err_lower or "limit" in err_lower))
            or ("range of input length" in err_lower)
            or ("invalidparameter" in err_lower and ("input length" in err_lower or "input token" in err_lower))
        )
    )


def json_to_str_lower(error_json):
    return json.dumps(error_json).lower()
