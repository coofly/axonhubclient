from __future__ import annotations

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

