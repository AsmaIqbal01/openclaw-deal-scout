"""
T030 — Unit tests for gmail_intake.gmail_client: FR-003a ordering and cap.

FR-003a: the max_messages cap is applied to the full inbox sorted oldest-first,
BEFORE the already_processed filter. Concretely:
  1. poll_inbox sorts all fetched messages by internalDate ascending.
  2. poll_inbox slices the sorted list to max_messages — this is the cap.
  3. server.py then applies `if msg_id in already_processed: continue` on the
     already-capped list (server.py:110-113).

This ordering ensures that if the operator's inbox has 60 unread messages and
max_messages=50, the 50 OLDEST messages are evaluated — never the 50 most-recent.
"""
from unittest.mock import MagicMock

from gmail_intake.gmail_client import poll_inbox


def test_poll_inbox_cap_applied_oldest_first():
    """
    Given 60 messages with distinct internalDates, poll_inbox with max_messages=50
    returns exactly the 50 with the smallest internalDate values (oldest first),
    not the 50 most-recent.
    """
    n_total = 60
    max_messages = 50

    # 60 stubs passed back by the Gmail list() call (arbitrary order)
    stubs = [{"id": f"msg{i}"} for i in range(n_total)]

    # Full messages: msg0 is oldest (internalDate 1000), msg59 newest (6900)
    full_msgs = [
        {"id": f"msg{i}", "internalDate": str(1000 + i * 100)}
        for i in range(n_total)
    ]

    service = MagicMock()
    # list() returns all 60 stubs in a single page
    (service.users.return_value
     .messages.return_value
     .list.return_value
     .execute.return_value) = {"messages": stubs}
    # get() returns full messages sequentially in stub order
    (service.users.return_value
     .messages.return_value
     .get.return_value
     .execute.side_effect) = full_msgs

    result = poll_inbox(service, since_ts=None, max_messages=max_messages)

    # Exactly max_messages returned
    assert len(result) == max_messages

    result_dates = [int(m["internalDate"]) for m in result]

    # Results are in ascending (oldest-first) order
    assert result_dates == sorted(result_dates)

    # The 50 results are the 50 OLDEST, not the 50 most-recent
    # msg0–msg49: internalDate 1000–5900 (included)
    # msg50–msg59: internalDate 6000–6900 (excluded)
    assert min(result_dates) == 1000
    assert max(result_dates) == 1000 + (max_messages - 1) * 100  # 5900

    # The 10 most-recent messages must not appear in the result
    excluded_ids = {f"msg{i}" for i in range(max_messages, n_total)}
    result_ids = {m["id"] for m in result}
    assert result_ids.isdisjoint(excluded_ids)
