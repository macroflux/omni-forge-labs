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


class TestEnsureTicketDefaults:
    def test_new_ticket_gets_standard_shape(self, board):
        ticket = board.upsert_ticket("T-001", {"project": "omnidigest"})
        assert ticket["ticket_id"] == "T-001"
        assert ticket["stage"] == "intake"
        assert ticket["status"] == "pending"
        assert ticket["approvals"] == {}
        assert ticket["approvals_meta"] == {}
        assert ticket["rollback_counts"] == {}
        assert ticket["history"] == []

    def test_existing_values_not_overwritten(self, board):
        board.upsert_ticket("T-001", {"stage": "implement", "status": "running"})
        ticket = board.upsert_ticket("T-001", {"last_log": "implement.log"})
        assert ticket["stage"] == "implement"
        assert ticket["status"] == "running"


class TestAppendEvent:
    def test_appends_event_to_history(self, board):
        board.upsert_ticket("T-001", {"project": "test"})
        board.append_event("T-001", "stage_passed", {"stage": "plan"})
        ticket = board.get_ticket("T-001")
        assert len(ticket["history"]) == 1
        evt = ticket["history"][0]
        assert evt["type"] == "stage_passed"
        assert evt["payload"] == {"stage": "plan"}
        assert "at" in evt

    def test_appends_multiple_events_in_order(self, board):
        board.upsert_ticket("T-001", {})
        board.append_event("T-001", "first", {})
        board.append_event("T-001", "second", {})
        history = board.get_ticket("T-001")["history"]
        assert history[0]["type"] == "first"
        assert history[1]["type"] == "second"

    def test_creates_ticket_if_missing(self, board):
        ticket = board.append_event("T-999", "stage_passed", {"stage": "intake"})
        assert ticket["ticket_id"] == "T-999"
        assert len(ticket["history"]) == 1

    def test_empty_payload_defaults_to_empty_dict(self, board):
        board.upsert_ticket("T-001", {})
        board.append_event("T-001", "ping")
        evt = board.get_ticket("T-001")["history"][0]
        assert evt["payload"] == {}


class TestApproveStage:
    def test_sets_approval_flag(self, board):
        board.upsert_ticket("T-001", {"project": "test"})
        board.approve_stage("T-001", "design", by="Chris")
        ticket = board.get_ticket("T-001")
        assert ticket["approvals"]["design"] is True

    def test_records_approvals_meta(self, board):
        board.upsert_ticket("T-001", {})
        board.approve_stage("T-001", "design", by="Chris")
        meta = board.get_ticket("T-001")["approvals_meta"]["design"]
        assert meta["by"] == "Chris"
        assert "at" in meta

    def test_defaults_approver_to_client(self, board):
        board.upsert_ticket("T-001", {})
        board.approve_stage("T-001", "test")
        meta = board.get_ticket("T-001")["approvals_meta"]["test"]
        assert meta["by"] == "client"

    def test_appends_approved_history_event(self, board):
        board.upsert_ticket("T-001", {})
        board.approve_stage("T-001", "design", by="Alex")
        history = board.get_ticket("T-001")["history"]
        assert any(
            e["type"] == "approved" and e["payload"]["stage"] == "design"
            for e in history
        )

    def test_creates_ticket_if_missing(self, board):
        ticket = board.approve_stage("T-999", "deliver", by="Sam")
        assert ticket["approvals"]["deliver"] is True
        assert ticket["ticket_id"] == "T-999"
