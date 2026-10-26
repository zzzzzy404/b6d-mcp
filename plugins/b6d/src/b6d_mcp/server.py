"""b6d MCP 服务入口：把对外 API 包装成 Codex 等 Agent 可直接调用的工具。"""
from importlib.metadata import PackageNotFoundError, version
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from b6d_mcp import terminal
from b6d_mcp.api import B6dApi
from b6d_mcp.config import configure_command
from b6d_mcp.drama_tools import register_drama_tools
from b6d_mcp.generation_tools import register_generation_tools
from b6d_mcp.media_tools import register_media_tools

DEFAULT_POLL_INTERVAL_SECONDS = 5.0

INSTRUCTIONS = """b6d 是 AI 图片/视频生成服务。
- 提示未配置 API Key 时，调用 setup_api_key 打开终端让用户粘贴 Key，不要让用户把 Key 发到对话里。
- 生成任务是异步的：generate_video / generate_image 立即返回任务 id，再用 wait_task 等结果。
- 参考素材先用 upload_media 上传本地文件，或用 search_media / list_media 找已有素材，把 url 传给生成工具。
- 生成会消耗积分。批量提交、长视频或 1080p 之前，先告诉用户预计数量并确认；可用 get_balance 查余额。
- 模型 key 用 list_models 查，不要猜。
- 结果链接是有时效的签名 URL，需要长期保存时用 wait_task 的 download_dir 下载，或 save_task_to_library 存进素材库。
- 查看短剧工作台：list_drama_projects → list_drama_episodes → preview_episode。给用户汇报某一集时附上 canvas_url，方便打开工作台画布。"""


def _package_version() -> str:
    try:
        return version("b6d-mcp")
    except PackageNotFoundError:
        return "0.0.0"


READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=True)


def _register_account_tools(server: MCPServer, api: B6dApi) -> None:
    @server.tool(annotations=READ_ONLY)
    async def list_models() -> dict[str, Any]:
        """列出当前 API Key 可以使用的图片/视频模型 key。"""
        return await api.get("/api/account/model-offering")

    @server.tool(annotations=ToolAnnotations(read_only_hint=False, open_world_hint=False))
    async def setup_api_key() -> str:
        """打开一个终端窗口，让用户粘贴 b6d API Key 并保存到本机。Key 不经过对话。"""
        if terminal.open_configure_terminal():
            return (
                "已打开终端窗口。请用户在 b6d 网站「API 密钥」页面创建 Key（查看短剧工作台需勾选 canvas:read），"
                "粘贴到终端里回车。看到「已保存」后回到这里继续，不用重启。"
            )
        return f"没能自动打开终端。请让用户自己打开终端运行：{configure_command()}"

    @server.tool(annotations=READ_ONLY)
    async def get_balance() -> dict[str, Any]:
        """查询积分余额。available 是可用积分，frozen 是进行中任务预扣的积分。"""
        return await api.get("/api/account/balance")


def build_server(api: B6dApi, poll_interval: float = DEFAULT_POLL_INTERVAL_SECONDS) -> MCPServer:
    server = MCPServer(name="b6d", version=_package_version(), instructions=INSTRUCTIONS)
    register_generation_tools(server, api, poll_interval)
    register_media_tools(server, api)
    register_drama_tools(server, api)
    _register_account_tools(server, api)
    return server


def main() -> None:
    build_server(B6dApi.from_config()).run("stdio")
