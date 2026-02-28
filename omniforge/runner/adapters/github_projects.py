"""GitHub Projects adapter (stub — future implementation).

This module will provide ticket sync between the local JSON board and
GitHub Issues / Projects once API credentials are configured.

Usage (future)::

    from adapters.github_projects import GitHubProjectsAdapter

    adapter = GitHubProjectsAdapter(
        token=os.environ["GITHUB_TOKEN"],
        owner="macroflux",
        repo="omni-forge-labs",
    )
    adapter.upsert_issue(ticket_id, fields)
"""

from __future__ import annotations


class GitHubProjectsAdapter:  # pragma: no cover
    """Stub adapter for GitHub Issues / Projects.

    Parameters
    ----------
    token:
        GitHub personal access token with ``repo`` and ``project`` scopes.
    owner:
        Repository owner (user or organisation).
    repo:
        Repository name.
    """

    def __init__(self, token: str, owner: str, repo: str) -> None:
        self.token = token
        self.owner = owner
        self.repo = repo

    def upsert_issue(self, ticket_id: str, fields: dict) -> dict:
        """Create or update a GitHub Issue for the ticket.

        Not yet implemented — raises ``NotImplementedError``.
        """
        raise NotImplementedError(
            "GitHubProjectsAdapter is not yet implemented. "
            "Use LocalBoard for MVP tracking."
        )
