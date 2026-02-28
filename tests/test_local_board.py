"""Tests for the LocalBoard JSON adapter."""

from __future__ import annotations

import json
import os

import pytest

from omniforge.runner.adapters.local_board import LocalBoard


@pytest.fixture()
def board(tmp_path):
    """Return a LocalBoard backed by a temporary file."""
    return LocalBoard(board_path=str(tmp_path / "board.json"))


class TestUpsertTicket:
    def test_creates_new_ticket(self, board):
        result = board.upsert_ticket("T-001", {"status": "running", "project": "test"})
        assert result["status"] == "running"
        assert result["project"] == "test"

    def test_updates_existing_ticket(self, board):
        board.upsert_ticket("T-001", {"status": "running"})
        board.upsert_ticket("T-001", {"status": "delivered", "extra": "value"})
        ticket = board.get_ticket("T-001")
        assert ticket["status"] == "delivered"
        assert ticket["extra"] == "value"

    def test_preserves_untouched_fields(self, board):
        board.upsert_ticket("T-001", {"project": "omnidigest", "status": "running"})
        board.upsert_ticket("T-001", {"status": "failed_at_test"})
        ticket = board.get_ticket("T-001")
        assert ticket["project"] == "omnidigest"

    def test_multiple_tickets_independent(self, board):
        board.upsert_ticket("T-001", {"status": "running"})
        board.upsert_ticket("T-002", {"status": "delivered"})
        assert board.get_ticket("T-001")["status"] == "running"
        assert board.get_ticket("T-002")["status"] == "delivered"


class TestGetTicket:
    def test_returns_none_for_missing_ticket(self, board):
        assert board.get_ticket("T-999") is None

    def test_returns_ticket_when_present(self, board):
        board.upsert_ticket("T-001", {"status": "running"})
        ticket = board.get_ticket("T-001")
        assert ticket is not None
        assert ticket["status"] == "running"


class TestListTickets:
    def test_empty_board_returns_empty_dict(self, board):
        assert board.list_tickets() == {}

    def test_returns_all_tickets(self, board):
        board.upsert_ticket("T-001", {"status": "running"})
        board.upsert_ticket("T-002", {"status": "delivered"})
        tickets = board.list_tickets()
        assert set(tickets.keys()) == {"T-001", "T-002"}


class TestDeleteTicket:
    def test_deletes_existing_ticket(self, board):
        board.upsert_ticket("T-001", {"status": "running"})
        removed = board.delete_ticket("T-001")
        assert removed is True
        assert board.get_ticket("T-001") is None

    def test_returns_false_for_missing_ticket(self, board):
        assert board.delete_ticket("T-999") is False


class TestPersistence:
    def test_data_persists_across_instances(self, tmp_path):
        path = str(tmp_path / "board.json")
        board1 = LocalBoard(board_path=path)
        board1.upsert_ticket("T-001", {"status": "delivered"})

        board2 = LocalBoard(board_path=path)
        assert board2.get_ticket("T-001")["status"] == "delivered"

    def test_board_file_is_valid_json(self, tmp_path):
        path = str(tmp_path / "board.json")
        board = LocalBoard(board_path=path)
        board.upsert_ticket("T-001", {"status": "running"})
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        assert "T-001" in data
