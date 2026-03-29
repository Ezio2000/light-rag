"""
统一配置管理 - 所有环境变量和默认值
"""

import os

# Embedding 服务
EMBEDDING_URL = os.getenv("EMBEDDING_URL", "http://localhost:8001")

# Chroma 向量数据库
CHROMA_URL = os.getenv("CHROMA_URL", "http://localhost:8000")
CHROMA_API_VERSION = os.getenv("CHROMA_API_VERSION", "v2")

# Chroma v2 API 基础路径
CHROMA_API_BASE = f"{CHROMA_URL}/api/{CHROMA_API_VERSION}"
CHROMA_COLLECTION_BASE = f"{CHROMA_API_BASE}/tenants/default_tenant/databases/default_database/collections"

# Collection 名称
COLLECTION_NAME = "knowledge"

# 检索配置
RAG_TOP_K = int(os.getenv("RAG_TOP_K", "3"))
RAG_MAX_CONTENT_LENGTH = int(os.getenv("RAG_MAX_CONTENT_LENGTH", "300"))
RAG_DISTANCE_THRESHOLD = float(os.getenv("RAG_DISTANCE_THRESHOLD", "0.5"))

# Reranker 配置
RERANK_ENABLED = os.getenv("RERANK_ENABLED", "false").lower() == "true"
RERANKER_URL = os.getenv("RERANKER_URL", "")
RERANK_CANDIDATES = int(os.getenv("RERANK_CANDIDATES", "20"))
RERANK_SCORE_THRESHOLD = float(os.getenv("RERANK_SCORE_THRESHOLD", "0.3"))

# 文档导入配置
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "500"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "50"))

# 关键词提取配置
KEYWORD_EXTRACT_ENABLED = os.getenv("KEYWORD_EXTRACT_ENABLED", "true").lower() == "true"
