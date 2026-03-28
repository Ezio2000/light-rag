"""
Embedding Service - 文本向量化服务
基于 BAAI/bge-large-zh-v1.5 模型（可通过 EMBEDDING_MODEL 环境变量切换）
"""

import os
import re
from typing import List
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer
import jieba
import jieba.posseg as pseg
import logging

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 配置
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-large-zh-v1.5")
KEYWORD_EXTRACT_ENABLED = os.getenv("KEYWORD_EXTRACT_ENABLED", "false").lower() == "true"

# 中文停用词表（常见无意义词）
STOPWORDS = {
    # 代词
    "我", "你", "他", "她", "它", "我们", "你们", "他们", "自己", "什么", "这个", "那个",
    "这些", "那些", "哪个", "哪里", "谁", "某", "某们", "各", "每",
    # 副词/连词
    "的", "了", "和", "是", "就", "都", "而", "及", "与", "或", "也", "又", "还", "在",
    "有", "被", "比", "等", "但", "如果", "因为", "所以", "虽然", "但是", "然后", "而且",
    # 量词/助词
    "个", "只", "些", "把", "次", "回", "下", "上", "中", "里", "到", "得", "地",
    # 常见无意义词
    "想", "要", "会", "能", "可以", "一下", "一点", "一种", "一个", "一些", "可能",
    "大概", "也许", "应该", "必须", "需要", "请", "帮", "帮忙", "帮忙看", "帮忙查",
    "怎么", "怎样", "如何", "为什么", "吗", "呢", "吧", "啊", "呀", "哦", "嗯",
    "了解", "知道", "看看", "查查", "找找", "说", "问", "告诉", "给", "让",
    # 补充停用词
    "请问", "查", "看", "找", "算", "做", "用", "来", "去", "过", "起", "来",
}

# 保留的词性（名词、动词、形容词）
ALLOWED_POS = {"n", "v", "a", "nz", "vn", "vg", "an", "ad", "ng"}

# 自定义词典（专业术语，防止被拆分）
CUSTOM_WORDS = [
    # 技术
    ("RAG", 100, "nz"),
    ("Claude", 100, "nz"),
    ("Embedding", 100, "nz"),
    ("Chroma", 100, "nz"),
    ("Hook", 100, "nz"),
    ("API", 100, "nz"),
    ("向量数据库", 100, "nz"),
    ("知识库", 100, "n"),
    # HR 相关
    ("年假", 100, "n"),
    ("请假", 100, "vn"),
    ("请假制度", 100, "n"),
    ("调休", 100, "n"),
    ("加班", 100, "vn"),
    ("社保", 100, "n"),
    ("公积金", 100, "n"),
]

# 添加自定义词到 jieba
for word, freq, pos in CUSTOM_WORDS:
    jieba.add_word(word, freq, pos)

# 初始化 FastAPI
app = FastAPI(
    title="Embedding Service",
    description="文本向量化服务，基于 BGE 模型",
    version="1.0.0"
)

# 全局模型实例
model = None


def extract_keywords(text: str) -> str:
    """
    从文本中提取关键词
    返回关键词拼接的字符串，用于向量检索

    流程：
    1. jieba 分词 + 词性标注
    2. 过滤停用词
    3. 保留名词、动词、形容词
    4. 拼接返回
    """
    words = pseg.cut(text)
    keywords = []

    for word, pos in words:
        word = word.strip()
        # 跳过空词和停用词
        if not word or word in STOPWORDS:
            continue
        # 跳过纯数字和单字符（除非是专业术语）
        if word.isdigit() or (len(word) == 1 and not word.isalpha()):
            continue
        # 保留指定词性
        if pos in ALLOWED_POS or len(word) >= 4:  # 4字以上默认保留（专有名词）
            keywords.append(word)

    # 如果提取不到关键词，返回原文本（兜底）
    if not keywords:
        return text

    return " ".join(keywords)


class EmbedRequest(BaseModel):
    """Embedding 请求"""
    text: str


class EmbedBatchRequest(BaseModel):
    """批量 Embedding 请求"""
    texts: List[str]


class KeywordsResponse(BaseModel):
    """关键词提取响应"""
    original_text: str
    keywords: str
    keyword_list: List[str]
    enabled: bool


class EmbedResponse(BaseModel):
    """Embedding 响应"""
    embedding: List[float]
    dimension: int
    model: str
    original_text: str = None  # 原始文本
    keywords: str = None  # 提取的关键词（仅当启用关键词提取时）


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
        "keyword_extract_enabled": KEYWORD_EXTRACT_ENABLED
    }


@app.post("/keywords", response_model=KeywordsResponse)
async def extract_keywords_api(request: EmbedRequest):
    """
    关键词提取接口（用于测试）
    返回提取的关键词，不进行向量化
    """
    if not request.text or not request.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty")

    original_text = request.text.strip()
    keywords = extract_keywords(original_text)
    keyword_list = keywords.split()

    return KeywordsResponse(
        original_text=original_text,
        keywords=keywords,
        keyword_list=keyword_list,
        enabled=KEYWORD_EXTRACT_ENABLED
    )


@app.post("/embed", response_model=EmbedResponse)
async def embed_text(request: EmbedRequest):
    """单个文本向量化"""
    if model is None:
        raise HTTPException(status_code=503, detail="Model not loaded")

    if not request.text or not request.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty")

    original_text = request.text.strip()
    keywords = None
    text_to_embed = original_text

    # 如果启用关键词提取，先提取关键词
    if KEYWORD_EXTRACT_ENABLED:
        keywords = extract_keywords(original_text)
        text_to_embed = keywords
        logger.info(f"关键词提取: '{original_text}' -> '{keywords}'")

    try:
        embedding = model.encode(text_to_embed, normalize_embeddings=True)
        return EmbedResponse(
            embedding=embedding.tolist(),
            dimension=len(embedding),
            model=EMBEDDING_MODEL,
            original_text=original_text,
            keywords=keywords
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
            model=EMBEDDING_MODEL
        )
    except Exception as e:
        logger.error(f"Batch embedding error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
