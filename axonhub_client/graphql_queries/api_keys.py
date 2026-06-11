from __future__ import annotations

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
projectID
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
        projectID
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
