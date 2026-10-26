# b6d Codex 插件

在 Codex 里调用 b6d：生成图片和视频、管理素材库、预览短剧工作台。MCP 服务在用户本机运行，固定连接 `https://api.b6d.co`。

## 安装

1. 安装 uv（已装可跳过）：

   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

2. 如果之前按旧方式手动添加过 b6d MCP（`codex mcp add b6d ...`），先删掉，否则 Codex 会跳过插件里的 b6d：

   ```bash
   codex mcp remove b6d
   ```

   在 Codex 里添加插件市场并安装 b6d 插件：

   ```bash
   codex plugin marketplace add zzzzzy404/b6d-mcp
   codex plugin add b6d@b6d
   ```

3. 在 b6d 网站「API 密钥」页面创建 Key（勾选需要的权限，查看短剧工作台需要 `canvas:read`），然后保存到本机：

   ```bash
   uvx --from "git+https://github.com/zzzzzy404/b6d-mcp#subdirectory=plugins/b6d" b6d-mcp configure
   ```

   Key 保存在 `~/.b6d/config.json`（权限 600），与 b6d CLI 共用。也可以改用环境变量 `B6D_API_KEY`。

4. 重启 Codex。首次启动会自动安装依赖，大约十几秒。

没配 Key 时调用任何工具，都会返回带本机路径的 `configure` 命令，照着运行即可。

## 更新

改代码后同时提高 `plugins/b6d/.codex-plugin/plugin.json` 和 `plugins/b6d/pyproject.toml` 里的 `version`（测试会检查两者一致），推到 GitHub。用户运行下面的命令拿到新版本：

```bash
codex plugin marketplace upgrade
```

## 仓库结构

```
.agents/plugins/marketplace.json   插件市场清单
plugins/b6d/
  .codex-plugin/plugin.json        插件信息（名称、版本、介绍）
  .mcp.json                        Codex 如何启动 MCP 服务
  scripts/launch.sh                找到 uv 并启动服务
  pyproject.toml / uv.lock         依赖，锁定版本
  src/b6d_mcp/                     MCP 服务代码
  tests/                           测试
```

## 开发

```bash
cd plugins/b6d
uv run pytest
```

联调本地或测试环境时设置 `B6D_DEV_ENDPOINT`（例如 `http://localhost:8241`）。插件的 `.mcp.json` 不转发这个变量，正常安装的用户连不到别的地址。

在 Codex 里联调：用本地路径添加插件市场并安装，再只改已安装副本 `~/.codex/plugins/cache/b6d/b6d/<版本>/.mcp.json`，在 `mcpServers.b6d` 下加 `"env": {"B6D_DEV_ENDPOINT": "http://localhost:8241"}`。重新安装插件即恢复为生产地址。

注意：`~/.codex/config.toml` 里不能再有手动添加的同名 `[mcp_servers.b6d]`，否则 Codex 会跳过插件里的 b6d 服务。`b6d-mcp configure` 检测到这种情况会提示运行 `codex mcp remove b6d`。
