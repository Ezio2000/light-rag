"""
Reranker Service - 重排序服务（扩展点）
基于 BAAI/bge-reranker-v2-m3 模型
"""

import os
from typing import List
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import logging

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 配置
RERANK_MODEL = os.getenv("RERANK_MODEL", "BAAI/bge-reranker-v2-m3")

# 初始化 FastAPI
app = FastAPI(
    title="Reranker Service",
    description="重排序服务，基于 BGE-Reranker 模型（扩展点）",
    version="1.0.0"
)

# 全局模型实例
model = None


class RerankRequest(BaseModel):
    """Rerank 请求"""
    query: str
    documents: List[str]
    top_k: int = 5


class RerankResult(BaseModel):
    """单条重排结果"""
    index: int
    document: str
    score: float


class RerankResponse(BaseModel):
    """Rerank 响应"""
    results: List[RerankResult]
    model: str


@app.on_event("startup")
async def load_model():
    """启动时加载模型"""
    global model
    logger.info(f"Loading reranker model: {RERANK_MODEL}")
    from sentence_transformers import CrossEncoder
    model = CrossEncoder(RERANK_MODEL)
    logger.info("Reranker model loaded successfully")


@app.get("/health")
async def health_check():
    """健康检查"""
    return {
        "status": "healthy",
        "model": RERANK_MODEL,
        "loaded": model is not None
    }


@app.post("/rerank", response_model=RerankResponse)
async def rerank(request: RerankRequest):
    """重排序"""
    if model is None:
        raise HTTPException(status_code=503, detail="Model not loaded")

    if not request.query or not request.documents:
        raise HTTPException(status_code=400, detail="Query and documents cannot be empty")

    try:
        # 构建 query-document 对
        pairs = [[request.query, doc] for doc in request.documents]
        # 使用 CrossEncoder 计算相关性分数
        scores = model.predict(pairs)

        # 按分数降序排序
        indexed_scores = list(enumerate(scores))
        indexed_scores.sort(key=lambda x: x[1], reverse=True)

        # 取 top_k 结果
        results = [
            RerankResult(
                index=idx,
                document=request.documents[idx],
                score=float(score)
            )
            for idx, score in indexed_scores[:request.top_k]
        ]
        return RerankResponse(results=results, model=RERANK_MODEL)
    except Exception as e:
        logger.error(f"Rerank error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
