FROM python:3.12-slim

WORKDIR /app/backend

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 数据目录（可被 SZT_DATA_DIR 覆盖）
RUN mkdir -p /app/data /app/backend/data

EXPOSE 8000

# host / port / workers 全部走环境变量
CMD ["sh", "-c", "uvicorn app.main:app --host ${SZT_HOST:-0.0.0.0} --port ${SZT_PORT:-8000} --workers ${SZT_WORKERS:-1} --log-level ${SZT_LOG_LEVEL:-info}"]
