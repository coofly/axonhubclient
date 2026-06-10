"""Admin GraphQL query / mutation 集合。

读取和写入后的返回字段刻意不请求 Channel.credentials、DisabledAPIKey.key 等敏感字段。
"""

ME_QUERY = """
query Me {
  me {
    id
    email
    firstName
    lastName
    isOwner
    scopes
    preferLanguage
    avatar
    hasPassword
    roles {
      name
    }
    projects {
      projectID
      isOwner
      scopes
      roles {
        name
      }
    }
  }
}
"""

CHANNEL_FIELDS = """
id
createdAt
updatedAt
type
baseURL
name
status
policies {
  stream
}
supportedModels
autoSyncSupportedModels
autoSyncModelPattern
manualModels
tags
defaultTestModel
settings {
  extraModelPrefix
  modelMappings {
    from
    to
  }
  autoTrimedModelPrefixes
  hideOriginalModels
  hideMappedModels
  lowercaseModelId
  transformOptions {
    forceArrayInstructions
    forceArrayInputs
    replaceDeveloperRoleWithSystem
  }
  passThroughUserAgent
  passThroughBody
  rateLimit {
    rpm
    tpm
    maxConcurrent
    queueSize
    queueTimeoutMs
  }
}
orderingWeight
errorMessage
remark
defaultEndpoints {
  apiFormat
  path
  baseURL
  transport
}
endpoints {
  apiFormat
  path
  baseURL
  transport
}
liveLimiterStats {
  inFlight
  waiting
  capacity
  queueSize
}
"""

QUERY_CHANNELS = f"""
query QueryChannels($input: QueryChannelInput!) {{
  queryChannels(input: $input) {{
    edges {{
      node {{
        {CHANNEL_FIELDS}
      }}
      cursor
    }}
    pageInfo {{
      hasNextPage
      hasPreviousPage
      startCursor
      endCursor
    }}
    totalCount
  }}
}}
"""

GET_CHANNEL = f"""
query GetChannel($id: ID!) {{
  node(id: $id) {{
    ... on Channel {{
      {CHANNEL_FIELDS}
    }}
  }}
}}
"""

ALL_CHANNEL_SUMMARYS = """
query GetAllChannelSummarys($includeArchived: Boolean) {
  allChannelSummarys(includeArchived: $includeArchived) {
    id
    name
    type
    status
    baseURL
    orderingWeight
    tags
    endpoints {
      apiFormat
      path
      baseURL
      transport
    }
    allModelEntries {
      requestModel
      actualModel
      source
    }
  }
}
"""

ALL_CHANNEL_TAGS = """
query AllChannelTags {
  allChannelTags
}
"""

COUNT_CHANNELS_BY_TYPE = """
query CountChannelsByType($input: CountChannelsByTypeInput!) {
  countChannelsByType(input: $input) {
    type
    count
  }
}
"""

CREATE_CHANNEL = f"""
mutation CreateChannel($input: CreateChannelInput!) {{
  createChannel(input: $input) {{
    {CHANNEL_FIELDS}
  }}
}}
"""

BULK_CREATE_CHANNELS = f"""
mutation BulkCreateChannels($input: BulkCreateChannelsInput!) {{
  bulkCreateChannels(input: $input) {{
    {CHANNEL_FIELDS}
  }}
}}
"""

BULK_IMPORT_CHANNELS = f"""
mutation BulkImportChannels($input: BulkImportChannelsInput!) {{
  bulkImportChannels(input: $input) {{
    success
    created
    failed
    errors
    channels {{
      {CHANNEL_FIELDS}
    }}
  }}
}}
"""

UPDATE_CHANNEL = f"""
mutation UpdateChannel($id: ID!, $input: UpdateChannelInput!) {{
  updateChannel(id: $id, input: $input) {{
    {CHANNEL_FIELDS}
  }}
}}
"""

UPDATE_CHANNEL_STATUS = f"""
mutation UpdateChannelStatus($id: ID!, $status: ChannelStatus!) {{
  updateChannelStatus(id: $id, status: $status) {{
    {CHANNEL_FIELDS}
  }}
}}
"""

SAVE_CHANNEL_ENDPOINTS = f"""
mutation SaveChannelEndpoints($input: SaveChannelEndpointsInput!) {{
  saveChannelEndpoints(input: $input) {{
    {CHANNEL_FIELDS}
  }}
}}
"""

DELETE_CHANNEL = """
mutation DeleteChannel($id: ID!) {
  deleteChannel(id: $id)
}
"""

TEST_CHANNEL = """
mutation TestChannel($input: TestChannelInput!) {
  testChannel(input: $input) {
    latency
    success
    message
    error
  }
}
"""

TEST_CHANNEL_API_KEYS = """
mutation TestChannelAPIKeys($channelID: ID!, $modelID: String) {
  testChannelAPIKeys(channelID: $channelID, modelID: $modelID) {
    channelID
    total
    successCount
    failedCount
    results {
      keyPrefix
      success
      latency
      error
      disabled
    }
  }
}
"""

API_KEY_PROFILE_FIELDS = """
name
modelMappings {
  from
  to
}
channelIDs
channelTags
channelTagsMatchMode
modelIDs
loadBalanceStrategy
quota {
  requests
  totalTokens
  cost
  period {
    type
    pastDuration {
      value
      unit
    }
    calendarDuration {
      unit
    }
  }
}
"""

API_KEY_FIELDS_SAFE = f"""
id
createdAt
updatedAt
name
type
status
scopes
profiles {{
  activeProfile
  profiles {{
    {API_KEY_PROFILE_FIELDS}
  }}
}}
"""

API_KEYS = """
query GetAPIKeys(
  $first: Int
  $after: Cursor
  $orderBy: APIKeyOrder
  $where: APIKeyWhereInput
) {
  apiKeys(first: $first, after: $after, orderBy: $orderBy, where: $where) {
    edges {
      node {
        id
        createdAt
        updatedAt
        name
        type
        status
        scopes
      }
      cursor
    }
    pageInfo {
      hasNextPage
      hasPreviousPage
      startCursor
      endCursor
    }
    totalCount
  }
}
"""

GET_API_KEY = f"""
query GetAPIKey($id: ID!) {{
  node(id: $id) {{
    ... on APIKey {{
      {API_KEY_FIELDS_SAFE}
    }}
  }}
}}
"""

API_KEY_QUOTA_USAGES = """
query APIKeyQuotaUsages($apiKeyId: ID!) {
  apiKeyQuotaUsages(apiKeyId: $apiKeyId) {
    profileName
    quota {
      requests
      totalTokens
      cost
      period {
        type
        pastDuration {
          value
          unit
        }
        calendarDuration {
          unit
        }
      }
    }
    window {
      start
      end
    }
    usage {
      requestCount
      totalTokens
      totalCost
    }
  }
}
"""

API_KEY_PROFILE_TEMPLATES = f"""
query APIKeyProfileTemplates($first: Int, $where: APIKeyProfileTemplateWhereInput) {{
  apiKeyProfileTemplates(first: $first, where: $where) {{
    edges {{
      node {{
        id
        createdAt
        updatedAt
        name
        description
        projectID
        profile {{
          {API_KEY_PROFILE_FIELDS}
        }}
        project {{
          id
          name
        }}
      }}
      cursor
    }}
    pageInfo {{
      hasNextPage
      hasPreviousPage
      startCursor
      endCursor
    }}
    totalCount
  }}
}}
"""

SYNC_CHANNEL_MODELS = """
mutation SyncChannelModels($channelID: ID!, $pattern: String) {
  syncChannelModels(channelID: $channelID, pattern: $pattern) {
    channelID
    supportedModels
  }
}
"""

BULK_ARCHIVE_CHANNELS = """
mutation BulkArchiveChannels($ids: [ID!]!) {
  bulkArchiveChannels(ids: $ids)
}
"""

BULK_DISABLE_CHANNELS = """
mutation BulkDisableChannels($ids: [ID!]!) {
  bulkDisableChannels(ids: $ids)
}
"""

BULK_ENABLE_CHANNELS = """
mutation BulkEnableChannels($ids: [ID!]!) {
  bulkEnableChannels(ids: $ids)
}
"""

BULK_RECOVER_CHANNELS = """
mutation BulkRecoverChannels($ids: [ID!]!) {
  bulkRecoverChannels(ids: $ids)
}
"""

BULK_DELETE_CHANNELS = """
mutation BulkDeleteChannels($ids: [ID!]!) {
  bulkDeleteChannels(ids: $ids)
}
"""

BULK_UPDATE_CHANNEL_ORDERING = """
mutation BulkUpdateChannelOrdering($input: BulkUpdateChannelOrderingInput!) {
  bulkUpdateChannelOrdering(input: $input) {
    success
    updated
    channels {
      id
      createdAt
      updatedAt
      type
      baseURL
      name
      status
      supportedModels
      autoSyncSupportedModels
      autoSyncModelPattern
      manualModels
      tags
      defaultTestModel
      orderingWeight
      remark
      defaultEndpoints {
        apiFormat
        path
        baseURL
        transport
      }
      endpoints {
        apiFormat
        path
        baseURL
        transport
      }
    }
  }
}
"""

DISABLE_CHANNEL_API_KEY = """
mutation DisableChannelAPIKey($channelID: ID!, $key: String!) {
  disableChannelAPIKey(channelID: $channelID, key: $key)
}
"""

ENABLE_CHANNEL_API_KEY = """
mutation EnableChannelAPIKey($channelID: ID!, $key: String!) {
  enableChannelAPIKey(channelID: $channelID, key: $key)
}
"""

ENABLE_ALL_CHANNEL_API_KEYS = """
mutation EnableAllChannelAPIKeys($channelID: ID!) {
  enableAllChannelAPIKeys(channelID: $channelID)
}
"""

ENABLE_SELECTED_CHANNEL_API_KEYS = """
mutation EnableSelectedChannelAPIKeys($channelID: ID!, $keys: [String!]!) {
  enableSelectedChannelAPIKeys(channelID: $channelID, keys: $keys)
}
"""

DELETE_DISABLED_CHANNEL_API_KEYS = """
mutation DeleteDisabledChannelAPIKeys($channelID: ID!, $keys: [String!]!) {
  deleteDisabledChannelAPIKeys(channelID: $channelID, keys: $keys) {
    success
    message
  }
}
"""

MODEL_SETTINGS_FIELDS = """
disableDeveloperSettingsInheritance
associations {
  type
  priority
  disabled
  when {
    enabled
    condition {
      type
      logic
      field
      operator
      value
      conditions {
        type
        logic
        field
        operator
        value
        conditions {
          type
          logic
          field
          operator
          value
        }
      }
    }
  }
  channelModel {
    channelId
    modelId
  }
  channelRegex {
    channelId
    pattern
  }
  regex {
    pattern
    exclude {
      channelNamePattern
      channelIds
      channelTags
    }
  }
  modelId {
    modelId
    exclude {
      channelNamePattern
      channelIds
      channelTags
    }
  }
  channelTagsModel {
    channelTags
    modelId
  }
  channelTagsRegex {
    channelTags
    pattern
  }
}
"""

MODEL_FIELDS = f"""
id
createdAt
updatedAt
developer
modelID
icon
type
name
group
modelCard {{
  reasoning {{
    supported
    default
  }}
  toolCall
  temperature
  modalities {{
    input
    output
  }}
  vision
  cost {{
    input
    output
    cacheRead
    cacheWrite
  }}
  limit {{
    context
    output
  }}
  knowledge
  releaseDate
  lastUpdated
}}
settings {{
  {MODEL_SETTINGS_FIELDS}
}}
status
remark
associatedChannelCount
"""

MODELS = f"""
query GetModels(
  $first: Int
  $after: Cursor
  $last: Int
  $before: Cursor
  $where: ModelWhereInput
  $orderBy: ModelOrder
) {{
  models(first: $first, after: $after, last: $last, before: $before, where: $where, orderBy: $orderBy) {{
    edges {{
      node {{
        {MODEL_FIELDS}
      }}
      cursor
    }}
    pageInfo {{
      hasNextPage
      hasPreviousPage
      startCursor
      endCursor
    }}
    totalCount
  }}
}}
"""

GET_MODEL = f"""
query GetModel($id: ID!) {{
  node(id: $id) {{
    ... on Model {{
      {MODEL_FIELDS}
    }}
  }}
}}
"""

CREATE_MODEL = f"""
mutation CreateModel($input: CreateModelInput!) {{
  createModel(input: $input) {{
    {MODEL_FIELDS}
  }}
}}
"""

BULK_CREATE_MODELS = f"""
mutation BulkCreateModels($inputs: [CreateModelInput!]!) {{
  bulkCreateModels(inputs: $inputs) {{
    {MODEL_FIELDS}
  }}
}}
"""

UPDATE_MODEL = f"""
mutation UpdateModel($id: ID!, $input: UpdateModelInput!) {{
  updateModel(id: $id, input: $input) {{
    {MODEL_FIELDS}
  }}
}}
"""

UPDATE_MODEL_STATUS = """
mutation UpdateModelStatus($id: ID!, $status: ModelStatus!) {
  updateModelStatus(id: $id, status: $status)
}
"""

DELETE_MODEL = """
mutation DeleteModel($id: ID!) {
  deleteModel(id: $id)
}
"""

BULK_ARCHIVE_MODELS = """
mutation BulkArchiveModels($ids: [ID!]!) {
  bulkArchiveModels(ids: $ids)
}
"""

BULK_DISABLE_MODELS = """
mutation BulkDisableModels($ids: [ID!]!) {
  bulkDisableModels(ids: $ids)
}
"""

BULK_ENABLE_MODELS = """
mutation BulkEnableModels($ids: [ID!]!) {
  bulkEnableModels(ids: $ids)
}
"""

BULK_DELETE_MODELS = """
mutation BulkDeleteModels($ids: [ID!]!) {
  bulkDeleteModels(ids: $ids)
}
"""

QUERY_MODEL_CHANNEL_CONNECTIONS = """
query QueryModelChannelConnections($associations: [ModelAssociationInput!]!) {
  queryModelChannelConnections(associations: $associations) {
    priority
    channel {
      id
      name
      type
      status
    }
    models {
      requestModel
      actualModel
      source
    }
  }
}
"""

QUERY_UNASSOCIATED_CHANNELS = """
query QueryUnassociatedChannels {
  queryUnassociatedChannels {
    channel {
      id
      name
      type
      status
    }
    models
  }
}
"""

FASTEST_MODELS = """
query GetFastestModels($input: FastestChannelsInput!) {
  fastestModels(input: $input) {
    modelId
    modelName
    throughput
    tokensCount
    latencyMs
    requestCount
    confidenceLevel
  }
}
"""

DASHBOARD_OVERVIEW = """
query GetDashboardStats {
  dashboardOverview {
    totalRequests
    requestStats {
      requestsToday
      requestsThisWeek
      requestsLastWeek
      requestsThisMonth
    }
    failedRequests
    averageResponseTime
  }
}
"""

REQUESTS_BY_CHANNEL = """
query GetRequestsByChannel($timeWindow: String) {
  requestStatsByChannel(timeWindow: $timeWindow) {
    channelName
    count
  }
}
"""

REQUESTS_BY_MODEL = """
query GetRequestsByModel($timeWindow: String) {
  requestStatsByModel(timeWindow: $timeWindow) {
    modelId
    count
  }
}
"""

TOKENS_BY_CHANNEL = """
query GetTokensByChannel($timeWindow: String) {
  tokenStatsByChannel(timeWindow: $timeWindow) {
    channelId
    channelName
    inputTokens
    outputTokens
    cachedTokens
    reasoningTokens
    totalTokens
  }
}
"""

TOKENS_BY_MODEL = """
query GetTokensByModel($timeWindow: String) {
  tokenStatsByModel(timeWindow: $timeWindow) {
    modelId
    inputTokens
    outputTokens
    cachedTokens
    reasoningTokens
    totalTokens
  }
}
"""

COST_BY_CHANNEL = """
query GetCostByChannel($timeWindow: String) {
  costStatsByChannel(timeWindow: $timeWindow) {
    channelName
    cost
  }
}
"""

COST_BY_MODEL = """
query GetCostByModel($timeWindow: String) {
  costStatsByModel(timeWindow: $timeWindow) {
    modelId
    cost
  }
}
"""

DAILY_REQUEST_STATS = """
query GetDailyRequestStats {
  dailyRequestStats {
    date
    count
    tokens
    cost
  }
}
"""

TOKEN_STATS = """
query GetTokenStats {
  tokenStats {
    totalInputTokensToday
    totalOutputTokensToday
    totalCachedTokensToday
    totalInputTokensThisWeek
    totalOutputTokensThisWeek
    totalCachedTokensThisWeek
    totalInputTokensThisMonth
    totalOutputTokensThisMonth
    totalCachedTokensThisMonth
    totalInputTokensAllTime
    totalOutputTokensAllTime
    totalCachedTokensAllTime
    lastUpdated
  }
}
"""

CHANNEL_SUCCESS_RATES = """
query GetChannelSuccessRates($timeWindow: String, $limit: Int) {
  channelSuccessRates(timeWindow: $timeWindow, limit: $limit) {
    channelId
    channelName
    channelType
    channelDisabled
    successCount
    failedCount
    totalCount
    successRate
  }
}
"""

REQUEST_SUMMARY_FIELDS = """
id
createdAt
updatedAt
apiKeyID
projectID
traceID
source
modelID
format
reasoningEffort
channelID
externalID
status
stream
clientIP
metricsLatencyMs
metricsFirstTokenLatencyMs
metricsReasoningDurationMs
contentSaved
contentStorageKey
apiKey {
  id
  name
}
channel {
  id
  name
  type
}
usageLogs(first: 1) {
  edges {
    node {
      id
      promptTokens
      completionTokens
      totalTokens
      promptCachedTokens
      promptWriteCachedTokens
      totalCost
    }
  }
  totalCount
}
executions(first: 5, orderBy: { field: CREATED_AT, direction: DESC }) {
  edges {
    node {
      id
      createdAt
      requestID
      channelID
      modelID
      status
      responseStatusCode
      errorMessage
      metricsLatencyMs
      metricsFirstTokenLatencyMs
      metricsReasoningDurationMs
      channel {
        id
        name
        type
      }
    }
    cursor
  }
  pageInfo {
    hasNextPage
    hasPreviousPage
    startCursor
    endCursor
  }
  totalCount
}
"""

REQUEST_CONTENT_FIELDS = """
requestHeaders
requestBody
responseBody
responseChunks
"""

REQUESTS = f"""
query GetRequests(
  $first: Int
  $after: Cursor
  $last: Int
  $before: Cursor
  $orderBy: RequestOrder
  $where: RequestWhereInput
) {{
  requests(first: $first, after: $after, last: $last, before: $before, orderBy: $orderBy, where: $where) {{
    edges {{
      node {{
        {REQUEST_SUMMARY_FIELDS}
      }}
      cursor
    }}
    pageInfo {{
      hasNextPage
      hasPreviousPage
      startCursor
      endCursor
    }}
    totalCount
  }}
}}
"""

GET_REQUEST = f"""
query GetRequest($id: ID!) {{
  node(id: $id) {{
    ... on Request {{
      {REQUEST_SUMMARY_FIELDS}
    }}
  }}
}}
"""

GET_REQUEST_WITH_CONTENT = f"""
query GetRequestWithContent($id: ID!) {{
  node(id: $id) {{
    ... on Request {{
      {REQUEST_SUMMARY_FIELDS}
      {REQUEST_CONTENT_FIELDS}
    }}
  }}
}}
"""

REQUEST_EXECUTION_FIELDS = """
id
createdAt
updatedAt
projectID
requestID
channelID
dataStorageID
externalID
modelID
format
errorMessage
responseStatusCode
status
stream
metricsLatencyMs
metricsFirstTokenLatencyMs
metricsReasoningDurationMs
channel {
  id
  name
  type
  baseURL
}
"""

REQUEST_EXECUTIONS = f"""
query GetRequestExecutions(
  $requestID: ID!
  $first: Int
  $after: Cursor
  $orderBy: RequestExecutionOrder
  $where: RequestExecutionWhereInput
) {{
  node(id: $requestID) {{
    ... on Request {{
      executions(first: $first, after: $after, orderBy: $orderBy, where: $where) {{
        edges {{
          node {{
            {REQUEST_EXECUTION_FIELDS}
          }}
          cursor
        }}
        pageInfo {{
          hasNextPage
          hasPreviousPage
          startCursor
          endCursor
        }}
        totalCount
      }}
    }}
  }}
}}
"""

USAGE_LOG_FIELDS = """
id
createdAt
updatedAt
requestID
apiKeyID
projectID
channelID
modelID
promptTokens
completionTokens
totalTokens
promptAudioTokens
promptCachedTokens
promptWriteCachedTokens
completionAudioTokens
completionReasoningTokens
completionAcceptedPredictionTokens
completionRejectedPredictionTokens
source
format
totalCost
costItems {
  itemCode
  quantity
  subtotal
}
channel {
  id
  name
  type
}
"""

USAGE_LOGS = f"""
query GetUsageLogs(
  $first: Int
  $after: Cursor
  $orderBy: UsageLogOrder
  $where: UsageLogWhereInput
) {{
  usageLogs(first: $first, after: $after, orderBy: $orderBy, where: $where) {{
    edges {{
      node {{
        {USAGE_LOG_FIELDS}
      }}
      cursor
    }}
    pageInfo {{
      hasNextPage
      hasPreviousPage
      startCursor
      endCursor
    }}
    totalCount
  }}
}}
"""

GET_USAGE_LOG = f"""
query GetUsageLog($id: ID!) {{
  node(id: $id) {{
    ... on UsageLog {{
      {USAGE_LOG_FIELDS}
    }}
  }}
}}
"""

TRACE_FIELDS = """
id
traceID
createdAt
updatedAt
usageMetadata {
  totalInputTokens
  totalOutputTokens
  totalTokens
  totalCost
  totalCachedTokens
  totalCachedWriteTokens
}
project {
  id
  name
}
thread {
  id
  threadID
}
requests(where: { status: completed }) {
  totalCount
}
"""

TRACES = f"""
query GetTraces(
  $first: Int
  $after: Cursor
  $orderBy: TraceOrder
  $where: TraceWhereInput
) {{
  traces(first: $first, after: $after, orderBy: $orderBy, where: $where) {{
    edges {{
      node {{
        {TRACE_FIELDS}
      }}
      cursor
    }}
    pageInfo {{
      hasNextPage
      hasPreviousPage
      startCursor
      endCursor
    }}
    totalCount
  }}
}}
"""

GET_TRACE = f"""
query GetTrace($id: ID!) {{
  node(id: $id) {{
    ... on Trace {{
      {TRACE_FIELDS}
      rawRootSegment
    }}
  }}
}}
"""
