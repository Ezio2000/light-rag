FROM python:3.12-slim

WORKDIR /app

# 配置 uv 镜像源（清华源）
ENV UV_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 安装 uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

# 复制项目文件
COPY pyproject.toml ./
COPY app/ ./app/

# 使用 uv sync 安装依赖
RUN uv sync

EXPOSE 8002

# 使用 uv run 启动（自动激活虚拟环境）
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8002"]
