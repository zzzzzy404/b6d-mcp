"""MCP 用的对外 API 客户端：出错抛 ToolError，不像 CLI 那样直接退出进程。"""
import mimetypes
from pathlib import Path
from urllib.parse import quote
from typing import Any, Optional

import httpx
from mcp.server.mcpserver.exceptions import ToolError

from b6d_mcp.config import API_KEY_ENV, configure_command, get_api_key, get_endpoint

API_TIMEOUT_SECONDS = 60
TRANSFER_TIMEOUT_SECONDS = 300
MAX_UPLOAD_BYTES = 100 * 1024 * 1024

_STATUS_HINTS = {
    401: "认证失败：API Key 无效或已过期",
    403: "权限不足：当前 API Key 没有这项权限，或模型未开放",
    404: "资源不存在：请检查 ID 是否正确",
    422: "参数不合法",
    429: "请求过于频繁，请稍后再试",
}


class B6dApiError(ToolError):
    """对外 API 调用失败。继承 ToolError，MCP 会把消息原样交给模型。"""


def path_id(value: str) -> str:
    """模型传来的 id 拼进 URL 路径前先编码，防止 ../ 之类跳到别的接口。"""
    if not value or not value.strip():
        raise B6dApiError("id 不能为空")
    return quote(value.strip(), safe="")


def _error_detail(response: httpx.Response) -> str:
    try:
        detail = response.json().get("detail", response.text)
    except ValueError:
        detail = response.text
    return detail if isinstance(detail, str) else str(detail)


class B6dApi:
    def __init__(self, endpoint: str, api_key: str, transport: Optional[httpx.AsyncBaseTransport] = None):
        self._endpoint = endpoint.rstrip("/")
        self._api_key = api_key
        self._transport = transport

    @classmethod
    def from_config(cls) -> "B6dApi":
        """服务地址固定为生产环境；API Key 读 B6D_API_KEY 或 ~/.b6d/config.json。"""
        return cls(endpoint=get_endpoint(), api_key=get_api_key())

    def _ensure_config(self) -> None:
        if not self._api_key:
            raise B6dApiError(
                f"未配置 b6d API Key。请让用户在终端运行：{configure_command()} ，"
                f"或设置环境变量 {API_KEY_ENV}，然后重启 Codex"
            )

    def _client(self, timeout: float, with_auth: bool) -> httpx.AsyncClient:
        headers = {"Authorization": f"Bearer {self._api_key}"} if with_auth else {}
        return httpx.AsyncClient(timeout=timeout, headers=headers, transport=self._transport)

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[dict] = None,
        json: Any = None,
        data: Optional[dict] = None,
        files: Optional[dict] = None,
        timeout: float = API_TIMEOUT_SECONDS,
    ) -> Any:
        self._ensure_config()
        clean_params = {k: v for k, v in (params or {}).items() if v is not None}
        try:
            async with self._client(timeout, with_auth=True) as client:
                response = await client.request(
                    method,
                    f"{self._endpoint}{path}",
                    params=clean_params,
                    json=json,
                    data=data,
                    files=files,
                )
        except httpx.HTTPError as exc:
            raise B6dApiError(f"无法连接 b6d 服务 {self._endpoint}：{exc}") from exc

        if response.status_code >= 400:
            hint = _STATUS_HINTS.get(response.status_code, "请求失败")
            raise B6dApiError(f"{hint} (HTTP {response.status_code})：{_error_detail(response)}")
        return response.json()

    async def get(self, path: str, params: Optional[dict] = None) -> Any:
        return await self.request("GET", path, params=params)

    async def post(self, path: str, json: Any = None) -> Any:
        return await self.request("POST", path, json=json)

    async def patch(self, path: str, json: Any = None) -> Any:
        return await self.request("PATCH", path, json=json)

    async def delete(self, path: str) -> Any:
        return await self.request("DELETE", path)

    async def upload(self, file_path: Path, folder_id: Optional[str] = None) -> Any:
        if not file_path.is_file():
            raise B6dApiError(f"文件不存在：{file_path}")
        if file_path.stat().st_size > MAX_UPLOAD_BYTES:
            raise B6dApiError("文件超过 100MB 上传上限")
        content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        data = {"folder_id": folder_id} if folder_id else None
        with file_path.open("rb") as handle:
            return await self.request(
                "POST",
                "/api/generation/upload",
                data=data,
                files={"file": (file_path.name, handle, content_type)},
                timeout=TRANSFER_TIMEOUT_SECONDS,
            )

    async def fetch_image(self, url: str, max_bytes: int) -> tuple[bytes, str]:
        """取签名 URL 上的小图（缩略图），返回 (内容, 图片格式)。同样不带 API Key。"""
        try:
            async with self._client(API_TIMEOUT_SECONDS, with_auth=False) as client:
                response = await client.get(url)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise B6dApiError(f"获取缩略图失败：{exc}") from exc
        content_type = response.headers.get("content-type", "").split(";", 1)[0].strip()
        if not content_type.startswith("image/"):
            raise B6dApiError(f"缩略图不是图片：{content_type or '未知类型'}")
        if len(response.content) > max_bytes:
            raise B6dApiError("缩略图过大")
        return response.content, content_type.removeprefix("image/")

    async def download(self, url: str, destination: Path) -> Path:
        """下载签名 URL。文件存在对象存储上，不能带 API Key。"""
        try:
            async with self._client(TRANSFER_TIMEOUT_SECONDS, with_auth=False) as client:
                async with client.stream("GET", url) as response:
                    response.raise_for_status()
                    with destination.open("wb") as handle:
                        async for chunk in response.aiter_bytes():
                            handle.write(chunk)
        except httpx.HTTPError as exc:
            destination.unlink(missing_ok=True)
            raise B6dApiError(f"下载结果失败：{exc}") from exc
        return destination
