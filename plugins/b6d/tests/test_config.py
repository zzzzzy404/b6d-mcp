"""配置：生产地址固定、Key 的读取顺序、configure 写文件，以及插件清单的一致性。"""
import json
import stat
import tomllib
from pathlib import Path

import pytest

from b6d_mcp import config
from b6d_mcp.api import B6dApi

PLUGIN_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.delenv(config.API_KEY_ENV, raising=False)
    monkeypatch.delenv(config.DEV_ENDPOINT_ENV, raising=False)
    return tmp_path


def test_endpoint_defaults_to_production():
    assert config.get_endpoint() == "https://api.b6d.co"
    assert B6dApi.from_config()._endpoint == "https://api.b6d.co"


def test_dev_endpoint_override_for_internal_testing(monkeypatch):
    monkeypatch.setenv(config.DEV_ENDPOINT_ENV, "http://localhost:8241")
    assert config.get_endpoint() == "http://localhost:8241"


def test_cli_style_endpoint_settings_are_ignored(isolated_home, monkeypatch):
    monkeypatch.setenv("B6D_ENDPOINT", "http://evil.test")
    (isolated_home / ".b6d").mkdir()
    (isolated_home / ".b6d" / "config.json").write_text(json.dumps({"endpoint": "http://evil.test"}))
    assert config.get_endpoint() == "https://api.b6d.co"


def test_api_key_env_wins_over_file(monkeypatch):
    config.save_api_key("sk-from-file")
    assert config.get_api_key() == "sk-from-file"
    monkeypatch.setenv(config.API_KEY_ENV, "sk-from-env")
    assert config.get_api_key() == "sk-from-env"


def test_save_api_key_keeps_other_fields_and_is_private(isolated_home):
    path = isolated_home / ".b6d" / "config.json"
    path.parent.mkdir()
    path.write_text(json.dumps({"endpoint": "http://cli-only", "api_key": "sk-old"}))

    config.save_api_key("  sk-new  ")

    assert json.loads(path.read_text()) == {"endpoint": "http://cli-only", "api_key": "sk-new"}
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_save_api_key_rejects_non_key():
    with pytest.raises(ValueError):
        config.save_api_key("hello")


def test_broken_config_file_is_treated_as_empty(isolated_home):
    (isolated_home / ".b6d").mkdir()
    (isolated_home / ".b6d" / "config.json").write_text("{not json")
    assert config.get_api_key() == ""


def test_configure_command_points_at_plugin_dir():
    assert str(PLUGIN_DIR) in config.configure_command()


def test_plugin_and_package_versions_match():
    plugin = json.loads((PLUGIN_DIR / ".codex-plugin" / "plugin.json").read_text())
    package = tomllib.loads((PLUGIN_DIR / "pyproject.toml").read_text())
    assert plugin["version"] == package["project"]["version"]


def test_mcp_manifest_does_not_forward_endpoint_override():
    servers = json.loads((PLUGIN_DIR / ".mcp.json").read_text())["mcpServers"]
    assert config.DEV_ENDPOINT_ENV not in servers["b6d"]["env_vars"]
    assert config.API_KEY_ENV in servers["b6d"]["env_vars"]
