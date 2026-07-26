#!/usr/bin/env python3
"""NVCF pexec request construction and response validation.

Extracted from upstream.py (Reng modularization). Logic is byte-for-byte
equivalent to the original; no behavioral change.

- _build_pexec_body: per-model param stripping (strip_params declaration)
- _check_empty_200: detect 200 responses with null/empty choices → treat as failure
"""
import json

from .config import NV_MODEL_IDS
from .logger import _log


def _build_pexec_body(oai_body, tier_model, nvcf_config):
    """Build NVCF pexec request body with per-model param stripping.

    R38.12: Each model declares which params NVCF pexec rejects via strip_params.
    - deepseek/kimi: strip_params=[] → all params pass through ✅
    - glm5_2: strip_params=["thinking_budget"] → strip thinking_budget (NVCF 400) ❌
      reasoning_effort is OK (tested 200 OK) → NOT stripped.

    Args:
        oai_body: original OpenAI-format request body from Hermes
        tier_model: internal NV model key (dsv4p_nv)
        nvcf_config: NVCF_PEXEC_MODELS[tier_model] dict

    Returns: request body dict, ready for json.dumps
    """
    pexec_body = dict(oai_body)
    pexec_body["model"] = NV_MODEL_IDS[tier_model]

    # Per-model param stripping (declaration in nvcf_config["strip_params"])
    strip_params = nvcf_config.get("strip_params", [])
    for param in strip_params:
        pexec_body.pop(param, None)

    # thinking-inject (2026-07-01, per-model 抓包驱动):
    # 每个 model 的 NVCF_PEXEC_MODELS[tier]["inject"] dict 声明要注入的 body 参数
    # (key=参数路径顶层名, value=要设的值). 不同后端思考触发参数各异(抓包证实):
    #   - dsv4p sglang 8915fd28: reasoning_effort (OpenAI 风格)
    #   - glm5_2 3b9748d8:       chat_template_kwargs.enable_thinking (glm 原生)
    # 客户端已自带该参数则不覆盖(尊重 openclaw --thinking xhigh 等显式设置).
    # 注入在 strip 之后, 故 strip 掉的参数由 inject 补回正确形式(如 glm5_2 strip 掉 reasoning_effort
    # 因对它无效, 再由 inject 补 chat_template_kwargs).
    inject_map = nvcf_config.get("inject", {}) or {}
    for param, value in inject_map.items():
        if param not in pexec_body:
            pexec_body[param] = value
            _log("NV-INJECT-THINKING", f"({tier_model}) body had no {param} → injected {param}={value!r}")

    return pexec_body


def _check_empty_200(resp, key_idx, tier_model, is_stream):
    """Check if a 200 response is actually empty (no real content).

    NV API can return 200 with null choices, null content, or empty response.
    These are treated as failures and trigger key cycling or fallback.

    Returns: True if empty 200, False if valid response.
    On valid non-stream: sets resp._hm_cached_body for later use.
    """
    content_length_str = resp.getheader("Content-Length", "-1")

    if is_stream:
        # Streaming: can't read body. Content-Length=0 is a strong signal.
        if content_length_str == "0":
            _log("NV-EMPTY-200", f"k{key_idx+1} ({tier_model}) → 200 Content-Length:0 (stream)")
            return True
        return False

    # Non-streaming: read and inspect body
    resp_body = resp.read()
    resp._hm_cached_body = resp_body

    if not resp_body or len(resp_body) == 0:
        _log("NV-EMPTY-200", f"k{key_idx+1} ({tier_model}) → 200 empty body (0 bytes)")
        return True

    try:
        oai_resp = json.loads(resp_body)
    except (json.JSONDecodeError, ValueError):
        _log("NV-EMPTY-200", f"k{key_idx+1} ({tier_model}) → 200 unparseable body ({len(resp_body)}b)")
        return True

    choices = oai_resp.get("choices")
    if choices is None:
        _log("NV-EMPTY-200", f"k{key_idx+1} ({tier_model}) → 200 choices=null")
        return True
    if isinstance(choices, list) and len(choices) == 0:
        _log("NV-EMPTY-200", f"k{key_idx+1} ({tier_model}) → 200 choices=[] (empty)")
        return True
    if isinstance(choices, list) and choices[0] is None:
        _log("NV-EMPTY-200", f"k{key_idx+1} ({tier_model}) → 200 choices[0]=null")
        return True
    if isinstance(choices, list) and len(choices) > 0:
        msg = choices[0].get("message")
        if msg is None:
            _log("NV-EMPTY-200", f"k{key_idx+1} ({tier_model}) → 200 message=null")
            return True
        content = msg.get("content")
        # R844 F8: content is None 或 content=="" (空字符串) 都判 empty. 原只判 None 漏空字符串.
        # 场景: NVCF 返 200 content="" reasoning_content="" 空僵尸.
        if content is None or (isinstance(content, str) and content.strip() == ""):
            # R765: glm5_2_nv thinking 模式下 content 可能为 null, 思考输出在 reasoning_content.
            # 把有 reasoning_content 的响应视为有效 (非 empty), 避免 cycle/abort 误杀.
            reasoning = msg.get("reasoning_content")
            if reasoning and (isinstance(reasoning, str) and reasoning.strip()):
                _log("NV-THINKING-OK", f"k{key_idx+1} ({tier_model}) → 200 content=null/empty but reasoning_content present ({len(str(reasoning))} chars), treating as valid")
                return False
            _log("NV-EMPTY-200", f"k{key_idx+1} ({tier_model}) → 200 content={content!r} and no reasoning_content")
            return True

    return False
