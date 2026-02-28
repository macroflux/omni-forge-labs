"""Local JSON board adapter for ticket tracking.

Stores all ticket state in a single ``board.json`` file inside the ``runs/``
directory.  This is the MVP tracker — no external service required.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional

# Default board path relative to this file: ../../runs/board.json
_DEFAULT_BOARD_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "runs", "board.json"
)


class LocalBoard:
    """Simple JSON-backed ticket board.

    Parameters
    ----------
    board_path:
        Absolute path to the ``board.json`` file.  Defaults to
        ``runs/board.json`` at the repository root.
    """

    def __init__(self, board_path: Optional[str] = None) -> None:
        self.board_path = os.path.abspath(board_path or _DEFAULT_BOARD_PATH)
        os.makedirs(os.path.dirname(self.board_path), exist_ok=True)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load(self) -> Dict[str, Any]:
        if not os.path.exists(self.board_path):
            return {}
        with open(self.board_path, encoding="utf-8") as fh:
            return json.load(fh)

    def _save(self, data: Dict[str, Any]) -> None:
        with open(self.board_path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
            fh.write("\n")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def upsert_ticket(self, ticket_id: str, fields: Dict[str, Any]) -> Dict[str, Any]:
        """Create or update a ticket with the given fields.

        Parameters
        ----------
        ticket_id:
            Unique ticket identifier (e.g. ``"T-001"``).
        fields:
            Dictionary of fields to merge into the ticket record.

        Returns
        -------
        Dict[str, Any]
            The full ticket record after the update.
        """
        data = self._load()
        if ticket_id not in data:
            data[ticket_id] = {}
        data[ticket_id].update(fields)
        self._save(data)
        return data[ticket_id]

    def get_ticket(self, ticket_id: str) -> Optional[Dict[str, Any]]:
        """Return the ticket record, or *None* if not found."""
        return self._load().get(ticket_id)

    def list_tickets(self) -> Dict[str, Any]:
        """Return the full board as a dictionary keyed by ticket ID."""
        return self._load()

    def delete_ticket(self, ticket_id: str) -> bool:
        """Remove a ticket from the board.

        Returns
        -------
        bool
            ``True`` if the ticket existed and was removed, ``False`` otherwise.
        """
        data = self._load()
        if ticket_id not in data:
            return False
        del data[ticket_id]
        self._save(data)
        return True
