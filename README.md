# AxonHubClient

`AxonHubClient` 是用于管理 AxonHub 实例的 Python client 和命令行工具。它面向 AxonHub Admin API，通过 Admin Token 访问 `/admin/graphql`，用于盘点和管理渠道、模型、API Key / Profile、用量、请求日志、Trace 和诊断信息。

## 适用场景

- 查看 AxonHub 实例中的渠道、模型、用量和请求状态。
- 批量导入、创建、更新、启停或排序渠道。
- 管理模型和模型关联规则。
- 检查渠道健康状态、请求日志、用量日志和 Trace。
- 在自动化脚本或 Agent 工作流中复用同一套 AxonHub 管理操作。

本项目不负责获取上游 API 资源。调用方应确保传入的 endpoint、API key 和模型信息已经获得授权。

## 文档

- [使用说明](docs/使用说明.md)：完整 CLI 命令、参数、确认规则和示例。
- [示例输入](docs/examples/)：渠道、模型、排序和 endpoint 等 JSON 输入样例。

## 安装

本项目使用 Python 3.10+。从源码目录安装开发依赖：

```powershell
uv sync --extra dev
```

运行 CLI：

```powershell
.venv\Scripts\axonhubclient.exe --help
```

也可以通过 `uv run` 调用：

```powershell
uv run axonhubclient --help
```

如需安装到当前用户工具环境：

```powershell
uv tool install --editable .
```

命令名为 `axonhubclient`；Windows 下为 `axonhubclient.exe`，macOS / Linux 下为 `axonhubclient`。

## 快速开始

首次使用先登录 AxonHub 管理后台。登录成功后，CLI 会把默认 session 保存到当前用户配置目录；session 文件保存实例地址、token、用户摘要和保存时间，不保存密码。

```powershell
axonhubclient auth login --url https://your-axonhub.example.com --username admin@example.com
```

`auth login` 也可以不传参数，按提示交互式输入实例地址、用户名和密码。

常用盘点命令：

```powershell
axonhubclient --json inventory summary
axonhubclient --json channels list
axonhubclient --json models list
axonhubclient --json api-keys list --status enabled
axonhubclient --json diagnostics channel-health --limit 10
```

创建或修改资源时，先查看 dry-run 输出，再追加 `--confirm` 执行真实变更：

```powershell
axonhubclient channels create `
  --type openai `
  --name "openai-main" `
  --upstream-base-url "https://api.openai.com/v1" `
  --api-key "sk-..." `
  --tag prod

axonhubclient channels create `
  --type openai `
  --name "openai-main" `
  --upstream-base-url "https://api.openai.com/v1" `
  --api-key "sk-..." `
  --tag prod `
  --confirm
```

更多命令、参数和输入文件格式见 [使用说明](docs/使用说明.md)。

## Python Client

也可以在 Python 代码中直接使用 client：

```python
from axonhub_client import AxonHubClient

client = AxonHubClient.from_config(
    "https://your-axonhub.example.com",
    admin_token="your-admin-token",
)

channels = client.channels.list(first=20)
```

## 安全说明

- 写操作默认 dry-run；传入 `--confirm` 才提交真实 mutation。
- CLI 输出会对常见敏感字段二次脱敏。
- 渠道查询不请求 `Channel.credentials`。
- 渠道查询不请求 disabled API key 明文字段。
- API Key / Profile 盘点不请求明文字段 `key`。
- `auth login` 不保存密码，默认不打印 token。
- 渠道测试和渠道内 API key 测试会真实请求上游接口，可能消耗额度，因此也需要显式确认。

## 许可证

本项目使用 Apache License 2.0，详见 [LICENSE](LICENSE)。
