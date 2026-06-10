from __future__ import annotations

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

