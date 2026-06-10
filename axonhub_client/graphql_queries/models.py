from __future__ import annotations

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

