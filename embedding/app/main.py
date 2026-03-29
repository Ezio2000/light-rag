"""
Embedding Service - 纯模型推理服务
基于 BAAI/bge-large-zh-v1.5 模型（可通过 EMBEDDING_MODEL 环境变量切换）
仅负责文本向量化，不包含任何业务逻辑
"""

import os
from typing import List
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer
import logging

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 配置
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-large-zh-v1.5")

# 初始化 FastAPI
app = FastAPI(
    title="Embedding Service",
    description="文本向量化服务，基于 BGE 模型（纯推理）",
    version="1.0.0"
)

# 全局模型实例
model = None


class EmbedRequest(BaseModel):
    """Embedding 请求"""
    text: str


class EmbedBatchRequest(BaseModel):
    """批量 Embedding 请求"""
    texts: List[str]


class EmbedResponse(BaseModel):
    """Embedding 响应"""
    embedding: List[float]
    dimension: int
    model: str


class EmbedBatchResponse(BaseModel):
    """批量 Embedding 响应"""
    embeddings: List[List[float]]
    dimension: int
    count: int
    model: str


@app.on_event("startup")
async def load_model():
    """启动时加载模型"""
    global model
    logger.info(f"Loading embedding model: {EMBEDDING_MODEL}")
    model = SentenceTransformer(EMBEDDING_MODEL)
    logger.info(f"Model loaded successfully, dimension: {model.get_sentence_embedding_dimension()}")


@app.get("/health")
async def health_check():
    """健康检查"""
    return {
        "status": "healthy",
        "model": EMBEDDING_MODEL,
        "dimension": model.get_sentence_embedding_dimension() if model else None,
    }


@app.post("/embed", response_model=EmbedResponse)
async def embed_text(request: EmbedRequest):
    """单个文本向量化"""
    if model is None:
        raise HTTPException(status_code=503, detail="Model not loaded")

    if not request.text or not request.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty")

    try:
        embedding = model.encode(request.text.strip(), normalize_embeddings=True)
        return EmbedResponse(
            embedding=embedding.tolist(),
            dimension=len(embedding),
            model=EMBEDDING_MODEL,
        )
    except Exception as e:
        logger.error(f"Embedding error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/embed/batch", response_model=EmbedBatchResponse)
async def embed_batch(request: EmbedBatchRequest):
    """批量文本向量化"""
    if model is None:
        raise HTTPException(status_code=503, detail="Model not loaded")

    if not request.texts:
        raise HTTPException(status_code=400, detail="Texts list cannot be empty")

    try:
        embeddings = model.encode(request.texts, normalize_embeddings=True, show_progress_bar=False)
        return EmbedBatchResponse(
            embeddings=embeddings.tolist(),
            dimension=embeddings.shape[1],
            count=len(embeddings),
            model=EMBEDDING_MODEL,
        )
    except Exception as e:
        logger.error(f"Batch embedding error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
