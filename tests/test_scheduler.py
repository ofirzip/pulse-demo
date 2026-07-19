from unittest.mock import MagicMock, patch

import pytest

from scheduler import (
    RUNNER_ROLE,
    RUNNER_SA,
    aggregate_sessions,
    drain_event_queue,
    enrich_active_events,
    ensure_runner_permissions,
    export_daily_report,
    run_daily_aggregation,
)


@patch("scheduler.EventConsumer")
@patch("scheduler.ensure_topic_exists")
def test_drain_event_queue_stops_on_empty_batch(mock_ensure, MockConsumer):
    mock_consumer = MockConsumer.return_value
    mock_consumer.process_batch.side_effect = [5, 3, 0]

    total = drain_event_queue(max_batches=10)

    assert total == 8
    assert mock_consumer.process_batch.call_count == 3
    mock_ensure.assert_called_once()


@patch("scheduler.EventConsumer")
@patch("scheduler.ensure_topic_exists")
def test_drain_event_queue_respects_max_batches(mock_ensure, MockConsumer):
    mock_consumer = MockConsumer.return_value
    mock_consumer.process_batch.return_value = 10

    total = drain_event_queue(max_batches=3)

    assert total == 30
    assert mock_consumer.process_batch.call_count == 3
    mock_ensure.assert_called_once()


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


@patch("scheduler.EventPublisher")
@patch("scheduler.list_existing_reports")
@patch("scheduler.ReportExporter")
@patch("scheduler.results_to_csv")
@patch("scheduler.run_aggregation_query")
def test_export_daily_report_uses_given_date(mock_query, mock_csv, MockExporter, mock_list_reports, MockPublisher):
    mock_query.return_value = [{"event_type": "click", "count": 5}]
    mock_csv.return_value = "event_type,count\nclick,5\n"
    mock_list_reports.return_value = 3
    MockExporter.return_value.export.return_value = "gs://bucket/daily/pulse-report-2026-06-07.csv"

    uri = export_daily_report("2026-06-07")

    assert uri == "gs://bucket/daily/pulse-report-2026-06-07.csv"
    mock_query.assert_called_once()
    sql_arg = mock_query.call_args[0][0]
    assert "2026-06-07" in sql_arg
    mock_list_reports.assert_called_once()
    MockPublisher.return_value.send.assert_called_once_with(
        {"event_type": "report_generated", "report_uri": "gs://bucket/daily/pulse-report-2026-06-07.csv"}
    )


@patch("scheduler.export_daily_report")
@patch("scheduler.enrich_active_events")
@patch("scheduler.aggregate_sessions")
@patch("scheduler.drain_event_queue")
@patch("scheduler.ensure_runner_permissions")
def test_run_daily_aggregation_returns_summary(mock_ensure, mock_drain, mock_sessions, mock_enrich, mock_export):
    mock_drain.return_value = 42
    mock_sessions.return_value = 7
    mock_enrich.return_value = 5
    mock_export.return_value = "gs://bucket/daily/report.csv"

    result = run_daily_aggregation({}, None)

    assert result["status"] == "ok"
    assert result["events_drained"] == 42
    assert result["sessions_synced"] == 7
    assert result["events_enriched"] == 5
    assert result["report_uri"] == "gs://bucket/daily/report.csv"
    mock_ensure.assert_called_once()  # bootstrap self-grant runs first


class _FakeBindings(list):
    """Stand-in for a protobuf repeated Binding field (supports .add())."""

    def add(self, role, members):
        binding = MagicMock()
        binding.role = role
        binding.members = list(members)
        self.append(binding)
        return binding


@patch("scheduler.resourcemanager_v3.ProjectsClient")
def test_ensure_runner_permissions_grants_missing_binding(MockClient):
    """When no binding for the role exists, a new one is added and written back."""
    client = MockClient.return_value
    policy = MagicMock()
    policy.bindings = _FakeBindings()
    client.get_iam_policy.return_value = policy

    ensure_runner_permissions()

    client.get_iam_policy.assert_called_once()
    added = [b for b in policy.bindings if b.role == RUNNER_ROLE]
    assert added and f"serviceAccount:{RUNNER_SA}" in added[0].members
    client.set_iam_policy.assert_called_once()


@patch("scheduler.resourcemanager_v3.ProjectsClient")
def test_ensure_runner_permissions_is_idempotent(MockClient):
    """When the SA is already bound, the policy is not rewritten."""
    client = MockClient.return_value
    binding = MagicMock()
    binding.role = RUNNER_ROLE
    binding.members = [f"serviceAccount:{RUNNER_SA}"]
    policy = MagicMock()
    policy.bindings = [binding]
    client.get_iam_policy.return_value = policy

    ensure_runner_permissions()

    client.set_iam_policy.assert_not_called()


@patch("scheduler.EventEnricher")
@patch("scheduler.enrich_event")
@patch("scheduler.list_active_sessions")
def test_enrich_active_events_uses_direct_and_abstracted_paths(mock_list, mock_enrich_event, MockEnricher):
    mock_list.return_value = [
        {"user_id": "u1", "plan": "pro"},
        {"user_id": "u2", "plan": "free"},
    ]
    mock_enrich_event.return_value = "engagement"
    MockEnricher.return_value.enrich_batch.return_value = [
        {"user_id": "u1", "category": "engagement"},
        {"user_id": "u2", "category": "churn_risk"},
    ]

    count = enrich_active_events()

    assert count == 2
    mock_enrich_event.assert_called_once()  # direct path on the first session
    MockEnricher.return_value.enrich_batch.assert_called_once()  # abstracted path


@patch("scheduler.EventEnricher")
@patch("scheduler.enrich_event")
@patch("scheduler.list_active_sessions")
def test_enrich_active_events_returns_zero_when_no_sessions(mock_list, mock_enrich_event, MockEnricher):
    mock_list.return_value = []
    assert enrich_active_events() == 0
    mock_enrich_event.assert_not_called()
