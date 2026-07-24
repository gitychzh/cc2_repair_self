# cc4101 — CC (cc2) 专用 glm5.2 Anthropic↔OpenAI 转换网关.
# R684: 全新独立链路, 不掺杂其他模型. 后端 primary=nv_gw(glm5_2_nv), fallback=ms_gw(glm5_2_ms).
# 纯标库 + psycopg2(DB). 自写代码, 不 import litellm.
FROM python:3.12-slim
WORKDIR /app
RUN python3 -m pip install --quiet --no-cache-dir "psycopg2-binary>=2.9"
RUN mkdir -p /app/logs
COPY gateway/ ./gateway/
COPY gateway_main.py .
ENTRYPOINT ["python3"]
CMD ["gateway_main.py"]
