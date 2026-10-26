"""打开一个新的终端窗口运行 b6d-mcp configure，用户只需粘贴 API Key。

Key 不能经过 Codex 对话（会进模型上下文），所以由用户在终端里输入；这里负责把终端和命令准备好。
"""
import shlex
import shutil
import subprocess
import sys
from typing import Callable, Optional

WINDOW_TITLE = "b6d API Key"
# 中文注释：按常见程度排序；gnome-terminal 用 -- 分隔命令，其余用 -e
_LINUX_TERMINALS = (
    ("x-terminal-emulator", "-e"),
    ("gnome-terminal", "--"),
    ("konsole", "-e"),
    ("xfce4-terminal", "-x"),
    ("xterm", "-e"),
)
_KEEP_OPEN = "; printf '\\n按回车关闭窗口'; read _"


def configure_shell_command(platform: str = sys.platform) -> str:
    """用当前 Python 运行 configure：插件里的 uv 环境、uvx 临时环境都适用。"""
    argv = [sys.executable, "-m", "b6d_mcp", "configure"]
    if platform == "win32":
        return subprocess.list2cmdline(argv)
    return " ".join(shlex.quote(part) for part in argv)


def _applescript_string(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def terminal_launch_argv(
    command: str,
    platform: str = sys.platform,
    which: Callable[[str], Optional[str]] = shutil.which,
) -> Optional[list[str]]:
    """返回在新终端窗口里运行 command 的启动参数；找不到可用终端时返回 None。"""
    if platform == "darwin":
        return [
            "osascript",
            "-e", 'tell application "Terminal" to activate',
            "-e", f'tell application "Terminal" to do script {_applescript_string(command)}',
        ]
    if platform == "win32":
        return ["cmd", "/c", "start", WINDOW_TITLE, "cmd", "/k", command]
    for name, exec_flag in _LINUX_TERMINALS:
        path = which(name)
        if path:
            return [path, exec_flag, "sh", "-c", command + _KEEP_OPEN]
    return None


def open_configure_terminal() -> bool:
    """打开终端窗口运行 configure。成功启动返回 True；没有终端或启动失败返回 False。"""
    argv = terminal_launch_argv(configure_shell_command())
    if argv is None:
        return False
    try:
        subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        return False
    return True
