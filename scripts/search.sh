#!/bin/bash
# 检索 Hook - UserPromptSubmit 时触发
# 调用 embedding + chroma API 检索相关知识

set -euo pipefail

# 配置
EMBEDDING_URL="${EMBEDDING_URL:-http://localhost:8001}"
CHROMA_URL="${CHROMA_URL:-http://localhost:8000}"
CHROMA_API_VERSION="${CHROMA_API_VERSION:-v2}"
TOP_K="${RAG_TOP_K:-3}"
MAX_CONTENT_LENGTH="${RAG_MAX_CONTENT_LENGTH:-300}"
RERANK_ENABLED="${RERANK_ENABLED:-false}"
RERANK_CANDIDATES="${RERANK_CANDIDATES:-20}"
DISTANCE_THRESHOLD="${RAG_DISTANCE_THRESHOLD:-0.5}"

# 读取 stdin JSON
INPUT=$(cat)
PROMPT=$(echo "$INPUT" | jq -r '.prompt')

# 空查询跳过
if [ -z "$PROMPT" ] || [ "$PROMPT" = "null" ]; then
    exit 0
fi

# 1. 调用 embedding 服务获取向量
EMBEDDING_RESPONSE=$(curl -s --max-time 30 \
    -X POST "${EMBEDDING_URL}/embed" \
    -H "Content-Type: application/json" \
    -d "{\"text\": $(echo "$PROMPT" | jq -Rs .)}")

# 检查 embedding 是否成功
if echo "$EMBEDDING_RESPONSE" | jq -e '.embedding' > /dev/null 2>&1; then
    EMBEDDING=$(echo "$EMBEDDING_RESPONSE" | jq -c '.embedding')
else
    # embedding 失败，静默退出
    exit 0
fi

# 2. 确定检索数量
if [ "$RERANK_ENABLED" = "true" ]; then
    N_RESULTS="$RERANK_CANDIDATES"
else
    N_RESULTS="$TOP_K"
fi

# 3. 获取 collection ID
COLLECTION_BASE="${CHROMA_URL}/api/${CHROMA_API_VERSION}/tenants/default_tenant/databases/default_database/collections"
COLLECTION_ID=$(curl -s --max-time 10 \
    "${COLLECTION_BASE}" | jq -r '.[] | select(.name == "knowledge") | .id')

if [ -z "$COLLECTION_ID" ] || [ "$COLLECTION_ID" = "null" ]; then
    exit 0
fi

# 4. 调用 Chroma 检索（v2 API，用 collection ID），同时获取 distances
SEARCH_RESPONSE=$(curl -s --max-time 30 \
    -X POST "${COLLECTION_BASE}/${COLLECTION_ID}/query" \
    -H "Content-Type: application/json" \
    -d "{\"query_embeddings\": [$EMBEDDING], \"n_results\": $N_RESULTS, \"include\": [\"documents\", \"metadatas\", \"distances\"]}")

# 检查检索结果
if ! echo "$SEARCH_RESPONSE" | jq -e '.documents' > /dev/null 2>&1; then
    exit 0
fi

# 5. 如果启用重排，调用 reranker 服务
if [ "$RERANK_ENABLED" = "true" ] && [ -n "${RERANKER_URL:-}" ]; then
    DOCUMENTS=$(echo "$SEARCH_RESPONSE" | jq -c '.documents[0]')
    METADATAS=$(echo "$SEARCH_RESPONSE" | jq -c '.metadatas[0]')
    DISTANCES=$(echo "$SEARCH_RESPONSE" | jq -c '.distances[0]')

    RERANK_RESPONSE=$(curl -s --max-time 30 \
        -X POST "${RERANKER_URL}/rerank" \
        -H "Content-Type: application/json" \
        -d "{\"query\": $(echo "$PROMPT" | jq -Rs .), \"documents\": $DOCUMENTS, \"top_k\": $TOP_K}")

    # 合并重排结果与原始 metadata 和 distances
    if echo "$RERANK_RESPONSE" | jq -e '.results' > /dev/null 2>&1; then
        # 根据 index 匹配原始 metadata 和 distance，构建新的响应
        SEARCH_RESPONSE=$(echo "$RERANK_RESPONSE" "$METADATAS" "$DISTANCES" | jq -s '
            .[0] as $rerank |
            .[1] as $metas |
            .[2] as $dists |
            {
                results: [$rerank.results[] |
                    . as $r |
                    $metas[$r.index // 0] as $meta |
                    $dists[$r.index // 0] as $dist |
                    {
                        document: $r.document,
                        score: $r.score,
                        distance: $dist,
                        source: (if $meta.source then $meta.source else "未知" end),
                        index: $r.index
                    }
                ]
            }
        ')
    fi
fi

# 6. 格式化输出（带距离阈值过滤）
format_results() {
    local response="$1"
    local limit="$2"
    local max_len="$3"
    local threshold="$4"

    echo "$response" | jq -r --arg limit "$limit" --arg max_len "$max_len" --argjson threshold "$threshold" '
        if .results then
            # reranker 格式（包含 source, distance, score）
            .results[:($limit | tonumber)] | map(
                .document as $doc |
                .score as $score |
                .distance as $dist |
                .source as $src |
                (if ($doc | length) > ($max_len | tonumber) then ($doc[:($max_len | tonumber)] + "...") else $doc end) as $truncated |
                "[来源: " + $src + " | 距离: " + ($dist * 100 | round / 100 | tostring) + " | 相关度: " + ($score * 100 | round / 100 | tostring) + "]\n" + $truncated
            ) | join("\n\n---\n\n")
        else
            # chroma 格式 - 过滤距离超阈值的结果
            .documents[0] as $docs |
            .metadatas[0] as $metas |
            .distances[0] as $dists |
            [$docs, $metas, $dists] | transpose |
            map(select(.[2] < $threshold)) |
            .[:($limit | tonumber)] |
            map(
                .[0] as $doc |
                .[1] as $meta |
                .[2] as $dist |
                (if ($doc | length) > ($max_len | tonumber) then ($doc[:($max_len | tonumber)] + "...") else $doc end) as $truncated |
                "[来源: \($meta.source // "未知") | 距离: \($dist | . * 100 | round / 100 | tostring)]\n\($truncated)"
            ) | join("\n\n---\n\n")
        end
    '
}

RESULTS=$(format_results "$SEARCH_RESPONSE" "$TOP_K" "$MAX_CONTENT_LENGTH" "$DISTANCE_THRESHOLD")

# 7. 输出结果（JSON 格式，包含 systemMessage）
if [ -n "$RESULTS" ] && [ "$RESULTS" != "null" ]; then
    # 统计结果数量
    RESULT_COUNT=$(echo "$RESULTS" | grep -c "^\[来源:" || echo "0")

    # 构建完整上下文
    CONTEXT="📚 [知识库检索结果]
以下知识库内容可能与当前问题相关，可作为参考：

$RESULTS"

    # 提取简洁摘要：来源 + 相关度/距离（不含内容）
    SUMMARY=$(echo "$RESULTS" | grep "^\[来源:" | head -n "$TOP_K")

    # systemMessage 只展示文档名和相关性
    SYSTEM_MSG="📚 知识库检索完成，找到 ${RESULT_COUNT} 条相关结果：
${SUMMARY}"

    # 输出 JSON 格式（hookSpecificOutput 包裹 additionalContext）
    jq -n \
        --arg ctx "$CONTEXT" \
        --arg msg "$SYSTEM_MSG" \
        '{
            hookSpecificOutput: {
                hookEventName: "UserPromptSubmit",
                additionalContext: $ctx
            },
            systemMessage: $msg
        }'
fi

exit 0
