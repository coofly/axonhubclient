from __future__ import annotations

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

