"""
检索编排模块 - 替代 scripts/search.sh
从 stdin 读取用户问题，执行检索并输出 JSON 结果
"""

import json
import sys

import requests

from .config import (
    CHROMA_COLLECTION_BASE,
    COLLECTION_NAME,
    EMBEDDING_URL,
    KEYWORD_EXTRACT_ENABLED,
    RAG_DISTANCE_THRESHOLD,
    RAG_MAX_CONTENT_LENGTH,
    RAG_TOP_K,
    RERANK_CANDIDATES,
    RERANK_ENABLED,
    RERANK_SCORE_THRESHOLD,
    RERANKER_URL,
)
from .keywords import extract_keywords


def get_embedding(text: str) -> tuple[list[float], str | None]:
    """
    调用 Embedding 服务获取文本向量。
    返回 (embedding, keywords)。
    """
    keywords = None
    text_to_embed = text

    # 本地关键词提取（如果启用）
    if KEYWORD_EXTRACT_ENABLED:
        keywords = extract_keywords(text)
        text_to_embed = keywords

    response = requests.post(
        f"{EMBEDDING_URL}/embed",
        json={"text": text_to_embed},
        timeout=30,
    )
    response.raise_for_status()
    embedding = response.json()["embedding"]
    return embedding, keywords


def get_collection_id() -> str | None:
    """获取 knowledge collection ID"""
    try:
        response = requests.get(CHROMA_COLLECTION_BASE, timeout=10)
        if response.status_code == 200:
            for col in response.json():
                if col.get("name") == COLLECTION_NAME:
                    return col["id"]
    except requests.RequestException:
        pass
    return None


def search_chroma_by_id(
    collection_id: str, embedding: list[float], n_results: int
) -> dict | None:
    """在 Chroma 中使用 collection ID 执行向量检索"""
    try:
        response = requests.post(
            f"{CHROMA_COLLECTION_BASE}/{collection_id}/query",
            json={
                "query_embeddings": [embedding],
                "n_results": n_results,
                "include": ["documents", "metadatas", "distances"],
            },
            timeout=30,
        )
        response.raise_for_status()
        return response.json()
    except Exception:
        return None


def rerank(query: str, documents: list[str], top_k: int) -> list[dict] | None:
    """调用 Reranker 服务进行精排"""
    try:
        response = requests.post(
            f"{RERANKER_URL}/rerank",
            json={"query": query, "documents": documents, "top_k": top_k},
            timeout=30,
        )
        response.raise_for_status()
        return response.json().get("results")
    except Exception:
        return None


def format_results(
    search_data: dict,
    rerank_results: list[dict] | None,
    top_k: int,
    max_length: int,
    distance_threshold: float,
    score_threshold: float,
) -> tuple[str, int]:
    """
    格式化检索结果，返回 (格式化文本, 结果数量)。
    """
    if rerank_results is not None:
        # Reranker 模式：按相关性分数过滤
        metas = search_data.get("metadatas", [[]])[0]
        dists = search_data.get("distances", [[]])[0]

        filtered = []
        for r in rerank_results[:top_k]:
            if r["score"] < score_threshold:
                continue
            idx = r.get("index", 0)
            doc = r["document"]
            score = r["score"]
            dist = dists[idx] if idx < len(dists) else 0
            source = metas[idx].get("source", "未知") if idx < len(metas) else "未知"

            if len(doc) > max_length:
                doc = doc[:max_length] + "..."

            filtered.append(
                f"[来源: {source} | 距离: {round(dist * 100) / 100} | 相关度: {round(score * 100) / 100}]\n{doc}"
            )

        if not filtered:
            return "", 0
        return "\n\n---\n\n".join(filtered), len(filtered)
    else:
        # 纯向量模式：按距离过滤
        docs = search_data.get("documents", [[]])[0]
        metas = search_data.get("metadatas", [[]])[0]
        dists = search_data.get("distances", [[]])[0]

        filtered = []
        for i, (doc, meta, dist) in enumerate(zip(docs, metas, dists)):
            if dist >= distance_threshold:
                continue
            if len(doc) > max_length:
                doc = doc[:max_length] + "..."
            source = meta.get("source", "未知")
            filtered.append(
                f"[来源: {source} | 距离: {round(dist * 100) / 100}]\n{doc}"
            )
            if len(filtered) >= top_k:
                break

        if not filtered:
            return "", 0
        return "\n\n---\n\n".join(filtered), len(filtered)


def run_search(prompt: str) -> str | None:
    """
    执行完整的检索流程，返回 JSON 字符串或 None。
    """
    if not prompt or not prompt.strip():
        return None

    prompt = prompt.strip()

    # 1. 获取 Embedding
    try:
        embedding, keywords = get_embedding(prompt)
    except Exception:
        return None

    # 2. 获取 Collection ID
    collection_id = get_collection_id()
    if not collection_id:
        return None

    # 3. 确定检索数量
    n_results = RERANK_CANDIDATES if RERANK_ENABLED else RAG_TOP_K

    # 4. Chroma 检索
    search_data = search_chroma_by_id(collection_id, embedding, n_results)
    if not search_data or not search_data.get("documents"):
        return None

    # 5. Reranker 精排（如果启用）
    rerank_results = None
    if RERANK_ENABLED and RERANKER_URL:
        documents = search_data.get("documents", [[]])[0]
        if documents:
            rerank_results = rerank(prompt, documents, RAG_TOP_K)

    # 6. 格式化结果
    results_text, result_count = format_results(
        search_data,
        rerank_results,
        RAG_TOP_K,
        RAG_MAX_CONTENT_LENGTH,
        RAG_DISTANCE_THRESHOLD,
        RERANK_SCORE_THRESHOLD,
    )

    if not results_text:
        return None

    # 7. 构建 JSON 输出
    context = f"📚 [知识库检索结果]\n以下知识库内容可能与当前问题相关，可作为参考：\n\n{results_text}"

    # 构建摘要
    summary_lines = []
    if rerank_results is not None:
        metas = search_data.get("metadatas", [[]])[0]
        dists = search_data.get("distances", [[]])[0]
        for r in rerank_results[:RAG_TOP_K]:
            if r["score"] < RERANK_SCORE_THRESHOLD:
                continue
            idx = r.get("index", 0)
            source = metas[idx].get("source", "未知") if idx < len(metas) else "未知"
            dist = dists[idx] if idx < len(dists) else 0
            summary_lines.append(
                f"[来源: {source} | 距离: {round(dist * 100) / 100} | 相关度: {round(r['score'] * 100) / 100}]"
            )
    else:
        docs = search_data.get("documents", [[]])[0]
        metas = search_data.get("metadatas", [[]])[0]
        dists = search_data.get("distances", [[]])[0]
        for i, (doc, meta, dist) in enumerate(zip(docs, metas, dists)):
            if dist >= RAG_DISTANCE_THRESHOLD:
                continue
            source = meta.get("source", "未知")
            summary_lines.append(
                f"[来源: {source} | 距离: {round(dist * 100) / 100}]"
            )
            if len(summary_lines) >= RAG_TOP_K:
                break

    summary = "\n".join(summary_lines)

    # 关键词提示
    keyword_msg = ""
    if keywords:
        keyword_msg = f"🔍 关键词: {keywords}\n"

    system_msg = f"📚 知识库检索完成，找到 {result_count} 条相关结果：\n{keyword_msg}{summary}"

    output = {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": context,
        },
        "systemMessage": system_msg,
    }

    return json.dumps(output, ensure_ascii=False)


def main():
    """从 stdin 读取 JSON，执行检索，输出结果"""
    try:
        input_data = json.loads(sys.stdin.read())
        prompt = input_data.get("prompt", "")
    except (json.JSONDecodeError, EOFError):
        return

    result = run_search(prompt)
    if result:
        print(result)
