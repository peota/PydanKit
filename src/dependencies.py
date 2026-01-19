"""Dependency injection container for the agent."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentDeps:
    """Base dependency container - extend for your agent's needs.

    Examples of dependencies you might add:
        - Database connections
        - API clients
        - User context
        - Feature flags
        - Cache instances

    Usage:
        @dataclass
        class MyAgentDeps(AgentDeps):
            db: Database
            api_client: APIClient
    """

    user_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
