"""Local JSON board adapter for ticket tracking.

Stores all ticket state in a single ``board.json`` file inside the ``runs/``
directory.  This is the MVP tracker — no external service required.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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

    @staticmethod
    def _ensure_ticket_defaults(ticket: Dict[str, Any], ticket_id: str) -> Dict[str, Any]:
        """Populate ticket defaults without overwriting existing values."""
        ticket.setdefault("ticket_id", ticket_id)
        ticket.setdefault("project", None)
        ticket.setdefault("stage", "intake")
        ticket.setdefault("status", "pending")
        ticket.setdefault("approvals", {})
        ticket.setdefault("approvals_meta", {})
        ticket.setdefault("rollback_counts", {})
        ticket.setdefault("history", [])
        return ticket

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
        ticket = self._ensure_ticket_defaults(data[ticket_id], ticket_id)
        ticket.update(fields)
        data[ticket_id] = ticket
        self._save(data)
        return ticket

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

    def append_event(
        self,
        ticket_id: str,
        event_type: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Append a history event to the ticket.

        Parameters
        ----------
        ticket_id:
            Unique ticket identifier.
        event_type:
            Short label for the event (e.g. ``"stage_passed"``, ``"approved"``).
        payload:
            Optional dict with additional event data.

        Returns
        -------
        Dict[str, Any]
            The full ticket record after appending the event.
        """
        data = self._load()
        if ticket_id not in data:
            data[ticket_id] = {}
        ticket = self._ensure_ticket_defaults(data[ticket_id], ticket_id)
        ticket["history"].append({
            "at": _now_iso(),
            "type": event_type,
            "payload": payload or {},
        })
        data[ticket_id] = ticket
        self._save(data)
        return ticket

    def approve_stage(
        self,
        ticket_id: str,
        stage: str,
        by: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Record a client approval for a gate stage.

        Sets ``approvals[stage] = True``, records metadata in
        ``approvals_meta[stage]``, and appends an ``"approved"`` history event.

        Parameters
        ----------
        ticket_id:
            Unique ticket identifier.
        stage:
            SDLC stage being approved (e.g. ``"design"``).
        by:
            Approver name.  Defaults to ``"client"`` when omitted.

        Returns
        -------
        Dict[str, Any]
            The full ticket record after recording the approval.
        """
        approver = by or "client"
        data = self._load()
        if ticket_id not in data:
            data[ticket_id] = {}
        ticket = self._ensure_ticket_defaults(data[ticket_id], ticket_id)
        ticket["approvals"][stage] = True
        ticket["approvals_meta"][stage] = {"by": approver, "at": _now_iso()}
        data[ticket_id] = ticket
        self._save(data)
        return self.append_event(ticket_id, "approved", {"stage": stage, "by": approver})
