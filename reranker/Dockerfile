FROM python:3.12-slim

WORKDIR /app

# 安装 uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# 清华源
ENV UV_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple

# 安装依赖到系统 Python
COPY pyproject.toml ./
RUN uv pip install --system --no-cache .

COPY app/ ./app/

EXPOSE 8002

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8002"]
