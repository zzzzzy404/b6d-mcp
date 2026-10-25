"""命令行入口：b6d-mcp 启动 MCP 服务（stdio）；b6d-mcp configure 保存 API Key。"""
import getpass
import sys

from b6d_mcp.config import save_api_key


def configure() -> int:
    key = getpass.getpass("b6d API Key（在 b6d 网站「API 密钥」页面创建，输入时不显示）：")
    try:
        path = save_api_key(key)
    except ValueError as exc:
        print(f"未保存：{exc}", file=sys.stderr)
        return 1
    print(f"已保存到 {path}，重启 Codex 后生效")
    return 0


def main() -> None:
    args = sys.argv[1:]
    if args == ["configure"]:
        sys.exit(configure())
    if args:
        print("用法：b6d-mcp            启动 MCP 服务\n      b6d-mcp configure  保存 API Key", file=sys.stderr)
        sys.exit(2)

    from b6d_mcp.server import main as serve

    serve()


if __name__ == "__main__":
    main()
