# nv_gw — NV 上游网关 (三 agent 通用). NVCF pexec/integrate direct path.
# R680: 去 litellm base. 自写代码纯标库 + psycopg2(DB) + PySocks(SOCKS5, 代码 import socks).
# R859: 换 ASGI 异步框架. ThreadingHTTPServer+同步 http.client → FastAPI+uvicorn+httpx[socks].
#   根因: handlers._stream_openai_passthrough 的 resp.read(8192) 裸阻塞无 per-read timeout,
#   NVCF 返回 200 头(打 SUCCESS)后 body 不发则无限阻塞, deadline 在循环顶部是死代码.
#   async httpx 的 read timeout 真正在 event loop 层生效, 不再卡死.
FROM python:3.12-slim
WORKDIR /app
RUN python3 -m pip install --quiet --no-cache-dir \
    "PySocks>=1.7.1" \
    "psycopg2-binary>=2.9" \
    "fastapi>=0.115" \
    "uvicorn>=0.30" \
    "httpx[socks]>=0.27"
RUN mkdir -p /app/logs
COPY gateway/ ./gateway/
COPY gateway_main.py .
ENTRYPOINT ["python3"]
CMD ["gateway_main.py"]
