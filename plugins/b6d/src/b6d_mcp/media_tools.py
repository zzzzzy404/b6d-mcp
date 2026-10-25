"""素材管理工具：上传、列表、搜索、改名、移动、删除、文件夹、保存生成结果。"""
from pathlib import Path
from typing import Annotated, Any, Literal, Optional

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations
from pydantic import Field

from b6d_mcp.api import B6dApi, path_id

READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=True)
WRITES = ToolAnnotations(read_only_hint=False, destructive_hint=False, open_world_hint=True)
DESTRUCTIVE = ToolAnnotations(read_only_hint=False, destructive_hint=True, open_world_hint=True)

FolderId = Annotated[Optional[str], Field(description="文件夹 id，见 list_folders。不传表示根目录")]


def register_media_tools(server: MCPServer, api: B6dApi) -> None:
    @server.tool(annotations=WRITES)
    async def upload_media(
        file_path: Annotated[str, Field(description="本地文件路径，建议绝对路径。图片 JPG/PNG、视频 MP4/MOV、音频 MP3/WAV，最大 100MB")],
        folder_id: FolderId = None,
    ) -> dict[str, Any]:
        """把本地文件上传到素材库。返回的 url 可以直接作为 generate_video / generate_image 的参考素材。"""
        path = Path(file_path).expanduser().resolve()
        return await api.upload(path, folder_id=folder_id)

    @server.tool(annotations=READ_ONLY)
    async def list_media(
        file_type: Annotated[Optional[Literal["image", "video", "audio"]], Field(description="按类型过滤")] = None,
        folder_id: Annotated[Optional[str], Field(description="只看这个文件夹里的素材")] = None,
        root_only: Annotated[bool, Field(description="只看没有放进文件夹的素材")] = False,
        page: Annotated[int, Field(ge=1)] = 1,
        page_size: Annotated[int, Field(ge=1, le=100)] = 30,
    ) -> dict[str, Any]:
        """列出素材库里的素材，新的在前。"""
        return await api.get(
            "/api/generation/media",
            params={
                "file_type": file_type,
                "folder_id": folder_id,
                "root_only": "true" if root_only else None,
                "page": page,
                "page_size": page_size,
            },
        )

    @server.tool(annotations=READ_ONLY)
    async def search_media(
        query: Annotated[str, Field(description="按名称搜索的关键词")],
        source: Annotated[
            Literal["all", "media", "model"], Field(description="media：素材库；model：人像资产；all：都搜")
        ] = "all",
        page: Annotated[int, Field(ge=1)] = 1,
        page_size: Annotated[int, Field(ge=1, le=100)] = 20,
    ) -> dict[str, Any]:
        """按关键词搜索素材和人像资产。结果里的 api_url 可以直接作为生成任务的参考素材。"""
        return await api.get(
            "/api/generation/assets/search",
            params={"q": query, "source": source, "page": page, "page_size": page_size},
        )

    @server.tool(annotations=WRITES)
    async def rename_media(
        asset_id: Annotated[str, Field(description="素材 id")],
        name: Annotated[str, Field(min_length=1, max_length=200, description="新名称")],
    ) -> dict[str, Any]:
        """重命名素材。"""
        return await api.patch(f"/api/generation/media/{path_id(asset_id)}", json={"name": name})

    @server.tool(annotations=WRITES)
    async def move_media(
        asset_id: Annotated[str, Field(description="素材 id")],
        folder_id: Annotated[Optional[str], Field(description="目标文件夹 id。不传表示移回根目录")] = None,
    ) -> dict[str, Any]:
        """把素材移到另一个文件夹，或移回根目录。"""
        return await api.patch(
            f"/api/generation/media/{path_id(asset_id)}", json={"move": True, "folder_id": folder_id}
        )

    @server.tool(annotations=DESTRUCTIVE)
    async def delete_media(asset_id: Annotated[str, Field(description="素材 id")]) -> dict[str, Any]:
        """永久删除素材，文件和记录都会删掉，不能恢复。删除前请先和用户确认。"""
        return await api.delete(f"/api/generation/media/{path_id(asset_id)}")

    @server.tool(annotations=WRITES)
    async def save_task_to_library(task_id: Annotated[str, Field(description="已成功的任务 id")]) -> dict[str, Any]:
        """把生成成功的视频或图片保存到素材库，方便以后引用。"""
        return await api.post(f"/api/generation/tasks/{path_id(task_id)}/save-to-library")

    @server.tool(annotations=READ_ONLY)
    async def list_folders() -> dict[str, Any]:
        """列出素材库的文件夹和每个文件夹里的素材数量。"""
        return await api.get("/api/generation/folders")

    @server.tool(annotations=WRITES)
    async def create_folder(
        name: Annotated[str, Field(min_length=1, max_length=200, description="文件夹名称")],
        parent_id: Annotated[Optional[str], Field(description="上级文件夹 id，不传则建在根目录")] = None,
        category: Annotated[Optional[str], Field(description="文件夹分类标签，例如 角色、场景、道具")] = None,
    ) -> dict[str, Any]:
        """新建素材文件夹。"""
        payload: dict[str, Any] = {"name": name}
        if parent_id:
            payload["parent_id"] = parent_id
        if category:
            payload["category"] = category
        return await api.post("/api/generation/folders", json=payload)
