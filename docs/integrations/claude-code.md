# Claude Code 接入指南

通过 Claude Code 的 Hook 机制，在每次提问时自动检索知识库，将相关内容注入到 Claude 的上下文中。

## 配置

编辑项目根目录 `.claude/settings.json`：

```json
{
  "hooks": {
    "UserPromptSubmit": [{
      "hooks": [{
        "type": "command",
        "command": "cd \"$CLAUDE_PROJECT_DIR\" && uv run python -m light_rag search",
        "timeout": 60
      }]
    }]
  },
  "env": {
    "EMBEDDING_URL": "http://localhost:8001",
    "CHROMA_URL": "http://localhost:8000",
    "RERANK_ENABLED": "true",
    "RERANKER_URL": "http://localhost:8002",
    "RAG_TOP_K": "3",
    "RAG_MAX_CONTENT_LENGTH": "500",
    "RAG_DISTANCE_THRESHOLD": "1.2",
    "RERANK_SCORE_THRESHOLD": "0.1"
  }
}
```

## 工作原理

```
用户在 Claude Code 提问
  ↓
UserPromptSubmit Hook 触发
  ↓
uv run python -m light_rag search
  ↓
从 stdin 读取 {"prompt": "用户问题"}
  ↓
本地 jieba 关键词提取 → Embedding 向量化 → Chroma 检索 → Reranker 精排
  ↓
输出 JSON 到 stdout → Claude Code 自动注入上下文
```

## env 配置说明

| 变量 | 说明 |
|------|------|
| `EMBEDDING_URL` | Embedding 服务地址 |
| `CHROMA_URL` | Chroma 服务地址 |
| `RERANK_ENABLED` | 是否启用重排（需启动 reranker 容器） |
| `RERANKER_URL` | Reranker 服务地址 |
| `RAG_TOP_K` | 返回最大条数 |
| `RAG_MAX_CONTENT_LENGTH` | 每条结果最大字符数 |
| `RAG_DISTANCE_THRESHOLD` | 向量距离阈值（纯向量模式下过滤） |
| `RERANK_SCORE_THRESHOLD` | 重排分数阈值（Reranker 模式下过滤） |

## 验证

1. 确认 Docker 服务运行：`docker compose ps`
2. 确认已导入文档：`uv run python -m light_rag import knowledge/`
3. 手动测试 Hook：`echo '{"prompt":"test"}' | uv run python -m light_rag search`
4. 重启 Claude Code 会话使 Hook 生效

## 故障排除

### Hook 未触发

- 确认 `.claude/settings.json` 在项目根目录
- 确认 JSON 格式正确（无语法错误）
- 修改 settings.json 后需重启 Claude Code 会话

### 检索无结果

- 检查 Docker 服务健康：`curl localhost:8001/health` 和 `curl localhost:8000/api/v2/heartbeat`
- 检查知识库是否有数据：`curl -s http://localhost:8000/api/v2/tenants/default_tenant/databases/default_database/collections`
- 调大阈值（如 `RAG_DISTANCE_THRESHOLD=1.2`、`RERANK_SCORE_THRESHOLD=0.1`）

### 端口冲突

修改 `.env` 中的端口，同步修改 `.claude/settings.json` 中对应的 URL。
