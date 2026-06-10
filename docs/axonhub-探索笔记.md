# AxonHub 探索笔记

本文档记录目前针对 AxonHub 源码和线上入口的探索结论，供后续实现 `AxonHubClient`、CLI 及其配套 Skill / Agent 约定时参考。

探索时间：2026-06-09

## 当前目标

本项目的长期目标是让 Agent 拥有管理 AxonHub 实例的能力。

当前项目已经从“只读资产盘点”进入“安全受控管理闭环”阶段：

- 实现一个通用 `AxonHubClient`，通过 `axonhubclient auth login` 登录任意 AxonHub 实例，并使用当前用户默认 session 执行后续命令。
- 通过 Admin Token 模式调用真实 HTTP 与 GraphQL 接口。
- 读操作用于资产盘点和排障，可直接执行。
- 写操作默认 dry-run，必须显式 `--confirm` 才提交真实 mutation；删除和清理类高风险动作也使用统一 `--confirm`，但 dry-run 输出必须明确标记不可逆或高风险影响。
- 当前已覆盖：
  - 渠道 / 供应商视图。
  - 模型。
  - 用量和 dashboard 统计。
  - 渠道导入、更新、启停、排序、endpoint 保存、验证、模型同步、归档、恢复、删除。
  - 渠道内 API key 禁用、启用、启用全部、启用选中、清理 disabled key 记录。
- 仍然避开 API key 明文读取、复制、显示、导出和 rotate 等敏感操作。

## 上游源码参考

本仓库不再保存 AxonHub 上游源码 submodule。后续如需复核接口事实，可临时查阅上游仓库中的这些位置：

- `internal/server/routes.go`：后端路由注册。
- `internal/server/gql/*.graphql`：后台 Admin GraphQL schema。
- `internal/server/gql/openapi/openapi.graphql`：程序化 OpenAPI GraphQL schema。
- `frontend/src/gql/graphql.ts`：前端后台 GraphQL 客户端。
- `frontend/src/features/*/data/*.ts`：前端页面实际使用的 GraphQL query / mutation。
- `examples/openapi/README.md`：OpenAPI service account 使用说明。

## 已知 API 面

AxonHub 目前至少有三类 API 面。

### 1. 公共后台端点

路由来源：`internal/server/routes.go`

- `GET /health`
- `GET /favicon`
- `GET /admin/system/status`
- `POST /admin/system/initialize`
- `POST /admin/auth/signin`

这些端点不走后台 GraphQL。

其中 `POST /admin/auth/signin` 用于邮箱密码登录，成功后返回用户信息和 JWT token。

### 2. 后台 Admin GraphQL

端点：

- `POST /admin/graphql`

前端来源：

- `frontend/src/gql/graphql.ts`

认证方式：

- 请求头使用 `Authorization: Bearer <admin_jwt>`。
- 前端从本地 storage 读取 token 后带到 `/admin/graphql`。

用途：

- 完整后台管理能力基本都在这个接口里，包括渠道、模型、用量、项目、用户、角色、系统配置、请求日志、Trace 等。

### 运维排障相关 GraphQL 映射

P1 运维排障能力已按上游 Admin GraphQL 和前端页面 query 映射到 CLI：

- 请求日志：
  - 顶层连接：`requests(first, after, orderBy, where)`。
  - 单条详情：`node(id) { ... on Request }`。
  - 执行记录：`Request.executions(first, after, orderBy, where)`。
  - 默认只取请求摘要、用量摘要和 execution 摘要；`requestHeaders`、`requestBody`、`responseBody`、`responseChunks` 只在 CLI 显式 `requests get --include-content` 时读取。
- 用量日志：
  - 顶层连接：`usageLogs(first, after, orderBy, where)`。
  - 单条详情：`node(id) { ... on UsageLog }`。
  - 读取 token、成本、来源、格式、requestID、channel 摘要和 `costItems`，不选择 API Key 明文字段 `key`。
- Trace：
  - 顶层连接：`traces(first, after, orderBy, where)`。
  - 单条详情：`node(id) { ... on Trace }`，包含 `usageMetadata`、`thread`、completed request count 和 `rawRootSegment`。
  - 按请求筛选使用 `TraceWhereInput.hasRequestsWith: [{ id: <request-id> }]`；按项目筛选使用 `projectID`；时间窗口使用 `createdAtGTE` / `createdAtLTE`。
- 渠道健康诊断：
  - 聚合 `channels list/get`、`channelSuccessRates` 和最近失败 `requests`。
  - 输出 `healthy` / `warning` / `critical` 级别、低成功率、渠道未启用、错误信息、缺少 supported models 和最近失败请求。

结论：

- 如果 `AxonHubClient` 要覆盖渠道、模型、用量等后台资产，应优先实现 Admin GraphQL 客户端。
- 该客户端需要支持传入 admin JWT。
- 当前 CLI 通过 `auth login` 获取 admin JWT，并把默认 session 保存到当前用户配置目录；不会保存密码。

### 3. 程序化 OpenAPI GraphQL

端点：

- `POST /openapi/v1/graphql`
- `GET /openapi/v1/playground`

源码来源：

- `internal/server/gql/openapi/openapi.graphql`
- `examples/openapi/README.md`

认证方式：

- 请求头使用 `Authorization: Bearer <service_account_api_key>`。
- 只有 `service_account` 类型 API Key 可以访问。
- 普通 user 类型 API Key 会被拒绝。

限制：

- `/openapi/v1/graphql` 只支持 POST。
- GET transport 已被禁用，避免明文 key 或 variables 经 URL 泄漏到代理日志、浏览器历史等位置。

当前公开能力主要集中在 API Key profile 和 quota usage：

- `createLLMAPIKey(name)`
- `updateAPIKeyProfiles(id, input)`
- `loadApiKeyProfileTemplate(input)`
- `apiKeyQuotaUsages(apiKeyId, key)`

结论：

- OpenAPI 适合作为后续“自动化服务账号”能力入口。
- 但它目前不是完整后台管理 API，不能覆盖当前管理闭环所需的渠道、模型、dashboard 用量和写操作。

## 认证设计建议

`AxonHubClient` 当前收敛为 Admin Token 模式；OpenAPI service account 仅作为后续参考。

### Admin Token 模式

用途：

- 调用 `/admin/graphql`。
- 读取渠道、模型、用量、请求、Trace、项目等后台资产。

当前 CLI 入口：

- `axonhubclient auth login` 登录并保存默认 session。
- 后续命令自动读取默认 session。

请求头：

```text
Authorization: Bearer <admin_jwt>
Content-Type: application/json
```

### Service Account Key 模式（后续参考）

用途：

- 调用 `/openapi/v1/graphql`。
- 管理或查询 OpenAPI 暴露的 API Key profile / quota 子集。

当前项目不把该模式作为主实现路径。

请求头：

```text
Authorization: Bearer <service_account_api_key>
Content-Type: application/json
```

## 已映射接口

### 身份和状态

候选命令：

```bash
axonhubclient auth status
axonhubclient auth whoami
```

接口映射：

- `auth status` -> `GET /admin/system/status`
- `auth whoami` -> Admin GraphQL `me`

相关源码：

- `frontend/src/gql/users.ts`
- `frontend/src/lib/api-client.ts`

### 渠道 / 供应商视图

候选命令：

```bash
axonhubclient channels list
axonhubclient channels summary
axonhubclient channels tags
axonhubclient channels count-by-type
axonhubclient channels probe-data
axonhubclient channels success-rates
axonhubclient channels fastest
```

接口映射：

- `queryChannels(input)`：分页、筛选渠道。
- `allChannelSummarys(includeArchived)`：渠道摘要。
- `allChannelTags`：全部渠道标签。
- `countChannelsByType(input)`：按 channel type 计数，可作为供应商视图基础。
- `channelProbeData(input)`：渠道探测数据。
- `channelSuccessRates(timeWindow, limit)`：渠道成功率。
- `fastestChannels(input)`：最快渠道统计。

相关源码：

- `internal/server/gql/axonhub.graphql`
- `internal/server/gql/dashboard.graphql`
- `internal/server/gql/channel_probe.graphql`
- `frontend/src/features/channels/data/channels.ts`
- `frontend/src/features/dashboard/data/dashboard.ts`
- `frontend/src/features/dashboard/data/fastest-performers.ts`

注意：

- 源码里没有发现独立的 `Provider` 实体。
- “供应商”更像是渠道的 `type` 视图，例如 OpenAI、Anthropic、Gemini、DeepSeek 等。
- CLI 可以提供 `providers` 作为 `channels count-by-type` 或渠道 type 统计的别名，但底层仍应基于 channel。

### 模型

候选命令：

```bash
axonhubclient models list
axonhubclient models get <id>
axonhubclient models channels <id>
axonhubclient models rules unassociated
axonhubclient models fastest
```

接口映射：

- `models(...)`：Ent 生成的模型分页查询；当前 `models list` 和 `models get --model-id` 基于它实现。
- `node(id)` + `... on Model`：按实体 ID 读取单个模型。
- `queryModels(input)`：轻量模型列表查询，前端在模型选择器中使用；当前 CLI 暂未单独包装。
- `queryModelChannelConnections(associations)`：模型与渠道连接关系；`models channels <id>` 默认读取模型 `settings.associations` 后调用它，也支持直接传入 `--associations-json` 预览。
- `queryUnassociatedChannels`：未关联渠道。
- `fastestModels(input)`：最快模型统计。

相关源码：

- `internal/server/gql/model.graphql`
- `frontend/src/gql/models.ts`
- `frontend/src/features/models/data/models.ts`
- `frontend/src/features/dashboard/data/fastest-performers.ts`

### 用量和 Dashboard 统计

候选命令：

```bash
axonhubclient usage overview
axonhubclient usage requests-by-channel
axonhubclient usage requests-by-model
axonhubclient usage requests-by-api-key
axonhubclient usage tokens-by-channel
axonhubclient usage tokens-by-model
axonhubclient usage tokens-by-api-key
axonhubclient usage cost-by-channel
axonhubclient usage cost-by-model
axonhubclient usage cost-by-api-key
axonhubclient usage daily
axonhubclient usage token-stats
```

接口映射：

- `dashboardOverview`
- `requestStats`
- `requestStatsByChannel(timeWindow)`
- `requestStatsByModel(timeWindow)`
- `requestStatsByAPIKey(timeWindow)`
- `tokenStatsByChannel(timeWindow)`
- `tokenStatsByModel(timeWindow)`
- `tokenStatsByAPIKey(timeWindow)`
- `costStatsByChannel(timeWindow)`
- `costStatsByModel(timeWindow)`
- `costStatsByAPIKey(timeWindow)`
- `dailyRequestStats`
- `topRequestsProjects`
- `tokenStats`
- `channelSuccessRates(timeWindow, limit)`
- `modelPerformanceStats`
- `channelPerformanceStats`

相关源码：

- `internal/server/gql/dashboard.graphql`
- `frontend/src/features/dashboard/data/dashboard.ts`

### API Key / Profile 只读盘点

当前仍不主动读取 API Key 明文，也不点击或调用显示密钥类能力。

已实现只读命令：

```bash
axonhubclient api-keys list
axonhubclient api-keys get <api-key-id>
axonhubclient api-keys quota <api-key-id>
axonhubclient api-keys templates
```

接口映射：

- Admin GraphQL：`apiKeys(first, after, orderBy, where)`
- Admin GraphQL：`node(id) { ... on APIKey }`
- Admin GraphQL：`apiKeyQuotaUsages(apiKeyId: ID!)`
- Admin GraphQL：`apiKeyProfileTemplates(first, where)`
- OpenAPI GraphQL：`apiKeyQuotaUsages(apiKeyId: ID, key: String)`

注意：

- Admin GraphQL 的 API Key 查询已在 client 内裁剪字段，不选择明文字段 `key`。
- `api-keys list` 默认排除 `noauth` 类型；显式传入 `--type` 时按指定类型查询。
- OpenAPI 版本支持通过明文 key 查询，但 CLI 当前未实现，也不应默认鼓励传入明文 key。
- CLI 当前不主动读取或展示明文 key；若未来扩展 API Key 主体写操作，应继续保持默认 dry-run 和脱敏输出。

## 后续完整能力清单

下面这些接口存在于源码或前端调用中。渠道主体写操作和渠道内 API key 状态管理已经进入当前实现；其余能力后续可以按风险逐步实现。

### 渠道写操作

- `createChannel`
- `bulkCreateChannels`
- `updateChannel`
- `saveChannelEndpoints`
- `updateChannelStatus`
- `deleteChannel`
- `bulkArchiveChannels`
- `bulkDisableChannels`
- `bulkEnableChannels`
- `bulkRecoverChannels`
- `bulkDeleteChannels`
- `testChannel`
- `testChannelAPIKeys`
- `bulkImportChannels`
- `bulkUpdateChannelOrdering`
- `syncChannelModels`

当前 `AxonHubClient` 已实现其中一部分安全闭环能力：

- `createChannel` / `updateChannel`
- `updateChannelStatus`
- `saveChannelEndpoints`
- `testChannel` / `testChannelAPIKeys`
- `syncChannelModels`
- `bulkArchiveChannels` / `bulkRecoverChannels` / `bulkDeleteChannels`

这些 CLI 命令默认 dry-run，必须显式传入 `--confirm` 才会执行 mutation。`bulkDeleteChannels` 属于不可逆高风险操作，dry-run 输出会明确标记风险。

当前仓库的渠道写操作已覆盖：

- `createChannel` / `bulkCreateChannels` / `bulkImportChannels`
- `updateChannel`
- `updateChannelStatus`
- `bulkDisableChannels` / `bulkEnableChannels`
- `saveChannelEndpoints`
- `testChannel` / `testChannelAPIKeys`
- `bulkUpdateChannelOrdering`
- `syncChannelModels`
- `bulkArchiveChannels` / `bulkRecoverChannels` / `bulkDeleteChannels`

### 渠道模型同步与 `手动` 标记

源码调查结论：

- 网站上的 `手动` 不是渠道 `tags`，而是前端根据渠道字段 `manualModels` 渲染的模型徽标。
- 上游 `Channel` 字段包含 `supportedModels`、`manualModels`、`autoSyncSupportedModels` 和 `autoSyncModelPattern`。
- 前端手动输入/批量输入模型时，会同时加入 `supportedModels` 和 `manualModels`；从 provider 拉取的模型加入 `supportedModels` 时，不会加入 `manualModels`。
- `syncChannelModels(channelID, pattern)` 只返回 `channelID` 和 `supportedModels`。后端同步时读取已有 `manualModels`，拉取 provider 模型后执行 `manualModels + fetchedModels` 去重合并，只更新 `supportedModels`，保留 `manualModels` 不变。
- 周期同步任务注册为 `channel-model-sync`，cron 为 UTC 每小时第 11 分钟触发一次；实际是否执行还会按系统配置的 `ChannelSetting.AutoSync.Frequency` 对齐判断，默认频率为 `1h`，可为 `1h` / `6h` / `1d`。
- 周期同步只查询 `status=enabled` 且 `autoSyncSupportedModels=true` 的渠道。

`AxonHubClient` 修复结论：

- `channels create` 在未显式传入 `--manual-model` 时，默认写入 `manualModels=[]`。
- 自动发现得到的模型只写入 `supportedModels`，不会在网站上显示为 `手动`。
- 只有用户显式传入 `--manual-model` 时，才会写入 `manualModels` 并触发网站的 `手动` 徽标。

### 渠道 API Key 管理

- `disableChannelAPIKey`
- `enableChannelAPIKey`
- `enableAllChannelAPIKeys`
- `enableSelectedChannelAPIKeys`
- `deleteDisabledChannelAPIKeys`

当前已实现 CLI 包装：

- `channels keys disable <channel-id> --key sk-xxx`
- `channels keys enable <channel-id> --key sk-xxx`
- `channels keys enable-all <channel-id>`
- `channels keys enable-selected <channel-id> --key sk-a --key sk-b`
- `channels keys prune-disabled <channel-id> --key '["sk-a","sk-b"]'`

安全约束：

- 这些命令默认 dry-run，只有传入 `--confirm` 才提交 mutation。
- 单个或选中 key 通过 `--key` 直接传入。
- `--key` 支持重复传入，单次也可为逗号/换行分隔文本或 JSON 字符串数组。
- dry-run 输出会对 `key` / `keys` 脱敏。
- `keys prune-disabled` 属于高风险清理操作，执行时使用统一 `--confirm`。
- 当前不实现读取或展示 `disabledAPIKeys.key` 的命令，避免通过 client 暴露密钥明文。

### 模型写操作

- `createModel`
- `bulkCreateModels`
- `updateModel`
- `deleteModel`
- `updateModelStatus`
- `bulkArchiveModels`
- `bulkDisableModels`
- `bulkEnableModels`
- `bulkDeleteModels`

当前 client 已实现上述核心 mutation：

- `models create` / `models create-many` / `models update` 通过 JSON 输入提交 `CreateModelInput` / `UpdateModelInput`，默认 dry-run。
- `models status` 调用 `updateModelStatus`；`models enable` / `disable` / `archive` / `recover` 调用对应批量状态 mutation，其中 `recover` 复用 `bulkEnableModels`。
- `models delete` 根据 ID 数量调用 `deleteModel` 或 `bulkDeleteModels`，属于不可逆高风险操作，执行时使用统一 `--confirm`。
- `models rules list` 读取 `settings.associations`；`models rules replace` 只替换 `settings.associations`，保留其它模型 settings 字段。
- `models rules add/remove/enable/disable/reorder` 支持按 1-based 索引细粒度编辑关联规则；编辑时按上游前端一致的 `priority` 升序视图定位规则，并在写回前把 `priority` 归一化为 `0..n-1`。

### API Key 管理

- `apiKeys`
- `node(id) { ... on APIKey }`
- `apiKeyQuotaUsages`
- `apiKeyProfileTemplates`
- `createAPIKey`
- `updateAPIKey`
- `updateAPIKeyStatus`
- `updateAPIKeyProfiles`
- `rotateAPIKey`
- `bulkDisableAPIKeys`
- `bulkEnableAPIKeys`
- `bulkArchiveAPIKeys`
- `createApiKeyProfileTemplate`
- `updateApiKeyProfileTemplate`
- `deleteApiKeyProfileTemplate`
- `loadApiKeyProfileTemplate`

安全要求：

- 默认不输出 key 明文。
- `rotateAPIKey` 属于高风险操作，必须强确认。
- `createAPIKey` 如果服务端返回明文 key，应默认脱敏显示，除非用户明确要求一次性显示。

### 项目、用户、角色

- `projects`
- `createProject`
- `updateProject`
- `updateProjectStatus`
- `updateProjectProfiles`
- `deleteProject`
- `users`
- `createUser`
- `updateUser`
- `updateUserStatus`
- `deleteUser`
- `roles`
- `createRole`
- `updateRole`
- `deleteRole`
- `bulkDeleteRoles`
- `addUserToProject`
- `updateProjectUser`
- `removeUserFromProject`

### 请求、日志、Trace、线程

- `requests`
- `request`
- `usageLogs`
- `usageLog`
- `traces`
- `trace`
- `threads`
- `thread`
- `executions`

这部分适合后续做运维排障能力。

### 系统配置

- `updateBrandSettings`
- `updateStoragePolicy`
- `updateRetryPolicy`
- `updateWebhookNotifierConfig`
- `updateSystemModelSettings`
- `updateDefaultDataStorage`
- `updateSystemChannelSettings`
- `updateSystemGeneralSettings`
- `updateVideoStorageSettings`
- `updateQuotaEnforcementSettings`
- `updateSecuritySettings`
- `previewGcCleanup`
- `triggerGcCleanup`
- `getCacheDiagnostics`
- `clearCache`
- `backup`
- `restore`
- `updateAutoBackupSettings`

这些多为高影响系统操作，后续实现时应默认只读，写操作需要强确认。

## 客户端设计建议

### Python 包结构建议

```text
axonhub_client/
  __init__.py
  client.py
  transport.py
  queries.py
  discovery.py
  cli.py
tests/
docs/
pyproject.toml
```

### Client 分层

建议拆成三层：

- `GraphQLTransport`：负责 HTTP POST、headers、错误解析。
- `AdminClient`：封装 `/admin/graphql` 的后台接口。
- `OpenAPIClient`：封装 `/openapi/v1/graphql` 的 service account 接口。

### 错误处理

GraphQL 响应需要处理：

- HTTP 401 / 403。
- 非 JSON 响应。
- `errors` 字段。
- `extensions.code == UNAUTHENTICATED`。

这些行为可参考：

- `frontend/src/gql/graphql.ts`

## 安全边界

默认规则：

- 不读取、不展示 API Key 明文。
- 不把 token 或 key 写入仓库。
- 不把 token 或 key 写入日志。
- 不在命令行参数中鼓励传明文 key。
- 所有 mutation 默认视为写操作。
- 写操作实现前必须有 `--yes` 或交互确认设计，但 Agent 执行时仍应先向用户说明具体影响。

当前实现已经允许安全受控的 mutation 包装。后续新增 mutation 时必须继续维持：默认 dry-run、明确 `--confirm`、高风险 dry-run 摘要、凭证脱敏、避免把密钥写入仓库或日志。

## 待确认问题

- 后续是否需要支持 `POST /admin/auth/signin` 直接登录获取 admin JWT。
- admin JWT 在前端 storage 中的 key 名称是否要通过 Chrome 工具观察确认。
- 是否需要为 `providers` 提供一等命令，还是只作为 `channels` 的视图别名。
- 输出格式是否固定为 JSON，还是同时支持表格 / Markdown。

