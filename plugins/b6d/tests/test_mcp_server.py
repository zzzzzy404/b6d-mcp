"""b6d MCP 服务测试：用 httpx.MockTransport 假装对外 API，用内存 MCP Client 调工具。"""
import json
from pathlib import Path

import httpx
import pytest

pytest.importorskip("mcp")

from mcp.client import Client  # noqa: E402

from b6d_mcp.api import B6dApi  # noqa: E402
from b6d_mcp.server import build_server  # noqa: E402

ENDPOINT = "https://api.example.test"
API_KEY = "sk-test"


class FakeBackend:
    """按 (method, path) 返回预置响应，并记录收到的请求。"""

    def __init__(self, routes: dict):
        self.routes = routes
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        key = (request.method, request.url.path)
        route = self.routes.get(key)
        if route is None:
            return httpx.Response(404, json={"detail": f"no route {key}"})
        if callable(route):
            return route(request)
        status, body = route
        if isinstance(body, bytes):
            return httpx.Response(status, content=body)
        return httpx.Response(status, json=body)

    def last(self, method: str, path: str) -> httpx.Request:
        matches = [r for r in self.requests if r.method == method and r.url.path == path]
        assert matches, f"没有收到 {method} {path}"
        return matches[-1]


def make_server(routes: dict, api_key: str = API_KEY):
    backend = FakeBackend(routes)
    api = B6dApi(endpoint=ENDPOINT, api_key=api_key, transport=httpx.MockTransport(backend))
    return build_server(api, poll_interval=0), backend


async def call(server, name: str, arguments: dict | None = None):
    async with Client(server) as client:
        return await client.call_tool(name, arguments or {})


def text_of(result) -> str:
    return "".join(getattr(item, "text", "") for item in result.content)


@pytest.fixture
def anyio_backend():
    return "asyncio"


SUCCEEDED_VIDEO = {
    "id": "t-video",
    "status": "succeeded",
    "task_type": "video",
    "model_id": "doubao-seedance-2-5-260628",
    "prompt_text": "橘猫",
    "credits_estimated": 100.0,
    "credits_actual": 98.0,
    "stored_video_url": f"{ENDPOINT}/files/video.mp4",
    "thumbnail_url": f"{ENDPOINT}/files/thumb.jpg",
}

SUCCEEDED_IMAGE = {
    "id": "t-image",
    "status": "succeeded",
    "task_type": "image",
    "model_id": "doubao-seedream-5-0-260128",
    "result_image_urls": [f"{ENDPOINT}/files/thumb1.jpg"],
    "result_image_download_urls": [f"{ENDPOINT}/files/original1.png"],
}


@pytest.mark.anyio
async def test_lists_expected_tools():
    server, _ = make_server({})
    async with Client(server) as client:
        tools = {tool.name for tool in (await client.list_tools()).tools}
    assert tools == {
        "generate_video",
        "generate_image",
        "get_task",
        "wait_task",
        "list_tasks",
        "upload_media",
        "list_media",
        "search_media",
        "rename_media",
        "move_media",
        "delete_media",
        "save_task_to_library",
        "list_folders",
        "create_folder",
        "list_models",
        "get_balance",
        "setup_api_key",
        "list_drama_projects",
        "list_drama_episodes",
        "preview_episode",
    }


@pytest.mark.anyio
async def test_generate_video_builds_content_with_references():
    server, backend = make_server(
        {("POST", "/api/generation/tasks"): (200, {"id": "t1", "status": "queued", "credits_estimated": 50.0})}
    )

    result = await call(
        server,
        "generate_video",
        {
            "prompt": "让人物挥手",
            "model": "doubao-seedance-2-5-260628",
            "image_urls": ["asset://a1"],
            "audio_urls": ["https://x/a.mp3"],
            "duration": 8,
            "ratio": "9:16",
        },
    )

    assert not result.is_error, text_of(result)
    request = backend.last("POST", "/api/generation/tasks")
    assert request.headers["authorization"] == f"Bearer {API_KEY}"
    body = json.loads(request.content)
    assert body["video_model"] == "doubao-seedance-2-5-260628"
    assert body["duration"] == 8
    assert body["ratio"] == "9:16"
    assert body["mode"] == "reference"
    assert body["content"] == [
        {"type": "text", "text": "让人物挥手"},
        {"type": "image_url", "image_url": {"url": "asset://a1"}},
        {"type": "audio_url", "audio_url": {"url": "https://x/a.mp3"}},
    ]
    assert result.structured_content["id"] == "t1"


@pytest.mark.anyio
async def test_generate_video_from_draft_does_not_need_prompt():
    server, backend = make_server(
        {("POST", "/api/generation/tasks"): (200, {"id": "t2", "status": "queued"})}
    )

    result = await call(server, "generate_video", {"draft_task_id": "draft-1"})

    assert not result.is_error, text_of(result)
    body = json.loads(backend.last("POST", "/api/generation/tasks").content)
    assert body["draft_task_id"] == "draft-1"
    assert body["video_model"] == "doubao-seedance-2-5-260628"
    assert "content" not in body


@pytest.mark.anyio
async def test_generate_video_rejects_missing_prompt():
    server, backend = make_server({})

    result = await call(server, "generate_video", {"duration": 5})

    assert result.is_error
    assert "prompt" in text_of(result)
    assert backend.requests == []


@pytest.mark.anyio
async def test_generate_image_sends_payload():
    server, backend = make_server(
        {("POST", "/api/generation/image-tasks"): (200, {"id": "t3", "status": "queued"})}
    )

    result = await call(
        server,
        "generate_image",
        {"prompt": "水墨山水", "n": 2, "image_urls": ["https://x/ref.png"]},
    )

    assert not result.is_error, text_of(result)
    body = json.loads(backend.last("POST", "/api/generation/image-tasks").content)
    assert body["prompt"] == "水墨山水"
    assert body["n"] == 2
    assert body["image_urls"] == ["https://x/ref.png"]
    assert "image_model" not in body


@pytest.mark.anyio
async def test_api_error_becomes_readable_tool_error():
    server, _ = make_server(
        {("POST", "/api/generation/image-tasks"): (403, {"detail": "该模型未开放 API 调用，请联系管理员"})}
    )

    result = await call(server, "generate_image", {"prompt": "x"})

    assert result.is_error
    message = text_of(result)
    assert "403" in message
    assert "该模型未开放 API 调用" in message


@pytest.mark.anyio
async def test_missing_api_key_reports_how_to_configure():
    server, backend = make_server({}, api_key="")

    result = await call(server, "get_balance")

    assert result.is_error
    assert "setup_api_key" in text_of(result)
    assert "b6d-mcp configure" in text_of(result)
    assert backend.requests == []


@pytest.mark.anyio
async def test_api_key_saved_after_start_is_picked_up_without_restart():
    backend = FakeBackend({("GET", "/api/account/balance"): (200, {"available": 1})})
    saved = {"key": ""}
    api = B6dApi(endpoint=ENDPOINT, api_key="", key_loader=lambda: saved["key"], transport=httpx.MockTransport(backend))
    server = build_server(api, poll_interval=0)

    assert (await call(server, "get_balance")).is_error
    saved["key"] = "sk-late"
    assert not (await call(server, "get_balance")).is_error
    assert backend.last("GET", "/api/account/balance").headers["Authorization"] == "Bearer sk-late"


@pytest.mark.anyio
async def test_setup_api_key_opens_terminal(monkeypatch):
    from b6d_mcp import terminal

    monkeypatch.setattr(terminal, "open_configure_terminal", lambda: True)
    server, _ = make_server({}, api_key="")

    result = await call(server, "setup_api_key")

    assert not result.is_error
    assert "终端" in text_of(result)


@pytest.mark.anyio
async def test_setup_api_key_falls_back_to_command(monkeypatch):
    from b6d_mcp import terminal

    monkeypatch.setattr(terminal, "open_configure_terminal", lambda: False)
    server, _ = make_server({}, api_key="")

    result = await call(server, "setup_api_key")

    assert "b6d-mcp configure" in text_of(result)


@pytest.mark.anyio
async def test_get_task_prefers_original_image_urls():
    server, _ = make_server({("GET", "/api/generation/tasks/t-image"): (200, SUCCEEDED_IMAGE)})

    result = await call(server, "get_task", {"task_id": "t-image"})

    assert not result.is_error, text_of(result)
    assert result.structured_content["image_urls"] == [f"{ENDPOINT}/files/original1.png"]


@pytest.mark.anyio
async def test_wait_task_polls_until_done_and_downloads(tmp_path: Path):
    responses = iter(
        [
            httpx.Response(200, json={**SUCCEEDED_VIDEO, "status": "processing"}),
            httpx.Response(200, json=SUCCEEDED_VIDEO),
        ]
    )
    server, _ = make_server(
        {
            ("GET", "/api/generation/tasks/t-video"): lambda _req: next(responses),
            ("GET", "/files/video.mp4"): (200, b"MP4DATA"),
        }
    )

    result = await call(
        server, "wait_task", {"task_id": "t-video", "timeout_seconds": 30, "download_dir": str(tmp_path)}
    )

    assert not result.is_error, text_of(result)
    data = result.structured_content
    assert data["status"] == "succeeded"
    assert data["finished"] is True
    saved = Path(data["downloaded_files"][0])
    assert saved.parent == tmp_path
    assert saved.read_bytes() == b"MP4DATA"


@pytest.mark.anyio
async def test_download_does_not_send_api_key_to_file_host(tmp_path: Path):
    server, backend = make_server(
        {
            ("GET", "/api/generation/tasks/t-video"): (200, SUCCEEDED_VIDEO),
            ("GET", "/files/video.mp4"): (200, b"MP4DATA"),
        }
    )

    await call(server, "wait_task", {"task_id": "t-video", "download_dir": str(tmp_path)})

    assert "authorization" not in backend.last("GET", "/files/video.mp4").headers


@pytest.mark.anyio
async def test_wait_task_returns_unfinished_status_on_timeout():
    server, _ = make_server(
        {("GET", "/api/generation/tasks/t-video"): (200, {**SUCCEEDED_VIDEO, "status": "processing"})}
    )

    result = await call(server, "wait_task", {"task_id": "t-video", "timeout_seconds": 1})

    assert not result.is_error, text_of(result)
    assert result.structured_content["status"] == "processing"
    assert result.structured_content["finished"] is False


@pytest.mark.anyio
async def test_list_tasks_passes_filters():
    server, backend = make_server(
        {("GET", "/api/generation/tasks"): (200, {"items": [SUCCEEDED_IMAGE], "total": 1})}
    )

    result = await call(server, "list_tasks", {"status": "succeeded", "task_type": "image", "page_size": 5})

    assert not result.is_error, text_of(result)
    params = backend.last("GET", "/api/generation/tasks").url.params
    assert params["task_status"] == "succeeded"
    assert params["task_type"] == "image"
    assert params["page_size"] == "5"
    assert result.structured_content["items"][0]["id"] == "t-image"


@pytest.mark.anyio
async def test_upload_media_sends_local_file(tmp_path: Path):
    image = tmp_path / "ref.png"
    image.write_bytes(b"PNGDATA")
    server, backend = make_server(
        {("POST", "/api/generation/upload"): (200, {"id": "m1", "url": "https://x/m1.png", "type": "image"})}
    )

    result = await call(server, "upload_media", {"file_path": str(image), "folder_id": "f1"})

    assert not result.is_error, text_of(result)
    request = backend.last("POST", "/api/generation/upload")
    assert b"PNGDATA" in request.content
    assert b'name="folder_id"' in request.content
    assert result.structured_content["id"] == "m1"


@pytest.mark.anyio
async def test_upload_media_rejects_missing_file(tmp_path: Path):
    server, backend = make_server({})

    result = await call(server, "upload_media", {"file_path": str(tmp_path / "nope.png")})

    assert result.is_error
    assert "不存在" in text_of(result)
    assert backend.requests == []


@pytest.mark.anyio
async def test_move_media_to_root_sends_explicit_null():
    server, backend = make_server(
        {("PATCH", "/api/generation/media/m1"): (200, {"id": "m1", "folder_id": None})}
    )

    result = await call(server, "move_media", {"asset_id": "m1"})

    assert not result.is_error, text_of(result)
    body = json.loads(backend.last("PATCH", "/api/generation/media/m1").content)
    assert body == {"move": True, "folder_id": None}


@pytest.mark.anyio
async def test_delete_media_is_marked_destructive():
    server, _ = make_server({})
    async with Client(server) as client:
        tools = {tool.name: tool for tool in (await client.list_tools()).tools}
    assert tools["delete_media"].annotations.destructive_hint is True
    assert tools["list_media"].annotations.read_only_hint is True


@pytest.mark.anyio
async def test_search_media_and_folders_and_models():
    server, backend = make_server(
        {
            ("GET", "/api/generation/assets/search"): (200, {"items": [], "total": 0}),
            ("GET", "/api/generation/folders"): (200, {"items": [{"id": "f1", "name": "角色"}]}),
            ("POST", "/api/generation/folders"): (200, {"id": "f2", "name": "场景"}),
            ("GET", "/api/account/model-offering"): (200, {"model_keys": ["doubao-seedance-2-5-260628"]}),
        }
    )

    search = await call(server, "search_media", {"query": "猫"})
    folders = await call(server, "list_folders")
    created = await call(server, "create_folder", {"name": "场景"})
    models = await call(server, "list_models")

    for result in (search, folders, created, models):
        assert not result.is_error, text_of(result)
    assert backend.last("GET", "/api/generation/assets/search").url.params["q"] == "猫"
    assert json.loads(backend.last("POST", "/api/generation/folders").content) == {"name": "场景"}
    assert models.structured_content["model_keys"] == ["doubao-seedance-2-5-260628"]


@pytest.mark.anyio
async def test_ids_are_encoded_into_a_single_path_segment():
    server, backend = make_server({})

    await call(server, "get_task", {"task_id": "../../account/balance"})

    assert backend.requests[-1].url.raw_path == b"/api/generation/tasks/..%2F..%2Faccount%2Fbalance"


PNG_BYTES = b"\x89PNG\r\n\x1a\nfake"
EPISODE_PREVIEW = {
    "episode": {"id": "ep-1", "episode_index": 1, "web_url": "https://www.example.test/canvas/ep-1"},
    "project": {"id": "p-1", "name": "都市短剧"},
    "stats": {"succeeded": 1, "failed": 1},
    "nodes": [
        {
            "node_id": "n-1",
            "type": "video",
            "label": "雨夜",
            "shot": {"scene": "1-1", "shot": "1"},
            "status": "succeeded",
            "thumbnail_url": f"{ENDPOINT}/files/n1.jpg",
        },
        {"node_id": "n-2", "type": "video", "label": "天台", "status": "failed", "error_message": "审核未通过"},
        {"node_id": "n-3", "type": "image", "label": "定妆", "status": "succeeded",
         "thumbnail_url": f"{ENDPOINT}/files/broken.jpg"},
    ],
}


def _image_response(request: httpx.Request) -> httpx.Response:
    assert "authorization" not in request.headers
    return httpx.Response(200, content=PNG_BYTES, headers={"content-type": "image/png"})


@pytest.mark.anyio
async def test_preview_episode_returns_canvas_link_list_and_captioned_thumbnails():
    server, backend = make_server({
        ("GET", "/api/drama/episodes/ep-1/preview"): (200, EPISODE_PREVIEW),
        ("GET", "/files/n1.jpg"): _image_response,
        ("GET", "/files/broken.jpg"): (403, {"detail": "expired"}),
    })

    result = await call(server, "preview_episode", {"episode_id": "ep-1"})

    assert not result.is_error
    summary = json.loads(result.content[0].text)
    assert summary["canvas_url"] == "https://www.example.test/canvas/ep-1"
    assert summary["nodes"][1]["error_message"] == "审核未通过"
    assert summary["thumbnail_errors"] == ["定妆"]
    assert result.content[1].text == "缩略图：雨夜（1-1-1），succeeded"
    assert result.content[2].type == "image"
    assert result.content[2].mime_type == "image/png"
    assert len(result.content) == 3


@pytest.mark.anyio
async def test_preview_episode_without_thumbnails_skips_image_fetch():
    server, backend = make_server({("GET", "/api/drama/episodes/ep-1/preview"): (200, EPISODE_PREVIEW)})

    result = await call(server, "preview_episode", {"episode_id": "ep-1", "thumbnails": 0})

    assert len(result.content) == 1
    assert [r.url.path for r in backend.requests] == ["/api/drama/episodes/ep-1/preview"]


@pytest.mark.anyio
async def test_list_drama_episodes_and_projects():
    server, backend = make_server({
        ("GET", "/api/drama/projects"): (200, {"items": [{"id": "p-1"}], "total": 1}),
        ("GET", "/api/drama/projects/p-1/episodes"): (200, {"episodes": [{"id": "ep-1"}]}),
    })

    await call(server, "list_drama_projects", {"page_size": 5})
    episodes = await call(server, "list_drama_episodes", {"project_id": "p-1"})

    assert backend.last("GET", "/api/drama/projects").url.params["page_size"] == "5"
    assert "ep-1" in text_of(episodes)


@pytest.mark.anyio
async def test_preview_episode_missing_scope_is_readable():
    server, _ = make_server({
        ("GET", "/api/drama/episodes/ep-1/preview"): (403, {"detail": "API Key 缺少权限: canvas:read"}),
    })

    result = await call(server, "preview_episode", {"episode_id": "ep-1"})

    assert result.is_error
    assert "canvas:read" in text_of(result)
