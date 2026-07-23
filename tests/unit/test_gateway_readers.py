"""Tests for openclaw_gateway.readers — pipeline log and state-store reading."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from openclaw_gateway import readers

_TODAY = datetime.now(timezone.utc).date().isoformat()


def _cfg(log_path: Path, state_path: Path) -> SimpleNamespace:
    return SimpleNamespace(log_path=log_path, state_store_path=state_path)


# ── pipeline.log fixture (5 JSONL lines: 3 past, 2 today) ─────────────────────

_LOG_LINES = [
    {"ts": "2026-07-20T00:00:00Z", "emails_processed": 5, "crm_logged": 1, "notified": 1, "pending": 0, "errors": [], "duration_seconds": 12.3},
    {"ts": "2026-07-21T00:00:00Z", "emails_processed": 3, "crm_logged": 0, "notified": 0, "pending": 0, "errors": ["quota_exhausted"], "duration_seconds": 8.1},
    {"ts": "2026-07-22T00:00:00Z", "emails_processed": 7, "crm_logged": 2, "notified": 2, "pending": 0, "errors": [], "duration_seconds": 15.0},
    {"ts": f"{_TODAY}T09:00:00Z", "emails_processed": 10, "crm_logged": 3, "notified": 3, "pending": 0, "errors": [], "duration_seconds": 20.0},
    {"ts": f"{_TODAY}T10:00:00Z", "emails_processed": 12, "crm_logged": 4, "notified": 4, "pending": 0, "errors": [], "duration_seconds": 25.0},
]

# ── processed_ids.json fixture (3 deals + 1 non-deal) ─────────────────────────

_DEAL_1 = {
    "gmail_message_id": "id1", "processed_at": "2026-07-20T00:00:00Z",
    "outcome": "deal_extracted", "sender_name": "Alice Smith", "sender_email": "alice@example.com",
    "subject": "Partnership Offer", "deal_type": "partnership", "confidence_score": 0.9,
    "crm_status": "logged", "crm_retry_count": 0, "hubspot_deal_id": "123456",
    "notify_status": "sent", "notify_retry_count": 0,
}
_DEAL_2 = {
    "gmail_message_id": "id2", "processed_at": "2026-07-21T00:00:00Z",
    "outcome": "deal_extracted", "sender_name": "Bob Jones", "sender_email": "bob@example.com",
    "subject": "Investment Opportunity", "deal_type": "investment", "confidence_score": 0.75,
    "crm_status": "pending", "crm_retry_count": 1, "hubspot_deal_id": None,
    "notify_status": None, "notify_retry_count": 0,
}
_DEAL_3 = {
    "gmail_message_id": "id3", "processed_at": "2026-07-22T00:00:00Z",
    "outcome": "deal_extracted", "sender_name": "Carol Lee", "sender_email": "carol@example.com",
    "subject": "Collaboration Request", "deal_type": "partnership", "confidence_score": 0.85,
    "crm_status": "logged", "crm_retry_count": 0, "hubspot_deal_id": "789012",
    "notify_status": "sent", "notify_retry_count": 0,
}
_NON_DEAL = {
    "gmail_message_id": "id4", "processed_at": "2026-07-22T00:00:00Z",
    "outcome": "not_deal",
}

_STATE_DATA = {"messages": [_DEAL_1, _DEAL_2, _DEAL_3, _NON_DEAL]}


@pytest.fixture
def log_file(tmp_path: Path) -> Path:
    p = tmp_path / "pipeline.log"
    p.write_text("\n".join(json.dumps(line) for line in _LOG_LINES), encoding="utf-8")
    return p


@pytest.fixture
def state_file(tmp_path: Path) -> Path:
    p = tmp_path / "state.json"
    p.write_text(json.dumps(_STATE_DATA), encoding="utf-8")
    return p


# ── read_pipeline_log ──────────────────────────────────────────────────────────

class TestReadPipelineLog:

    def test_returns_last_n_lines(self, tmp_path, log_file):
        cfg = _cfg(log_file, tmp_path / "state.json")
        result = readers.read_pipeline_log(3, cfg)
        assert len(result) == 3
        assert result[0]["emails_processed"] == 7
        assert result[-1]["emails_processed"] == 12

    def test_returns_all_when_n_exceeds_total(self, tmp_path, log_file):
        cfg = _cfg(log_file, tmp_path / "state.json")
        result = readers.read_pipeline_log(100, cfg)
        assert len(result) == 5

    def test_missing_log_returns_empty(self, tmp_path):
        cfg = _cfg(tmp_path / "missing.log", tmp_path / "state.json")
        result = readers.read_pipeline_log(10, cfg)
        assert result == []

    def test_returns_pipeline_cycle_dicts(self, tmp_path, log_file):
        cfg = _cfg(log_file, tmp_path / "state.json")
        result = readers.read_pipeline_log(5, cfg)
        for entry in result:
            assert "ts" in entry
            assert "emails_processed" in entry

    def test_single_line_requested(self, tmp_path, log_file):
        cfg = _cfg(log_file, tmp_path / "state.json")
        result = readers.read_pipeline_log(1, cfg)
        assert len(result) == 1
        assert result[0]["ts"].startswith(_TODAY)


# ── read_deals ─────────────────────────────────────────────────────────────────

class TestReadDeals:

    def test_returns_all_deals_excluding_non_deals(self, tmp_path, state_file):
        cfg = _cfg(tmp_path / "pipeline.log", state_file)
        result = readers.read_deals(100, "all", cfg)
        assert len(result) == 3
        assert all(d["outcome"] == "deal_extracted" for d in result)

    def test_non_deal_entries_excluded(self, tmp_path, state_file):
        cfg = _cfg(tmp_path / "pipeline.log", state_file)
        result = readers.read_deals(100, "all", cfg)
        ids = [d["gmail_message_id"] for d in result]
        assert "id4" not in ids

    def test_status_filter_crm_pending(self, tmp_path, state_file):
        cfg = _cfg(tmp_path / "pipeline.log", state_file)
        result = readers.read_deals(100, "crm_pending", cfg)
        assert len(result) == 1
        assert result[0]["gmail_message_id"] == "id2"

    def test_limit_respected(self, tmp_path, state_file):
        cfg = _cfg(tmp_path / "pipeline.log", state_file)
        result = readers.read_deals(2, "all", cfg)
        assert len(result) == 2

    def test_missing_state_file_returns_empty(self, tmp_path):
        cfg = _cfg(tmp_path / "pipeline.log", tmp_path / "missing.json")
        result = readers.read_deals(10, "all", cfg)
        assert result == []

    def test_all_filter_returns_deal_fields(self, tmp_path, state_file):
        cfg = _cfg(tmp_path / "pipeline.log", state_file)
        result = readers.read_deals(1, "all", cfg)
        assert "gmail_message_id" in result[0]
        assert "crm_status" in result[0]


# ── compute_quota_usage ────────────────────────────────────────────────────────

class TestComputeQuotaUsage:

    def test_has_all_required_keys(self, tmp_path, log_file):
        cfg = _cfg(log_file, tmp_path / "state.json")
        result = readers.compute_quota_usage(cfg)
        for key in (
            "estimated_requests_today", "daily_free_tier_limit", "estimated_remaining",
            "pct_used", "window_date", "cycles_today", "has_quota_error_today",
        ):
            assert key in result

    def test_cycles_today_counts_only_today(self, tmp_path, log_file):
        cfg = _cfg(log_file, tmp_path / "state.json")
        result = readers.compute_quota_usage(cfg)
        assert result["cycles_today"] == 2

    def test_estimated_requests_sums_today_emails(self, tmp_path, log_file):
        cfg = _cfg(log_file, tmp_path / "state.json")
        result = readers.compute_quota_usage(cfg)
        assert result["estimated_requests_today"] == 22  # 10 + 12

    def test_window_date_is_today(self, tmp_path, log_file):
        cfg = _cfg(log_file, tmp_path / "state.json")
        result = readers.compute_quota_usage(cfg)
        assert result["window_date"] == _TODAY

    def test_pct_used_is_correct(self, tmp_path, log_file):
        cfg = _cfg(log_file, tmp_path / "state.json")
        result = readers.compute_quota_usage(cfg)
        expected = 22 / 1500 * 100
        assert abs(result["pct_used"] - expected) < 0.01

    def test_missing_log_returns_zero_quota(self, tmp_path):
        cfg = _cfg(tmp_path / "missing.log", tmp_path / "state.json")
        result = readers.compute_quota_usage(cfg)
        assert result["cycles_today"] == 0
        assert result["estimated_requests_today"] == 0
        assert result["has_quota_error_today"] is False
        assert result["daily_free_tier_limit"] == 1500

    def test_has_quota_error_today_false_when_none(self, tmp_path, log_file):
        cfg = _cfg(log_file, tmp_path / "state.json")
        result = readers.compute_quota_usage(cfg)
        # _TODAY entries have no quota_exhausted error
        assert result["has_quota_error_today"] is False
