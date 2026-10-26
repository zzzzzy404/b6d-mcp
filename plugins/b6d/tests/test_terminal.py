"""打开终端窗口让用户粘贴 API Key：各平台的启动命令，以及找不到终端时的退路。"""
import shlex
import sys

from b6d_mcp import terminal

CMD = "'/x/python' -m b6d_mcp configure"


def test_configure_shell_command_uses_current_python():
    assert terminal.configure_shell_command(platform="darwin") == f"{shlex.quote(sys.executable)} -m b6d_mcp configure"
    windows = terminal.configure_shell_command(platform="win32")
    assert windows.endswith(" -m b6d_mcp configure") and "'" not in windows


def test_macos_uses_terminal_app_and_escapes_quotes():
    argv = terminal.terminal_launch_argv(CMD, platform="darwin", which=lambda name: None)
    assert argv[0] == "osascript"
    script = " ".join(argv)
    assert 'tell application "Terminal"' in script
    assert "do script \"'/x/python' -m b6d_mcp configure\"" in script


def test_macos_escapes_double_quotes_and_backslashes():
    argv = terminal.terminal_launch_argv('"a\\b"', platform="darwin", which=lambda name: None)
    assert 'do script "\\"a\\\\b\\""' in " ".join(argv)


def test_windows_opens_new_cmd_window():
    argv = terminal.terminal_launch_argv(CMD, platform="win32", which=lambda name: None)
    assert argv[:4] == ["cmd", "/c", "start", "b6d API Key"]
    assert argv[-1] == CMD


def test_linux_prefers_available_terminal():
    available = {"gnome-terminal"}
    argv = terminal.terminal_launch_argv(CMD, platform="linux", which=lambda n: f"/usr/bin/{n}" if n in available else None)
    assert argv[:2] == ["/usr/bin/gnome-terminal", "--"]
    assert argv[-1].startswith(CMD)


def test_linux_without_terminal_returns_none():
    assert terminal.terminal_launch_argv(CMD, platform="linux", which=lambda n: None) is None


def test_open_configure_terminal_launches_process(monkeypatch):
    launched = []
    monkeypatch.setattr(terminal, "terminal_launch_argv", lambda cmd: ["fake-term", cmd])
    monkeypatch.setattr(terminal.subprocess, "Popen", lambda argv, **kw: launched.append(argv))
    assert terminal.open_configure_terminal() is True
    assert launched and launched[0][0] == "fake-term"


def test_open_configure_terminal_reports_failure(monkeypatch):
    monkeypatch.setattr(terminal, "terminal_launch_argv", lambda cmd: None)
    assert terminal.open_configure_terminal() is False

    def boom(argv, **kw):
        raise OSError("no such file")

    monkeypatch.setattr(terminal, "terminal_launch_argv", lambda cmd: ["fake-term"])
    monkeypatch.setattr(terminal.subprocess, "Popen", boom)
    assert terminal.open_configure_terminal() is False
