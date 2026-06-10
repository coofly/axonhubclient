from __future__ import annotations

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

