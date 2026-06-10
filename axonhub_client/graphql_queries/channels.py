from __future__ import annotations

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

