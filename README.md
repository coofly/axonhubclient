# AxonHubClient

`AxonHubClient` 是用于管理 AxonHub 实例的 Python client 和 CLI。

当前阶段已经从“只读资产盘点”推进到“资产盘点 + 安全受控写操作”的管理闭环。读操作可直接执行；写操作默认 dry-run，必须显式传入统一确认参数 `--confirm` 才会提交真实 mutation。删除、清理 disabled key 等高风险操作仍只使用 `--confirm`，但 dry-run 输出会明确标记不可逆或高风险影响。

完整命令、参数、安全确认和示例输入文件见 [`docs/axonhubclient-CLI参考.md`](docs/axonhubclient-CLI参考.md)。示例 JSON 位于 [`docs/examples/`](docs/examples/)。

- `auth status|login|logout|whoami`
- `channels list|get|summary|tags|count-by-type|create|create-many|import|update|status|enable|disable|reorder|endpoints set|test|keys test|keys disable|keys enable|keys enable-all|keys enable-selected|keys prune-disabled|models sync|archive|recover|delete`
- `api-keys list|get|quota|templates`
- `models list|get|create|create-many|update|status|enable|disable|archive|recover|delete|rules list|rules preview|rules replace|rules add|rules remove|rules enable|rules disable|rules reorder|rules unassociated|fastest`
- `requests list|get|executions`
- `usage overview|requests-by-*|tokens-by-*|cost-by-*|daily|token-stats|channel-success-rates|logs list|logs get`
- `traces list|get`
- `diagnostics channel-health`
- `inventory summary`
- `smoke read-only`

## 安装

开发目录中优先使用项目内虚拟环境：

```powershell
uv sync --extra dev
.venv\Scripts\axonhubclient.exe --help
```

也可以通过 `uv run` 调用：

```powershell
uv run axonhubclient --help
```

如果需要安装到当前用户工具环境，可使用 editable tool 安装：

```powershell
uv tool install --editable .
```

命令名为 `axonhubclient`；Windows 下会生成 `axonhubclient.exe`，macOS / Linux 下会生成 `axonhubclient`。

首次使用先登录。CLI 会在当前用户的跨平台配置目录保存默认 session，后续命令自动读取该 session；session 失效时会提示重新登录。

```powershell
axonhubclient auth login --url https://your-axonhub.example.com --username admin@example.com
axonhubclient --json channels list
```

`auth login` 也可以不传参数，按提示交互式输入实例地址、用户名和密码。session 文件只保存 `baseUrl`、`token`、用户摘要和保存时间，不保存密码。`auth logout` 可清除当前默认 session。

```powershell
axonhubclient auth login
```

需要设置请求上下文项目时，使用全局 `--context-project-id`；列表筛选里的项目 ID 参数统一使用子命令局部的 `--project-id`。

```powershell
axonhubclient --json --context-project-id <project-id> inventory summary
axonhubclient --json requests list --project-id <project-id>
```

API Key / Profile 盘点是只读能力，不请求明文 `key` 字段；列表默认排除 `noauth`，可通过 `--type noauth` 显式查看：

```powershell
axonhubclient --json api-keys list --status enabled
axonhubclient --json api-keys get <api-key-id>
axonhubclient --json api-keys quota <api-key-id>
axonhubclient --json api-keys templates
```

创建渠道默认只做 dry-run，确认后才会提交 `createChannel` mutation。上游 API key 直接通过 `--api-key` 传入，可重复提供多个 key。对 OpenAI/NewAPI 兼容渠道，如果未提供 `--supported-model`，CLI 会自动请求上游 `/models` 获取 supportedModels；也可以手动传入 `--supported-model` 覆盖自动发现结果。

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

常见渠道写操作：

```powershell
axonhubclient channels create-many --input-file docs\examples\channel.bulk-create.json --confirm
axonhubclient channels import --input-file docs\examples\channels.import.json --confirm
axonhubclient channels update <channel-id> --input-file docs\examples\channel.update.json --confirm
axonhubclient channels status <channel-id> enabled --confirm
axonhubclient channels reorder --input-file docs\examples\channel.bulk-ordering.json --confirm
axonhubclient channels endpoints set <channel-id> --endpoints-file docs\examples\channel.endpoints.json --confirm
axonhubclient channels models sync <channel-id> --pattern "gpt-.*" --confirm
```

`channels test` 和 `channels keys test` 会真实请求上游接口，可能消耗额度：

```powershell
axonhubclient channels test <channel-id> --model gpt-4o-mini --confirm
axonhubclient channels keys test <channel-id> --model gpt-4o-mini --confirm
```

渠道内 API key 管理直接通过 `--key` 传入；需要多个 key 的命令可重复传入 `--key`，也可用 JSON array：

```powershell
axonhubclient channels keys disable <channel-id> --key "sk-..." --confirm
axonhubclient channels keys enable <channel-id> --key "sk-..." --confirm
axonhubclient channels keys enable-all <channel-id> --confirm
axonhubclient channels keys enable-selected <channel-id> --key "sk-..." --key "sk-..." --confirm
axonhubclient channels keys prune-disabled <channel-id> --key '["sk-...","sk-..."]' --confirm
```

模型管理和关联规则：

```powershell
axonhubclient models create --input-file docs\examples\model.create.json
axonhubclient models create-many --input-file docs\examples\models.bulk-create.json --confirm
axonhubclient models status <model-entity-id> enabled --confirm
axonhubclient models rules list <model-entity-id>
axonhubclient --json models rules preview <model-entity-id>
axonhubclient models rules add <model-entity-id> --association-file docs\examples\model.rule.json --position 1 --confirm
axonhubclient models rules replace <model-entity-id> --associations-file docs\examples\model.associations.json --confirm
```

删除属于不可逆高风险操作，仍使用统一 `--confirm`：

```powershell
axonhubclient channels delete <channel-id> --confirm
axonhubclient models delete <model-entity-id> --confirm
```

安全边界：

- 不请求 `Channel.credentials`。
- 不请求 disabled API key 明文字段。
- CLI 输出会对常见敏感字段二次脱敏。
- 写操作默认 dry-run；传入 `--confirm` 才执行 mutation。
- 渠道内 API key 管理通过命令参数传入 key；dry-run 输出会脱敏 `key` / `keys`。

## 许可证

本项目使用 Apache License 2.0，详见 [LICENSE](LICENSE)。

