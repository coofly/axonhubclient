from __future__ import annotations

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

