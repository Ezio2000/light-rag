# Light-RAG

轻量级 RAG 知识库系统。Docker 部署模型和向量库，业务逻辑全部本地 Python 执行。

## 架构

```
┌─────────── Docker 容器（纯基础设施）────────────┐
│                                                  │
│  Embedding (:8001)    Chroma (:8000)   Reranker (:8002) │
│  模型推理              向量数据库       模型推理（可选）   │
└──────────────────────────────────────────────────┘
                       ↕ HTTP
┌──────────── 本地 light_rag/（业务逻辑）──────────┐
│  keywords.py  → 关键词提取（jieba）               │
│  search.py    → 检索编排                          │
│  importer.py  → 文档导入                          │
│  config.py    → 配置管理                          │
└──────────────────────────────────────────────────┘
```

两层职责分离：
- **Docker**：只跑模型推理和向量存储，无业务逻辑
- **light_rag/**：核心 RAG 逻辑，可独立使用，可接入任何场景

## 快速开始

### 前置条件

| 依赖 | 验证命令 |
|------|----------|
| Docker + Docker Compose | `docker compose version` |
| uv | `uv --version` |
| 磁盘空间 ~5GB（模型 + 向量库） | |

### 1. 启动服务

```bash
cp .env.example .env
docker compose up -d
```

首次启动需下载模型（Embedding ~1.2GB，Reranker ~2.3GB）：

```bash
docker compose logs -f embedding   # 查看下载进度
```

等待看到 `Model loaded successfully` 即可。

### 2. 安装本地依赖

```bash
uv sync
```

### 3. 导入知识文档

将文档放入 `knowledge/` 目录（支持 `.md` `.txt` `.py` `.json` `.yaml` `.yml`），然后：

```bash
uv run python -m light_rag import knowledge/
```

### 4. 验证检索

```bash
echo '{"prompt": "谢宁筠是谁"}' | uv run python -m light_rag search
```

接入其他系统（Claude Code、Web API、聊天机器人等）请参考 [docs/integrations/](docs/integrations/) 目录下的文档。

## 目录结构

```
.
├── light_rag/              # 核心 RAG 库（可独立使用）
│   ├── __init__.py
│   ├── __main__.py         # CLI 入口
│   ├── config.py           # 统一配置
│   ├── keywords.py         # jieba 关键词提取
│   ├── search.py           # 检索编排
│   └── importer.py         # 文档导入
├── embedding/              # Embedding Docker 服务
│   ├── Dockerfile
│   ├── pyproject.toml
│   └── app/main.py         # 纯模型推理（FastAPI）
├── reranker/               # Reranker Docker 服务
│   ├── Dockerfile
│   ├── pyproject.toml
│   └── app/main.py         # 纯模型推理（FastAPI）
├── knowledge/              # 知识文档目录
├── data/                   # Chroma 持久化存储
├── docs/integrations/      # 接入文档
├── docker-compose.yml      # Docker 服务编排
├── pyproject.toml          # 本地依赖（requests + jieba）
└── .env                    # 环境变量
```

## CLI 用法

```bash
# 检索（stdin JSON → stdout JSON）
echo '{"prompt": "你的问题"}' | uv run python -m light_rag search

# 导入文档（默认 knowledge/ 目录）
uv run python -m light_rag import

# 导入指定目录
uv run python -m light_rag import /path/to/docs
```

`light_rag` 不依赖任何特定平台，可作为库接入任何场景。

## 配置参考

### Docker 服务（.env）

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `EMBEDDING_PORT` | 8001 | Embedding 服务端口 |
| `EMBEDDING_MODEL` | BAAI/bge-large-zh-v1.5 | 向量化模型 |
| `CHROMA_PORT` | 8000 | Chroma 端口 |
| `RERANKER_PORT` | 8002 | Reranker 端口 |
| `RERANK_MODEL` | BAAI/bge-reranker-v2-m3 | 重排序模型 |
| `HF_CACHE_DIR` | ~/.cache/huggingface | 模型缓存目录 |

### 检索参数（环境变量）

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `EMBEDDING_URL` | http://localhost:8001 | Embedding 地址 |
| `CHROMA_URL` | http://localhost:8000 | Chroma 地址 |
| `RAG_TOP_K` | 3 | 返回最大条数 |
| `RAG_MAX_CONTENT_LENGTH` | 300 | 每条结果最大字符数 |
| `RAG_DISTANCE_THRESHOLD` | 0.5 | 向量距离阈值 |
| `RERANK_ENABLED` | false | 是否启用重排 |
| `RERANKER_URL` | http://localhost:8002 | Reranker 地址 |
| `RERANK_CANDIDATES` | 5 | 重排候选数量 |
| `RERANK_SCORE_THRESHOLD` | 0.3 | 重排分数阈值 |
| `KEYWORD_EXTRACT_ENABLED` | true | 是否启用关键词提取 |

### 导入参数（环境变量）

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `CHUNK_SIZE` | 500 | 分块大小（字符） |
| `CHUNK_OVERLAP` | 50 | 分块重叠 |

## 常用命令

```bash
# Docker 管理
docker compose up -d              # 启动全部
docker compose up -d embedding chroma  # 不含 Reranker
docker compose down               # 停止
docker compose logs -f embedding  # 查看日志

# 重建（修改 embedding 代码后）
docker compose up -d --build embedding
```

## 常见问题

### 服务启动慢

首次需下载模型。通过 `docker compose logs -f embedding` 查看进度。国内网络可配置 HuggingFace 镜像。

### 检索不到结果

- 确认已导入文档：`uv run python -m light_rag import knowledge/`
- 确认 Docker 服务运行：`docker compose ps`
- 调大距离阈值：`RAG_DISTANCE_THRESHOLD=1.0`
