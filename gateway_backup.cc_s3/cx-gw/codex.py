#!/usr/bin/env python3
"""Responses API ↔ Chat Completions 格式转换 (纯函数).

抄自 /opt/cc-infra/proxy/legacy-codex/gateway/codex.py, 去掉对 handler/conn 的依赖,
改成纯函数: 输入 dict → 输出 dict / SSE event.

cx4102 用 aiohttp, SSE 事件由 forwarder/app 层 yield, 转换函数只负责生成 event payload.
"""
import json
import uuid
import time


# ─── ID 生成 ──────────────────────────────────────────────────────────────
def _gen_resp_id():
    return f"resp_{uuid.uuid4().hex[:24]}"


def _gen_msg_id():
    return f"msg_{uuid.uuid4().hex[:24]}"


def _gen_fc_id():
    return f"fc_{uuid.uuid4().hex[:8]}"


def _gen_call_id():
    return f"call_{uuid.uuid4().hex[:24]}"


# ─── Request: Responses API → Chat Completions ────────────────────────────
def responses_to_chat_body(cx_body, target_model):
    """Responses API request → Chat Completions request body (纯函数, 抄 legacy-codex).

    映射: instructions→system, input[]→messages, tools→function tools,
          max_output_tokens→max_tokens, stream→stream+stream_options.
    """
    oai_messages = []

    # 1. instructions → system message
    instructions = cx_body.get("instructions", "")
    if instructions:
        oai_messages.append({"role": "system", "content": instructions})

    # 2. input → messages
    input_data = cx_body.get("input", "")
    if isinstance(input_data, str):
        if input_data:
            oai_messages.append({"role": "user", "content": input_data})
    elif isinstance(input_data, list):
        for item in input_data:
            if isinstance(item, dict):
                item_type = item.get("type", "")
                if item_type == "message":
                    # R825: OpenAI Responses "developer" role == system; ModelScope/GLM
                    # rejects it (400 invalid_parameter_error). Normalize at source.
                    role = item.get("role", "user")
                    if role == "developer":
                        role = "system"
                    content = item.get("content", "")
                    if isinstance(content, list):
                        text_parts = []
                        for c in content:
                            if isinstance(c, dict):
                                if c.get("type") == "input_text":
                                    text_parts.append(c.get("text", ""))
                                elif c.get("type") == "input_image":
                                    img_url = c.get("image_url", "")
                                    oai_messages.append({
                                        "role": role,
                                        "content": [{"type": "image_url", "image_url": {"url": img_url}}],
                                    })
                                else:
                                    text_parts.append(c.get("text", str(c)))
                            elif isinstance(c, str):
                                text_parts.append(c)
                        if text_parts:
                            oai_messages.append({"role": role, "content": "\n".join(text_parts)})
                    elif isinstance(content, str):
                        oai_messages.append({"role": role, "content": content})
                    else:
                        oai_messages.append({"role": role, "content": str(content)})
                elif item_type == "function_call":
                    oai_messages.append({
                        "role": "assistant", "content": None,
                        "tool_calls": [{
                            "id": item.get("call_id", f"call_{uuid.uuid4().hex[:24]}"),
                            "type": "function",
                            "function": {"name": item.get("name", ""), "arguments": item.get("arguments", "{}")},
                        }],
                    })
                elif item_type == "function_call_output":
                    oai_messages.append({
                        "role": "tool", "tool_call_id": item.get("call_id", ""),
                        "content": item.get("output", ""),
                    })
                else:
                    content = item.get("content", item.get("text", ""))
                    if content:
                        oai_messages.append({"role": "user", "content": str(content)})
            elif isinstance(item, str):
                oai_messages.append({"role": "user", "content": item})

    if not oai_messages:
        oai_messages.append({"role": "user", "content": "test"})

    oai_body = {
        "model": target_model,
        "messages": oai_messages,
        "stream": cx_body.get("stream", False),
    }

    max_output = cx_body.get("max_output_tokens")
    if max_output:
        oai_body["max_tokens"] = max_output
        oai_body["max_completion_tokens"] = max_output
    else:
        oai_body["max_tokens"] = 4096
        oai_body["max_completion_tokens"] = 4096

    if cx_body.get("temperature"):
        oai_body["temperature"] = cx_body["temperature"]

    # tools — 只转 function 类型 (其他 web_search/code_interpreter 等后端不支持)
    cx_tools = cx_body.get("tools", [])
    if cx_tools:
        oai_tools = []
        for tool in cx_tools:
            if tool.get("type") == "function":
                fn = tool.get("function", {})
                if fn.get("name"):
                    oai_tools.append({
                        "type": "function",
                        "function": {
                            "name": fn["name"],
                            "description": fn.get("description", ""),
                            "parameters": fn.get("parameters", {}),
                        },
                    })
        if oai_tools:
            oai_body["tools"] = oai_tools

    tool_choice = cx_body.get("tool_choice")
    if tool_choice and oai_body.get("tools"):
        oai_body["tool_choice"] = tool_choice

    if cx_body.get("response_format"):
        oai_body["response_format"] = cx_body["response_format"]

    if oai_body.get("stream") and "stream_options" not in oai_body:
        oai_body["stream_options"] = {"include_usage": True}

    return oai_body


# ─── Response: Chat Completions → Responses API (非流) ────────────────────
def chat_to_responses(oai_response, request_model, fallback_notice=None):
    """Chat Completions response dict → Responses API response dict (纯函数).

    fallback_notice: 若非 None, 在 output message 前面插入提醒文本 (不中断任务).
    """
    resp_id = _gen_resp_id()
    output = []
    usage = oai_response.get("usage", {})
    input_tokens = usage.get("prompt_tokens", 0)
    output_tokens = usage.get("completion_tokens", 0)

    choices = oai_response.get("choices", [])
    if not choices:
        output.append({
            "type": "message", "id": _gen_msg_id(), "role": "assistant",
            "content": [{"type": "output_text", "text": ""}], "status": "completed",
        })
    else:
        choice = choices[0]
        # 兼容: 非流响应应该用 message, 但 ms_gw 有时同时返回 message(空 content)
        # + delta(带 reasoning_content), 要合并取
        message = choice.get("message") or {}
        delta = choice.get("delta") or {}
        finish_reason = choice.get("finish_reason", "stop")

        msg_content = []
        # 合并 message + delta 的 content / reasoning_content (delta 优先, 因为更新)
        text_content = (message.get("content") or "") or (delta.get("content") or "")
        reasoning_content = (message.get("reasoning_content") or "") or (delta.get("reasoning_content") or "")
        # 合并 tool_calls
        tool_calls = message.get("tool_calls") or delta.get("tool_calls") or []

        # fallback 提醒插入 (不中断: 提醒 + 原文, agent 看到的是完整 response)
        if fallback_notice:
            msg_content.append({"type": "output_text", "text": fallback_notice + "\n\n"})

        if text_content:
            msg_content.append({"type": "output_text", "text": text_content})
        # R760: reasoning_content 不再作为 output_text 追加 (会把思考过程当正文显示给 agent,
        # 且 reasoning 在多 chunk 重复会导致内容重复/乱码). codex catalog 设了
        # supports_reasoning_summaries=false, 不期望 reasoning, 故直接丢弃.
        # 若未来 agent 需要 reasoning, 应走单独��� reasoning summary item, 不混入 content.
        if not msg_content:
            msg_content.append({"type": "output_text", "text": ""})

        msg_status = "completed" if finish_reason != "length" else "incomplete"
        output.append({
            "type": "message", "id": _gen_msg_id(), "role": "assistant",
            "content": msg_content, "status": msg_status,
        })

        for tc in tool_calls:
            fn = tc.get("function", {})
            output.append({
                "type": "function_call", "id": _gen_fc_id(),
                "call_id": tc.get("id", _gen_call_id()),
                "name": fn.get("name", ""), "arguments": fn.get("arguments", "{}"),
                "status": "completed",
            })

    return {
        "id": resp_id, "object": "response", "created_at": int(time.time()),
        "model": request_model, "status": "completed", "output": output,
        "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens,
                  "total_tokens": input_tokens + output_tokens},
        "metadata": {},
    }


# ─── Stream: Chat Completions SSE → Responses API SSE events ──────────────
# 生成器: 输入上游 SSE chunk dict, yield (event_name, payload_dict).
# 调用方负责 SSE 序列化 (event: xxx\ndata: {...}\n\n).

class StreamConverter:
    """有状态的流转换器 (一个请求一个实例).

    事件序列:
      response.created → response.in_progress → response.output_item.added(message)
      → response.content_part.added → response.output_text.delta* (或 function_call_arguments.delta*)
      → response.content_part.done → response.output_item.done → response.completed
    """

    def __init__(self, request_model):
        self.request_model = request_model
        self.resp_id = _gen_resp_id()
        self.msg_id = _gen_msg_id()
        self.output_index = 0
        self.content_index = 0
        self.text_buffer = ""
        self.active_tool_calls = {}  # call_id → {name, output_index, arguments_buffer}
        self.streaming_input_tokens = 0
        self.streaming_output_tokens = 0
        self.finish_reason = None
        self._initialized = False
        self._tool_call_emitted = False  # 是否已经从 message 切到 function_call
        self.fallback_used = False  # 是否走了 fallback (用于 metadata 提醒)

    def initial_events(self):
        """流开始时的事件序列. 返回 [(event_name, payload), ...]."""
        events = [
            ("response.created", {
                "type": "response.created",
                "response": {
                    "id": self.resp_id, "object": "response", "created_at": int(time.time()),
                    "model": self.request_model, "status": "in_progress",
                    "output": [], "metadata": {},
                },
            }),
            ("response.in_progress", {
                "type": "response.in_progress",
                "response": {"id": self.resp_id, "object": "response", "status": "in_progress"},
            }),
            ("response.output_item.added", {
                "type": "response.output_item.added", "output_index": 0,
                "item": {"type": "message", "id": self.msg_id, "role": "assistant",
                         "content": [], "status": "in_progress"},
            }),
            ("response.content_part.added", {
                "type": "response.content_part.added", "output_index": 0, "content_index": 0,
                "part": {"type": "output_text", "text": "", "annotations": []},
            }),
        ]
        self._initialized = True
        return events

    def feed_chunk(self, chunk_data):
        """喂一个 Chat Completions SSE chunk dict, yield (event_name, payload).

        chunk_data: json.loads(data_str) 的结果.
        """
        if not self._initialized:
            for ev in self.initial_events():
                yield ev

        # usage (流式 chunk 里可能有)
        chunk_usage = chunk_data.get("usage", {})
        if chunk_usage:
            if chunk_usage.get("prompt_tokens", 0) > 0:
                self.streaming_input_tokens = chunk_usage["prompt_tokens"]
            if chunk_usage.get("completion_tokens", 0) > 0:
                self.streaming_output_tokens = chunk_usage["completion_tokens"]

        choices = chunk_data.get("choices", [])
        if not choices:
            return
        delta = choices[0].get("delta", {})
        fr = choices[0].get("finish_reason")

        # R760: content delta → output_text.delta; reasoning_content 单独走 reasoning.delta.
        # 之前把 reasoning+content 合并成一个 output_text.delta 是错的:
        #   1) 思考过程被当成正文显示给 agent
        #   2) reasoning 在多 chunk 重复 → 内容重复
        #   3) 字符串拼接切到多字节字符中段 → 乱码 (如 'total patients totalexecsql...')
        # codex catalog 设 supports_reasoning_summaries=false 会忽略 reasoning 事件,
        # 故 reasoning 不再污染正文. text_buffer 只累加真实 content.
        text_delta = delta.get("content") or ""
        reasoning_delta = delta.get("reasoning_content") or ""
        if reasoning_delta:
            # 单独的 reasoning summary item (output_index 独立, 不混入 message content)
            yield ("response.reasoning.delta", {
                "type": "response.reasoning.delta",
                "output_index": self.output_index, "summary_index": 0,
                "delta": reasoning_delta,
            })
        if text_delta:
            self.text_buffer += text_delta
            yield ("response.output_text.delta", {
                "type": "response.output_text.delta",
                "output_index": self.output_index, "content_index": self.content_index,
                "delta": text_delta,
            })

        # tool_calls → function_call output items
        for tc in (delta.get("tool_calls") or []):
            fn = tc.get("function", {})
            tc_id = tc.get("id")
            if tc_id:
                # 新 tool call → 切换 output_item
                call_id = tc_id
                if not self._tool_call_emitted:
                    # 关闭 message 的 content_part + output_item
                    yield ("response.content_part.done", {
                        "type": "response.content_part.done", "output_index": 0,
                        "content_index": self.content_index,
                        "part": {"type": "output_text", "text": self.text_buffer, "annotations": []},
                    })
                    yield ("response.output_item.done", {
                        "type": "response.output_item.done", "output_index": 0,
                        "item": {"type": "message", "id": self.msg_id, "role": "assistant",
                                 "content": [{"type": "output_text", "text": self.text_buffer, "annotations": []}],
                                 "status": "completed"},
                    })
                    self._tool_call_emitted = True

                self.output_index += 1
                yield ("response.output_item.added", {
                    "type": "response.output_item.added", "output_index": self.output_index,
                    "item": {"type": "function_call", "id": _gen_fc_id(), "call_id": call_id,
                             "name": fn.get("name", ""), "arguments": "", "status": "in_progress"},
                })
                self.active_tool_calls[call_id] = {
                    "name": fn.get("name", ""), "output_index": self.output_index,
                    "arguments_buffer": fn.get("arguments", ""),
                }
                if fn.get("arguments"):
                    yield ("response.function_call_arguments.delta", {
                        "type": "response.function_call_arguments.delta",
                        "output_index": self.output_index, "call_id": call_id,
                        "delta": fn["arguments"],
                    })
            elif fn.get("arguments") and self.active_tool_calls:
                last_call_id = list(self.active_tool_calls.keys())[-1]
                tc_info = self.active_tool_calls[last_call_id]
                tc_info["arguments_buffer"] += fn["arguments"]
                yield ("response.function_call_arguments.delta", {
                    "type": "response.function_call_arguments.delta",
                    "output_index": tc_info["output_index"], "call_id": last_call_id,
                    "delta": fn["arguments"],
                })

        if fr:
            self.finish_reason = fr

    def final_events(self):
        """流结束时的事件序列. 返回 [(event_name, payload), ...]."""
        if not self._initialized:
            # 上游没发任何 chunk, 也要发完整序列
            for ev in self.initial_events():
                yield ev

        # 关闭 active tool calls
        for call_id, tc_info in self.active_tool_calls.items():
            yield ("response.function_call_arguments.done", {
                "type": "response.function_call_arguments.done",
                "output_index": tc_info["output_index"], "call_id": call_id,
                "arguments": tc_info["arguments_buffer"],
            })
            yield ("response.output_item.done", {
                "type": "response.output_item.done", "output_index": tc_info["output_index"],
                "item": {"type": "function_call", "id": _gen_fc_id(), "call_id": call_id,
                         "name": tc_info["name"], "arguments": tc_info["arguments_buffer"],
                         "status": "completed"},
            })

        # 如果没切到 tool_call, 关闭 message
        if not self._tool_call_emitted:
            yield ("response.content_part.done", {
                "type": "response.content_part.done", "output_index": 0,
                "content_index": 0,
                "part": {"type": "output_text", "text": self.text_buffer, "annotations": []},
            })
            yield ("response.output_item.done", {
                "type": "response.output_item.done", "output_index": 0,
                "item": {"type": "message", "id": self.msg_id, "role": "assistant",
                         "content": [{"type": "output_text", "text": self.text_buffer, "annotations": []}],
                         "status": "completed"},
            })

        response_status = "completed" if self.finish_reason != "length" else "incomplete"
        metadata = {}
        if self.fallback_used:
            metadata["fallback_used"] = True
            metadata["fallback_notice"] = "nv_gw 全部 5 key 故障, 已 fallback 到 ms_gw"
        yield ("response.completed", {
            "type": "response.completed",
            "response": {
                "id": self.resp_id, "object": "response", "created_at": int(time.time()),
                "model": self.request_model, "status": response_status, "output": [],
                "usage": {"input_tokens": self.streaming_input_tokens,
                          "output_tokens": self.streaming_output_tokens,
                          "total_tokens": self.streaming_input_tokens + self.streaming_output_tokens},
                "metadata": metadata,
            },
        })
