#!/usr/bin/env python3
"""
文档导入脚本 - 将 knowledge/ 目录下的文档导入到 Chroma
用法: uv run .claude/hooks/import_docs.py [目录路径]
"""

import json
import os
import sys
from pathlib import Path

import requests

# 配置
EMBEDDING_URL = os.getenv("EMBEDDING_URL", "http://localhost:8001")
CHROMA_URL = os.getenv("CHROMA_URL", "http://localhost:8000")
CHROMA_API_VERSION = os.getenv("CHROMA_API_VERSION", "v2")
COLLECTION_NAME = "knowledge"
CHUNK_SIZE = 500
CHUNK_OVERLAP = 50

# Chroma v2 API
API_BASE = f"{CHROMA_URL}/api/{CHROMA_API_VERSION}"
COLLECTION_BASE = f"{API_BASE}/tenants/default_tenant/databases/default_database/collections"


def get_embeddings_batch(texts: list[str]) -> list[list[float]]:
    """批量获取向量"""
    response = requests.post(
        f"{EMBEDDING_URL}/embed/batch",
        json={"texts": texts},
        timeout=120
    )
    response.raise_for_status()
    return response.json()["embeddings"]


def ensure_collection() -> str:
    """确保 collection 存在，返回 collection ID"""
    try:
        response = requests.get(f"{COLLECTION_BASE}", timeout=10)
        if response.status_code == 200:
            for col in response.json():
                if col.get("name") == COLLECTION_NAME:
                    print(f"✓ Collection 已存在: {COLLECTION_NAME} (id: {col['id']})")
                    return col["id"]
    except requests.RequestException:
        pass

    # 创建 collection
    response = requests.post(
        f"{COLLECTION_BASE}",
        json={"name": COLLECTION_NAME, "get_or_create": True},
        timeout=10
    )
    response.raise_for_status()
    col = response.json()
    print(f"✓ 创建 collection: {COLLECTION_NAME} (id: {col['id']})")
    return col["id"]


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """将文本分块"""
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start = end - overlap
    return chunks


def import_file(file_path: Path, collection_id: str) -> int:
    """导入单个文件，返回导入的块数"""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        print(f"  ✗ 读取失败: {e}")
        return 0

    chunks = chunk_text(content)
    if not chunks:
        return 0

    # 批量向量化
    print(f"  向量化 {len(chunks)} 个文本块...")
    embeddings = get_embeddings_batch(chunks)

    # 生成 IDs
    file_id = str(file_path).replace("/", "_").replace(".", "_")
    ids = [f"{file_id}_{i}" for i in range(len(chunks))]
    metadatas = [{"source": str(file_path)}] * len(chunks)

    # 写入 Chroma（v2 用 collection ID，使用 upsert 支持更新）
    response = requests.post(
        f"{COLLECTION_BASE}/{collection_id}/upsert",
        json={
            "ids": ids,
            "embeddings": embeddings,
            "documents": chunks,
            "metadatas": metadatas,
        },
        timeout=30
    )
    response.raise_for_status()

    return len(chunks)


def main():
    print("=" * 60)
    print("知识库文档导入工具")
    print("=" * 60)

    # 检查服务
    try:
        requests.get(f"{EMBEDDING_URL}/health", timeout=5).raise_for_status()
        print(f"✓ Embedding 服务正常: {EMBEDDING_URL}")
    except requests.RequestException:
        print(f"✗ Embedding 服务不可用: {EMBEDDING_URL}")
        sys.exit(1)

    try:
        requests.get(f"{CHROMA_URL}/api/{CHROMA_API_VERSION}/heartbeat", timeout=5).raise_for_status()
        print(f"✓ Chroma 服务正常: {CHROMA_URL}")
    except requests.RequestException:
        print(f"✗ Chroma 服务不可用: {CHROMA_URL}")
        sys.exit(1)

    # 确保 collection 存在
    collection_id = ensure_collection()

    # 获取目录
    dir_path = Path(sys.argv[1] if len(sys.argv) > 1 else "knowledge")
    if not dir_path.exists():
        print(f"✗ 目录不存在: {dir_path}")
        sys.exit(1)

    extensions = {".md", ".txt", ".py", ".json", ".yaml", ".yml"}
    total_chunks = 0
    file_count = 0

    for file_path in sorted(dir_path.rglob("*")):
        if file_path.is_file() and file_path.suffix.lower() in extensions:
            print(f"\n📄 {file_path}")
            try:
                chunks = import_file(file_path, collection_id)
                total_chunks += chunks
                file_count += 1
                print(f"  ✓ 导入 {chunks} 个文本块")
            except Exception as e:
                print(f"  ✗ 导入失败: {e}")

    print(f"\n{'='*60}")
    print(f"📊 导入完成: {file_count} 个文件, {total_chunks} 个文本块")


if __name__ == "__main__":
    main()
