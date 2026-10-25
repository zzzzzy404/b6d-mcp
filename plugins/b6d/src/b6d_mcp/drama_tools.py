"""短剧工作台只读预览：项目、分集、分集画布镜头清单 + 缩略图 + 画布链接。"""
from typing import Annotated, Any

from mcp.server.mcpserver import Image, MCPServer
from mcp.types import ToolAnnotations
from pydantic import Field

from b6d_mcp.api import B6dApi, B6dApiError, path_id

READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=True)
DEFAULT_THUMBNAILS = 6
MAX_THUMBNAILS = 20
MAX_THUMBNAIL_BYTES = 2 * 1024 * 1024


def _caption(node: dict) -> str:
    shot = node.get("shot") or {}
    where = "-".join(str(shot[key]) for key in ("scene", "shot") if shot.get(key))
    name = node.get("label") or node["node_id"]
    return f"缩略图：{name}" + (f"（{where}）" if where else "") + f"，{node.get('status')}"


async def _thumbnails(api: B6dApi, nodes: list[dict], limit: int) -> tuple[list[str | Image], list[str]]:
    """按清单顺序取前 limit 张缩略图，每张前面放一行说明是哪个镜头。取不到的只记下来，不让整个预览失败。"""
    blocks: list[str | Image] = []
    failed: list[str] = []
    fetched = 0
    for node in nodes:
        if fetched >= limit:
            break
        url = node.get("thumbnail_url")
        if not url:
            continue
        try:
            data, fmt = await api.fetch_image(url, MAX_THUMBNAIL_BYTES)
        except B6dApiError:
            failed.append(node.get("label") or node["node_id"])
            continue
        blocks += [_caption(node), Image(data=data, format=fmt)]
        fetched += 1
    return blocks, failed


def register_drama_tools(server: MCPServer, api: B6dApi) -> None:
    @server.tool(annotations=READ_ONLY)
    async def list_drama_projects(
        page: Annotated[int, Field(ge=1)] = 1,
        page_size: Annotated[int, Field(ge=1, le=100)] = 20,
    ) -> dict[str, Any]:
        """列出短剧工作台里的短剧项目，最近更新的在前。web_url 是项目页面链接。"""
        return await api.get("/api/drama/projects", params={"page": page, "page_size": page_size})

    @server.tool(annotations=READ_ONLY)
    async def list_drama_episodes(
        project_id: Annotated[str, Field(description="短剧项目 id，见 list_drama_projects")],
    ) -> dict[str, Any]:
        """列出短剧项目的分集，按集数排序。每集的 id 用于 preview_episode，web_url 是该集的工作台画布链接。"""
        return await api.get(f"/api/drama/projects/{path_id(project_id)}/episodes")

    @server.tool(annotations=READ_ONLY)
    async def preview_episode(
        episode_id: Annotated[str, Field(description="分集画布 id，见 list_drama_episodes")],
        thumbnails: Annotated[
            int,
            Field(ge=0, le=MAX_THUMBNAILS, description="按镜头顺序附带几张缩略图，0 表示只要文字清单"),
        ] = DEFAULT_THUMBNAILS,
    ) -> list[dict[str, Any] | str | Image]:
        """预览一集的工作台画布：镜头清单（场次镜号、台词、提示词摘要、模型、生成状态、失败原因）、
        状态统计、缩略图，以及工作台画布链接 canvas_url。回复用户时请附上 canvas_url。
        media_url / thumbnail_url 是签名链接，约 2 小时有效。"""
        result = await api.get(f"/api/drama/episodes/{path_id(episode_id)}/preview")
        nodes = result.get("nodes", [])
        summary = {"canvas_url": result.get("episode", {}).get("web_url"), **result}
        if not thumbnails:
            return [summary]

        blocks, failed = await _thumbnails(api, nodes, thumbnails)
        if failed:
            summary["thumbnail_errors"] = failed
        return [summary, *blocks]
