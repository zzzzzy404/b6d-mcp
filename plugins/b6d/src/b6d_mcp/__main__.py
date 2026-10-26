"""命令行入口：b6d-mcp 启动 MCP 服务（stdio）；configure 保存 API Key；open-configure 打开终端窗口运行 configure。"""
import getpass
import sys

from b6d_mcp.config import codex_config_file, has_manual_codex_b6d_server, save_api_key

USAGE = """用法：b6d-mcp                 启动 MCP 服务
      b6d-mcp configure       保存 API Key
      b6d-mcp open-configure  打开终端窗口运行 configure"""


def configure() -> int:
    key = getpass.getpass("b6d API Key（在 b6d 网站「API 密钥」页面创建，输入时不显示）：")
    try:
        path = save_api_key(key)
    except ValueError as exc:
        print(f"未保存：{exc}", file=sys.stderr)
        return 1
    print(f"已保存到 {path}，可以关闭这个窗口，回到 Codex 继续")
    if has_manual_codex_b6d_server():
        print(
            f"注意：{codex_config_file()} 里有手动添加的 b6d MCP 服务，Codex 会因此跳过插件里的 b6d。"
            "请先运行 codex mcp remove b6d ，再重启 Codex。"
        )
    return 0


def open_configure() -> int:
    from b6d_mcp.terminal import configure_shell_command, open_configure_terminal

    if open_configure_terminal():
        print("已打开终端窗口，请在窗口里粘贴 b6d API Key")
        return 0
    print(f"没能打开终端窗口，请手动运行：{configure_shell_command()}", file=sys.stderr)
    return 1


def main() -> None:
    args = sys.argv[1:]
    if args == ["configure"]:
        sys.exit(configure())
    if args == ["open-configure"]:
        sys.exit(open_configure())
    if args:
        print(USAGE, file=sys.stderr)
        sys.exit(2)

    from b6d_mcp.server import main as serve

    serve()


if __name__ == "__main__":
    main()
