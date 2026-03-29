"""
Light-RAG CLI 入口

用法:
  uv run python -m light_rag search          # 从 stdin 读取 JSON 执行检索
  uv run python -m light_rag import [dir]     # 导入文档到知识库
"""

import sys


def main():
    if len(sys.argv) < 2:
        print("用法: python -m light_rag <search|import> [args]")
        sys.exit(1)

    command = sys.argv[1]

    if command == "search":
        from .search import main as search_main
        search_main()
    elif command == "import":
        from .importer import main as import_main
        dir_path = sys.argv[2] if len(sys.argv) > 2 else "knowledge"
        import_main(dir_path)
    else:
        print(f"未知命令: {command}")
        print("可用命令: search, import")
        sys.exit(1)


if __name__ == "__main__":
    main()
