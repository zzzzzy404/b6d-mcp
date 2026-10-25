"""生成相关工具：提交视频/图片任务、查询和等待任务。"""
import time
from pathlib import Path
from typing import Annotated, Any, Literal, Optional

import anyio
from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations
from pydantic import Field

from b6d_mcp.api import B6dApi, B6dApiError, path_id

SEEDANCE_25_MODEL = "doubao-seedance-2-5-260628"
FINISHED_STATUSES = frozenset({"succeeded", "failed", "cancelled"})
# 中文注释：Codex 默认工具超时 300 秒，留出余量
DEFAULT_WAIT_SECONDS = 240
MAX_WAIT_SECONDS = 1800

READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=True)
SPENDS_CREDITS = ToolAnnotations(read_only_hint=False, destructive_hint=False, open_world_hint=True)

MediaUrls = Annotated[
    Optional[list[str]],
    Field(description="upload_media 返回的 url，或素材的 asset://<素材 id>。不接受随意的外部链接"),
]


def summarize_task(task: dict) -> dict:
    """只留模型用得上的字段。图片优先给原图，列表里的 result_image_urls 是缩略图。"""
    image_urls = task.get("result_image_download_urls") or task.get("result_image_urls") or []
    summary = {
        "id": task.get("id"),
        "status": task.get("status"),
        "task_type": task.get("task_type"),
        "model_id": task.get("model_id"),
        "prompt_text": task.get("prompt_text"),
        "credits_estimated": task.get("credits_estimated"),
        "credits_actual": task.get("credits_actual"),
        "video_url": task.get("stored_video_url"),
        "thumbnail_url": task.get("thumbnail_url"),
        "image_urls": image_urls,
        "audio_urls": task.get("result_audio_urls") or [],
        "error_message": task.get("error_message"),
        "draft": task.get("draft"),
        "created_at": task.get("created_at"),
        "completed_at": task.get("completed_at"),
    }
    return {key: value for key, value in summary.items() if value not in (None, [])}


def _media_items(kind: str, urls: Optional[list[str]]) -> list[dict]:
    return [{"type": kind, kind: {"url": url}} for url in urls or []]


def _file_extension(url: str, default: str) -> str:
    suffix = Path(url.split("?", 1)[0]).suffix.lower()
    return suffix if 1 < len(suffix) <= 5 else default


async def _download_results(api: B6dApi, task: dict, directory: Path) -> list[str]:
    directory.mkdir(parents=True, exist_ok=True)
    prefix = str(task["id"])[:8]
    targets: list[tuple[str, str]] = []
    if task.get("video_url"):
        targets.append((task["video_url"], f"{prefix}_video{_file_extension(task['video_url'], '.mp4')}"))
    for index, url in enumerate(task.get("image_urls", []), start=1):
        targets.append((url, f"{prefix}_image_{index}{_file_extension(url, '.png')}"))
    for index, url in enumerate(task.get("audio_urls", []), start=1):
        targets.append((url, f"{prefix}_audio_{index}{_file_extension(url, '.mp3')}"))
    saved = [await api.download(url, directory / name) for url, name in targets]
    return [str(path) for path in saved]


def register_generation_tools(server: MCPServer, api: B6dApi, poll_interval: float) -> None:
    @server.tool(annotations=SPENDS_CREDITS)
    async def generate_video(
        prompt: Annotated[Optional[str], Field(description="视频描述。用 draft_task_id 生成正式视频时可以不传")] = None,
        model: Annotated[Optional[str], Field(description="视频模型 key，可用值见 list_models。不传用账号默认模型")] = None,
        duration: Annotated[int, Field(ge=-1, le=30, description="时长（秒），-1 为智能时长")] = 5,
        resolution: Annotated[Literal["480p", "720p", "1080p"], Field(description="分辨率")] = "720p",
        ratio: Annotated[
            str, Field(description="画面比例：16:9、9:16、1:1、4:3、3:4、21:9、adaptive。首尾帧模式只能 adaptive")
        ] = "16:9",
        mode: Annotated[
            Literal["reference", "first_last_frame"],
            Field(description="reference：图片作为参考；first_last_frame：第 1 张图是首帧，第 2 张是尾帧"),
        ] = "reference",
        image_urls: MediaUrls = None,
        video_urls: MediaUrls = None,
        audio_urls: MediaUrls = None,
        generate_audio: Annotated[bool, Field(description="是否同时生成声音")] = True,
        draft: Annotated[bool, Field(description="Seedance 2.5 样片，固定 480p，便宜，用来先看效果")] = False,
        draft_task_id: Annotated[
            Optional[str], Field(description="已成功的样片任务 id。传入后生成 1080p 正式视频，其余参数沿用样片")
        ] = None,
    ) -> dict[str, Any]:
        """提交视频生成任务，会消耗积分，立即返回任务 id。视频通常要 2-5 分钟，用 wait_task 等结果。
        参考图、参考视频、参考音频先用 upload_media 上传，再把返回的 url 传进来。"""
        if draft and draft_task_id:
            raise B6dApiError("draft 和 draft_task_id 不能同时传")
        if not prompt and not draft_task_id:
            raise B6dApiError("需要 prompt（只有用 draft_task_id 生成正式视频时可以省略）")

        payload: dict[str, Any] = {
            "duration": duration,
            "resolution": "480p" if draft else resolution,
            "ratio": ratio,
            "mode": mode,
            "generate_audio": generate_audio,
        }
        content = [{"type": "text", "text": prompt}] if prompt else []
        content += _media_items("image_url", image_urls)
        content += _media_items("video_url", video_urls)
        content += _media_items("audio_url", audio_urls)
        if content:
            payload["content"] = content
        if model or draft or draft_task_id:
            payload["video_model"] = model or SEEDANCE_25_MODEL
        if draft:
            payload["draft"] = True
        if draft_task_id:
            payload["draft_task_id"] = draft_task_id
        return summarize_task(await api.post("/api/generation/tasks", json=payload))

    @server.tool(annotations=SPENDS_CREDITS)
    async def generate_image(
        prompt: Annotated[str, Field(min_length=1, max_length=2000, description="图片描述")],
        model: Annotated[Optional[str], Field(description="图片模型 key，可用值见 list_models。不传用服务端默认")] = None,
        size: Annotated[str, Field(description="画面比例：1:1、16:9、9:16、4:3、3:4 等")] = "1:1",
        resolution: Annotated[str, Field(description="分辨率：1K、2K、3K、4K，取决于模型")] = "2K",
        n: Annotated[int, Field(ge=1, le=4, description="生成张数")] = 1,
        image_urls: MediaUrls = None,
        quality: Annotated[Optional[str], Field(description="画质档，仅 GPT Image 系列使用")] = None,
    ) -> dict[str, Any]:
        """提交图片生成任务，会消耗积分，立即返回任务 id。图片通常 10-30 秒完成，用 wait_task 等结果。"""
        payload: dict[str, Any] = {"prompt": prompt, "size": size, "resolution": resolution, "n": n}
        if model:
            payload["image_model"] = model
        if image_urls:
            payload["image_urls"] = image_urls
        if quality:
            payload["quality"] = quality
        return summarize_task(await api.post("/api/generation/image-tasks", json=payload))

    @server.tool(annotations=READ_ONLY)
    async def get_task(task_id: Annotated[str, Field(description="任务 id")]) -> dict[str, Any]:
        """查询一个任务的状态和结果链接。结果链接是签名 URL，约 2 小时内有效。"""
        return summarize_task(await api.get(f"/api/generation/tasks/{path_id(task_id)}"))

    @server.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False, open_world_hint=True))
    async def wait_task(
        task_id: Annotated[str, Field(description="任务 id")],
        timeout_seconds: Annotated[
            int, Field(ge=1, le=MAX_WAIT_SECONDS, description="最多等多少秒。到时还没完成会返回当前状态，可以再调一次")
        ] = DEFAULT_WAIT_SECONDS,
        download_dir: Annotated[
            Optional[str], Field(description="成功后把结果下载到这个本地目录（建议绝对路径）。不传则只返回链接")
        ] = None,
    ) -> dict[str, Any]:
        """等待任务完成并返回结果；finished=false 表示还在处理中。可选把成片下载到本地。"""
        deadline = time.monotonic() + timeout_seconds
        while True:
            task = summarize_task(await api.get(f"/api/generation/tasks/{path_id(task_id)}"))
            finished = task.get("status") in FINISHED_STATUSES
            if finished or time.monotonic() >= deadline:
                break
            await anyio.sleep(poll_interval)

        result = {**task, "finished": finished}
        if download_dir and task.get("status") == "succeeded":
            target = Path(download_dir).expanduser().resolve()
            result["downloaded_files"] = await _download_results(api, task, target)
        return result

    @server.tool(annotations=READ_ONLY)
    async def list_tasks(
        status: Annotated[
            Optional[Literal["queued", "processing", "succeeded", "failed"]], Field(description="按状态过滤")
        ] = None,
        task_type: Annotated[Optional[Literal["video", "image"]], Field(description="按类型过滤")] = None,
        page: Annotated[int, Field(ge=1)] = 1,
        page_size: Annotated[int, Field(ge=1, le=100)] = 20,
    ) -> dict[str, Any]:
        """列出最近的生成任务，新的在前。"""
        result = await api.get(
            "/api/generation/tasks",
            params={"task_status": status, "task_type": task_type, "page": page, "page_size": page_size},
        )
        return {
            "items": [summarize_task(item) for item in result.get("items", [])],
            "total": result.get("total", 0),
            "page": page,
        }
