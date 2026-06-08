from unittest.mock import MagicMock, patch

import pytest

from scheduler import (
    aggregate_sessions,
    drain_event_queue,
    export_daily_report,
    run_daily_aggregation,
)


@patch("scheduler.EventConsumer")
def test_drain_event_queue_stops_on_empty_batch(MockConsumer):
    mock_consumer = MockConsumer.return_value
    mock_consumer.process_batch.side_effect = [5, 3, 0]

    total = drain_event_queue(max_batches=10)

    assert total == 8
    assert mock_consumer.process_batch.call_count == 3


@patch("scheduler.EventConsumer")
def test_drain_event_queue_respects_max_batches(MockConsumer):
    mock_consumer = MockConsumer.return_value
    mock_consumer.process_batch.return_value = 10

    total = drain_event_queue(max_batches=3)

    assert total == 30
    assert mock_consumer.process_batch.call_count == 3


@patch("scheduler.SessionRepository")
@patch("scheduler.list_active_sessions")
def test_aggregate_sessions_re_saves_active_users(mock_list, MockRepo):
    mock_list.return_value = [
        {"user_id": "u1", "plan": "pro"},
        {"user_id": "u2", "plan": "free"},
    ]

    count = aggregate_sessions()

    assert count == 2
    assert MockRepo.return_value.save.call_count == 2


@patch("scheduler.SessionRepository")
@patch("scheduler.list_active_sessions")
def test_aggregate_sessions_returns_zero_when_no_sessions(mock_list, MockRepo):
    mock_list.return_value = []
    assert aggregate_sessions() == 0


@patch("scheduler.ReportExporter")
@patch("scheduler.results_to_csv")
@patch("scheduler.run_aggregation_query")
def test_export_daily_report_uses_given_date(mock_query, mock_csv, MockExporter):
    mock_query.return_value = [{"event_type": "click", "count": 5}]
    mock_csv.return_value = "event_type,count\nclick,5\n"
    MockExporter.return_value.export.return_value = "gs://bucket/daily/pulse-report-2026-06-07.csv"

    uri = export_daily_report("2026-06-07")

    assert uri == "gs://bucket/daily/pulse-report-2026-06-07.csv"
    mock_query.assert_called_once()
    sql_arg = mock_query.call_args[0][0]
    assert "2026-06-07" in sql_arg


@patch("scheduler.export_daily_report")
@patch("scheduler.aggregate_sessions")
@patch("scheduler.drain_event_queue")
def test_run_daily_aggregation_returns_summary(mock_drain, mock_sessions, mock_export):
    mock_drain.return_value = 42
    mock_sessions.return_value = 7
    mock_export.return_value = "gs://bucket/daily/report.csv"

    result = run_daily_aggregation({}, None)

    assert result["status"] == "ok"
    assert result["events_drained"] == 42
    assert result["sessions_synced"] == 7
    assert result["report_uri"] == "gs://bucket/daily/report.csv"
