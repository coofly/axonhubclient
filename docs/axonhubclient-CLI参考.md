# AxonHubClient CLI 参考

本文档按资源整理 `axonhubclient` CLI 的常用命令、参数、安全确认和示例输入文件。命令默认面向 AxonHub Admin API，认证使用当前用户配置目录中的默认 session。

## 全局参数

- `--context-project-id`：可选 `X-Project-ID` 请求上下文。
- `--timeout`：请求超时时间，单位秒，默认 `30`。
- `--json`：输出完整 JSON 响应。

列表类筛选参数统一使用子命令局部的 `--project-id`；它不同于全局请求上下文 `--context-project-id`。

## 安装与 Session

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

默认 session 保存位置：

- Windows：`%APPDATA%\AxonhubClient\session.json`
- macOS：`~/Library/Application Support/AxonhubClient/session.json`
- Linux：`$XDG_CONFIG_HOME/axonhubclient/session.json` 或 `~/.config/axonhubclient/session.json`

## 安全模型

- 读操作可直接执行。
- 写操作默认 dry-run；必须显式传入 `--confirm` 才提交 mutation。
- 删除渠道、删除模型、清理 disabled key 等高风险操作也只使用 `--confirm`，dry-run 输出会明确标记不可逆或高风险影响。
- dry-run 输出统一包含 `dryRun`、`operation`、`effect`、`variables`。
- CLI 不请求 `Channel.credentials`，不读取 disabled API key 或 API Key 主体的明文字段。
- CLI 输出会对 `apiKey`、`apiKeys`、`key`、`keys`、`token`、`password` 等字段脱敏。
- 请求/响应正文、headers 和 chunks 可能包含业务敏感内容；`requests get` 默认不读取这些字段，只有显式传入 `--include-content` 时才会请求。
- 示例 JSON 使用占位符；不要把真实 token、API key、账号密码或 endpoint 私密信息提交进仓库。
- 首次使用需执行 `auth login`；登录成功后自动生成默认 session，该文件不保存密码。
- 如果 session 失效或权限不足，CLI 会提示重新运行 `axonhubclient auth login`。

## Auth

| 命令 | 用途 | 写操作 |
| --- | --- | --- |
| `auth status` | 读取 `/admin/system/status` | 否 |
| `auth login` | 使用账号密码登录并保存默认 session | 否 |
| `auth whoami` | 读取当前 token 对应用户 | 否 |
| `auth logout` | 清除默认 session | 否 |

```powershell
axonhubclient auth login --url https://axonhub.example.com --username admin@example.com
axonhubclient auth login
axonhubclient auth logout
axonhubclient --json auth status
```

`auth login` 缺少 `url`、`username` 或 `password` 时会交互式询问；密码输入不会回显。登录成功后输出 session 文件路径和用户摘要，不默认打印 token。

## Inventory

| 命令 | 用途 | 关键参数 |
| --- | --- | --- |
| `inventory summary` | 聚合渠道、模型、用量、成功率和异常状态 | `--channel-first`、`--model-first`、`--success-window`、`--success-limit`、`--min-success-rate` |

```powershell
axonhubclient --json inventory summary
```

## Channels

### 只读命令

| 命令 | 用途 | 关键参数 |
| --- | --- | --- |
| `channels list` | 分页读取渠道 | `--first`、`--after`、`--status`、`--type`、`--tag`、`--model` |
| `channels get <id>` | 读取单个渠道 | `<id>` |
| `channels summary` | 读取渠道摘要和模型入口 | `--include-archived` |
| `channels tags` | 读取全部渠道标签 | 无 |
| `channels count-by-type` | 按渠道类型计数 | `--status` |

### 写操作

| 命令 | 用途 | 确认参数 |
| --- | --- | --- |
| `channels create` | 创建单个渠道 | `--confirm` |
| `channels create-many` | 按一份配置和多个 API key 批量创建渠道 | `--confirm` |
| `channels import` | 导入多条渠道记录 | `--confirm` |
| `channels update <id>` | 使用 `UpdateChannelInput` 更新渠道 | `--confirm` |
| `channels status <id> <enabled\|disabled>` | 设置单个渠道启停状态 | `--confirm` |
| `channels enable <ids...>` | 批量启用渠道 | `--confirm` |
| `channels disable <ids...>` | 批量禁用渠道 | `--confirm` |
| `channels archive <ids...>` | 批量归档渠道 | `--confirm` |
| `channels recover <ids...>` | 批量恢复归档渠道 | `--confirm` |
| `channels delete <ids...>` | 删除渠道，高风险不可逆 | `--confirm` |
| `channels reorder` | 批量更新排序权重 | `--confirm` |
| `channels endpoints set <id>` | 替换渠道 endpoints | `--confirm` |
| `channels models sync <id>` | 立即同步渠道 supportedModels | `--confirm` |

`channels create` 的 `--supported-model` 是可选参数：如果手动提供则优先使用；如果省略，CLI 会使用上游 API key 请求 OpenAI/NewAPI 兼容 `/models` 端点，自动填充 `supportedModels` 和默认测试模型。自动发现失败时不会回退到占位模型，而是要求显式提供 `--supported-model`。

`manualModels` 仅由显式 `--manual-model` 写入。未传 `--manual-model` 时默认 `manualModels=[]`，因此自动发现的模型不会在网站上显示为 `手动`。

```powershell
axonhubclient channels create `
  --type openai `
  --name iKunCode `
  --upstream-base-url https://api.ikuncode.cc/v1 `
  --api-key "sk-..."

axonhubclient channels create-many --input-file docs\examples\channel.bulk-create.json
axonhubclient channels import --input-file docs\examples\channels.import.json --confirm
axonhubclient channels update <channel-id> --input-file docs\examples\channel.update.json --confirm
axonhubclient channels reorder --input-file docs\examples\channel.bulk-ordering.json --confirm
axonhubclient channels endpoints set <channel-id> --endpoints-file docs\examples\channel.endpoints.json --confirm
axonhubclient channels models sync <channel-id> --pattern "gpt-.*" --confirm
```

`channels test` 和 `channels keys test` 也默认 dry-run，但执行时会真实请求上游接口，可能消耗额度：

```powershell
axonhubclient channels test <channel-id> --model gpt-4o-mini --confirm
axonhubclient channels keys test <channel-id> --model gpt-4o-mini --confirm
```

渠道内 API key 管理命令直接通过 `--key` 读取 key。需要多个 key 的命令可重复传入 `--key`，也可传入 JSON array：

```powershell
axonhubclient channels keys disable <channel-id> --key "sk-..." --confirm
axonhubclient channels keys enable <channel-id> --key "sk-..." --confirm
axonhubclient channels keys enable-all <channel-id> --confirm
axonhubclient channels keys enable-selected <channel-id> --key "sk-..." --key "sk-..." --confirm
axonhubclient channels keys prune-disabled <channel-id> --key '["sk-...","sk-..."]' --confirm
```

## API Keys

`api-keys` 是只读盘点资源。相关 GraphQL 查询不会选择 API Key 明文字段 `key`；输出仍会经过通用脱敏层。

| 命令 | 用途 | 关键参数 |
| --- | --- | --- |
| `api-keys list` | 分页读取 API Key 摘要 | `--first`、`--after`、`--status`、`--type`、`--name`、`--project-id`、`--user-id` |
| `api-keys get <id>` | 读取单个 API Key 详情和 Profile 配置 | `<id>` |
| `api-keys quota <id>` | 读取 API Key 各 Profile 的配额窗口和用量 | `<id>` |
| `api-keys templates` | 读取 Profile 模板 | `--first`、`--project-id`、`--name` |

```powershell
axonhubclient --json api-keys list --status enabled
axonhubclient --json api-keys quota <api-key-id>
axonhubclient --json api-keys templates --project-id <project-id>
```

`api-keys list` 默认追加 `typeNotIn: ["noauth"]`；显式传入 `--type` 时按指定类型查询。

## Models

### 只读命令

| 命令 | 用途 | 关键参数 |
| --- | --- | --- |
| `models list` | 分页读取模型 | `--first`、`--after`、`--status`、`--type`、`--model-id`、`--name` |
| `models get <id>` | 读取单个模型 | `--model-id` 可按 modelID 查询 |
| `models rules list <id>` | 读取模型关联规则 | `--model-id` |
| `models rules preview <id>` | 预览模型关联渠道 | `--model-id`、`--associations-json`、`--associations-file` |
| `models rules unassociated` | 检测未关联到模型配置的渠道模型入口 | 无 |
| `models fastest` | 读取最快模型吞吐排行 | `--window`、`--limit` |

### 写操作

| 命令 | 用途 | 确认参数 |
| --- | --- | --- |
| `models create` | 创建模型 | `--confirm` |
| `models create-many` | 批量创建模型 | `--confirm` |
| `models update <id>` | 使用 `UpdateModelInput` 更新模型 | `--confirm` |
| `models status <id> <enabled\|disabled\|archived>` | 设置单个模型状态 | `--confirm` |
| `models enable <ids...>` | 批量启用模型 | `--confirm` |
| `models disable <ids...>` | 批量禁用模型 | `--confirm` |
| `models archive <ids...>` | 批量归档模型 | `--confirm` |
| `models recover <ids...>` | 批量恢复模型为 enabled | `--confirm` |
| `models delete <ids...>` | 删除模型，高风险不可逆 | `--confirm` |
| `models rules replace <id>` | 整组替换 `settings.associations` | `--confirm` |
| `models rules add/remove/enable/disable/reorder <id>` | 细粒度编辑关联规则 | `--confirm` |

```powershell
axonhubclient models create --input-file docs\examples\model.create.json
axonhubclient models create-many --input-file docs\examples\models.bulk-create.json --confirm
axonhubclient models update <model-entity-id> --input-file docs\examples\model.update.json --confirm
axonhubclient models status <model-entity-id> enabled --confirm
axonhubclient models rules replace <model-entity-id> --associations-file docs\examples\model.associations.json --confirm
```

细粒度规则编辑使用 1-based 索引，并在写回前归一化 `priority`：

```powershell
axonhubclient models rules add <model-entity-id> --association-file docs\examples\model.rule.json --position 1 --confirm
axonhubclient models rules disable <model-entity-id> --index 1 --confirm
axonhubclient models rules reorder <model-entity-id> --from-index 2 --to-index 1 --confirm
```

`models create` 不接受 `status`；创建后如需启用，使用 `models enable` 或 `models status <id> enabled`。

## Requests

`requests` 是只读排障资源。列表默认只读取摘要、用量摘要和最近执行摘要；单条详情默认仍不读取请求/响应正文。

| 命令 | 用途 | 关键参数 |
| --- | --- | --- |
| `requests list` | 分页读取请求日志摘要 | `--first`、`--after`、`--status`、`--source`、`--channel-id`、`--project-id`、`--model`、`--trace-id`、`--created-after`、`--created-before` |
| `requests get <id>` | 读取单个请求日志 | `--include-content` |
| `requests executions <id>` | 读取请求对应的上游执行记录摘要 | `--first`、`--after`、`--status`、`--channel-id` |

```powershell
axonhubclient --json requests list --status failed --first 20
axonhubclient --json requests list --project-id <project-id> --created-after "2026-06-01T00:00:00Z"
axonhubclient --json requests get <request-id> --include-content
```

`--include-content` 会额外读取 `requestHeaders`、`requestBody`、`responseBody` 和 `responseChunks`，排障完成后应避免把输出保存进仓库。

## Usage

| 命令 | 用途 | 关键参数 |
| --- | --- | --- |
| `usage overview` | 读取 dashboardOverview | 无 |
| `usage requests-by-channel` | 按渠道统计请求量 | `--window` |
| `usage requests-by-model` | 按模型统计请求量 | `--window` |
| `usage tokens-by-channel` | 按渠道统计 token | `--window` |
| `usage tokens-by-model` | 按模型统计 token | `--window` |
| `usage cost-by-channel` | 按渠道统计成本 | `--window` |
| `usage cost-by-model` | 按模型统计成本 | `--window` |
| `usage daily` | 读取日聚合请求统计 | 无 |
| `usage token-stats` | 读取 token 聚合统计 | 无 |
| `usage channel-success-rates` | 读取渠道成功率 | `--window`、`--limit` |
| `usage logs list` | 分页读取用量日志 | `--first`、`--after`、`--source`、`--channel-id`、`--project-id`、`--request-id`、`--model`、`--created-after`、`--created-before` |
| `usage logs get <id>` | 读取单个用量日志 | `<id>` |

```powershell
axonhubclient --json usage overview
axonhubclient --json usage tokens-by-model --window month
axonhubclient --json usage logs list --request-id <request-id>
```

## Traces

| 命令 | 用途 | 关键参数 |
| --- | --- | --- |
| `traces list` | 分页读取 Trace | `--first`、`--after`、`--trace-id`、`--thread-id`、`--request-id`、`--project-id`、`--created-after`、`--created-before` |
| `traces get <id>` | 读取单个 Trace 详情和 `rawRootSegment` | `<id>` |

```powershell
axonhubclient --json traces list --request-id <request-id>
axonhubclient --json traces list --project-id <project-id> --created-after "2026-06-01T00:00:00Z"
axonhubclient --json traces get <trace-entity-id>
```

## Diagnostics

| 命令 | 用途 | 关键参数 |
| --- | --- | --- |
| `diagnostics channel-health` | 聚合渠道配置、成功率、最近失败请求和错误原因 | `--channel-id`、`--limit`、`--window`、`--min-success-rate`、`--recent-failures` |

```powershell
axonhubclient --json diagnostics channel-health --limit 10
```

## Smoke

| 命令 | 用途 | 写操作 |
| --- | --- | --- |
| `smoke read-only` | 对真实实例执行只读 smoke test 流程 | 否 |

```powershell
axonhubclient --json smoke read-only
```

该流程依次执行 `auth status`、`auth whoami`、`inventory summary`、`requests list --first 5`、`usage logs list --first 5`、`traces list --first 5` 和 `diagnostics channel-health --limit 10`。它不会提交 mutation；后续如需写入型 smoke test，应使用专用测试资源并另行设计确认流程。

## 示例文件索引

- `docs/examples/channel.bulk-create.json`
- `docs/examples/channels.import.json`
- `docs/examples/channel.update.json`
- `docs/examples/channel.bulk-ordering.json`
- `docs/examples/channel.endpoints.json`
- `docs/examples/model.create.json`
- `docs/examples/models.bulk-create.json`
- `docs/examples/model.update.json`
- `docs/examples/model.associations.json`
- `docs/examples/model.rule.json`

