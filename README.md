# AxonHubClient

`AxonHubClient` 是用于管理 AxonHub 实例的 Python client 和命令行工具。它面向 AxonHub Admin API，通过 Admin Token 访问 `/admin/graphql`，用于盘点和管理渠道、模型、API Key / Profile、用量、请求日志、Trace 和诊断信息。

## 上游项目：AxonHub

[AxonHub](https://github.com/looplj/axonhub) 是一个开源 AI Gateway / AI 开发平台，目标是在不更换业务代码和 SDK 的前提下，把 OpenAI、Anthropic、Gemini 等不同模型供应商接入到统一网关中。它提供模型供应商切换、统一 API 入口、智能负载均衡、故障转移、用量与成本统计、请求追踪和后台管理等能力。

本项目不替代 AxonHub 本体，而是围绕已有 AxonHub 实例提供可脚本化、可被 Agent 调用的管理层：通过命令行或 Python client 管理渠道、模型、API Key / Profile、用量和诊断信息。

## 适用场景

- 查看 AxonHub 实例中的渠道、模型、用量和请求状态。
- 按 AxonHub Project 盘点 API Key / Profile、请求、用量日志和 Trace。
- 批量导入、创建、更新、启停或排序渠道。
- 管理模型和模型关联规则。
- 检查渠道健康状态、请求日志、用量日志和 Trace。
- 在自动化脚本或 Agent 工作流中复用同一套 AxonHub 管理操作。

本项目不负责获取上游 API 资源。调用方应确保传入的 endpoint、API key 和模型信息已经获得授权。

## 文档

- [使用说明](docs/使用说明.md)：完整 CLI 命令、参数、确认规则和示例。
- [示例输入](docs/examples/)：渠道、模型、排序和 endpoint 等 JSON 输入样例。

## 安装

推荐使用 `uv` 作为独立命令行工具安装：

```bash
uv tool install axonhub-client
axonhub-client --help
```

升级和卸载：

```bash
uv tool upgrade axonhub-client
uv tool uninstall axonhub-client
```

Windows 用户也可以从 GitHub Release 下载 `axonhub-client-windows-x64-vX.Y.Z.zip`，解压后直接运行：

```powershell
.\axonhub-client.exe --help
```

从源码目录开发时：

```bash
uv sync --extra dev
uv run axonhub-client --help
```

命名约定：安装包、CLI 命令和发布产物使用 `axonhub-client`；Python import 包名使用 `axonhub_client`。

## 快速开始

首次使用先登录 AxonHub 管理后台。登录成功后，CLI 会把默认 session 保存到当前用户配置目录；session 文件保存实例地址、token、用户摘要和保存时间，不保存密码。

```powershell
axonhub-client auth login --url https://your-axonhub.example.com --username admin@example.com
```

上面的命令会继续提示输入密码，密码输入不会回显。需要非交互登录时，可以显式传入 `--password`：

```powershell
axonhub-client auth login --url https://your-axonhub.example.com --username admin@example.com --password "your-password"
```

`auth login` 也可以不传参数，按提示交互式输入实例地址、用户名和密码。

常用盘点命令：

```powershell
axonhub-client --json inventory summary
axonhub-client --json channels list
axonhub-client --json models list
axonhub-client --json api-keys list --status enabled
axonhub-client --project <project-id> --json requests list --first 20
axonhub-client --json diagnostics channel-health --limit 10
```

`--project <project-id>` 是全局参数，专指 AxonHub Project。它会作为 `X-Project-ID` 请求上下文，并用于 API Key / Profile、请求、用量日志和 Trace 等项目归属资源的列表过滤。

创建或修改资源时，命令默认只预览将要执行的操作，不会直接修改 AxonHub。确认无误后，再追加 `--confirm` 执行真实变更：

```powershell
axonhub-client channels create `
  --type openai `
  --name "openai-main" `
  --upstream-base-url "https://api.openai.com/v1" `
  --api-key "sk-..." `
  --tag prod

axonhub-client channels create `
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

- 创建、修改、删除等操作默认只预览，不会直接修改 AxonHub；传入 `--confirm` 后才会执行。
- 命令输出会自动遮盖常见敏感信息，例如 API key、token 和密码。
- 查询渠道时不会读取渠道中保存的上游密钥配置。
- 查询已禁用的渠道密钥时不会读取密钥明文。
- 查看 AxonHub API Key / Profile 信息时不会读取 API key 明文。
- `auth login` 不保存密码，默认也不会打印登录 token。
- 测试渠道和测试渠道内 API key 会真实请求上游服务，可能消耗额度，因此也需要显式确认。

## 许可证

本项目使用 Apache License 2.0，详见 [LICENSE](LICENSE)。

