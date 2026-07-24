# ms_gw — MS (ModelScope) unified proxy for three agents. Pure OpenAI passthrough.
# R680: 去 litellm base, 统一 python:3.12-slim.
# R683: 加 psycopg2-binary (实时 DB 写入, 抄 nv_gw 模式).
FROM python:3.12-slim
WORKDIR /app
RUN python3 -m pip install --quiet --no-cache-dir "psycopg2-binary>=2.9"
RUN mkdir -p /app/logs
COPY gateway/ ./gateway/
COPY gateway_main.py .
ENTRYPOINT ["python3"]
CMD ["gateway_main.py"]
