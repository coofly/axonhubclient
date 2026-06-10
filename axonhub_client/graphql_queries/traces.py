from __future__ import annotations

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
