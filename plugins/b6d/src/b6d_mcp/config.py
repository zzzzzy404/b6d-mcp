"""配置：服务地址固定为 b6d 生产环境；API Key 读环境变量 B6D_API_KEY 或 ~/.b6d/config.json。"""
import json
import os
from pathlib import Path

PRODUCTION_ENDPOINT = "https://api.b6d.co"
# 中文注释：仅供内部联调本地/测试环境。插件的 .mcp.json 不转发这个变量，正常安装的用户改不了地址
DEV_ENDPOINT_ENV = "B6D_DEV_ENDPOINT"
API_KEY_ENV = "B6D_API_KEY"
API_KEY_PREFIX = "sk-"


def plugin_dir() -> Path:
    """插件根目录（src/b6d_mcp 往上两级）。uv run 以可编辑方式安装，__file__ 就在插件目录里。"""
    return Path(__file__).resolve().parents[2]


def configure_command() -> str:
    return f'uv run --project "{plugin_dir()}" b6d-mcp configure'


def config_file() -> Path:
    """与 b6d CLI 共用 ~/.b6d/config.json，CLI 里配置过的 Key 直接可用。"""
    return Path.home() / ".b6d" / "config.json"


def _load_file() -> dict:
    path = config_file()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def get_endpoint() -> str:
    return os.environ.get(DEV_ENDPOINT_ENV) or PRODUCTION_ENDPOINT


def get_api_key() -> str:
    return (os.environ.get(API_KEY_ENV) or _load_file().get("api_key") or "").strip()


def save_api_key(api_key: str) -> Path:
    """写入 Key，保留文件里的其他字段，权限 600。"""
    key = api_key.strip()
    if not key.startswith(API_KEY_PREFIX):
        raise ValueError(f"API Key 应以 {API_KEY_PREFIX} 开头")
    path = config_file()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    data = {**_load_file(), "api_key": key}
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    path.chmod(0o600)
    return path
