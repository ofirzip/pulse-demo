import json
from unittest.mock import MagicMock, patch

import pytest

from consumer import (
    EventConsumer,
    acknowledge_messages,
    get_bq_client,
    get_subscriber,
    pull_events,
    stream_event,
    write_to_bigquery,
)


def _make_received_message(ack_id: str, event: dict):
    msg = MagicMock()
    msg.ack_id = ack_id
    msg.message.data = json.dumps(event).encode("utf-8")
    return msg


@patch("consumer.pubsub_v1.SubscriberClient")
def test_get_subscriber(MockSub):
    result = get_subscriber()
    MockSub.assert_called_once()
    assert result is MockSub.return_value


@patch("consumer.bigquery.Client")
def test_get_bq_client(MockBQ):
    result = get_bq_client()
    MockBQ.assert_called_once()
    assert result is MockBQ.return_value


@patch("consumer.pubsub_v1.SubscriberClient")
def test_pull_events_returns_ack_event_pairs(MockSub):
    mock_sub = MockSub.return_value
    mock_sub.pull.return_value.received_messages = [
        _make_received_message("ack-1", {"event_type": "click"}),
        _make_received_message("ack-2", {"event_type": "view"}),
    ]

    results = pull_events("projects/p/subscriptions/s")

    assert len(results) == 2
    assert results[0] == ("ack-1", {"event_type": "click"})
    assert results[1] == ("ack-2", {"event_type": "view"})


@patch("consumer.pubsub_v1.SubscriberClient")
def test_pull_events_returns_empty_on_no_messages(MockSub):
    MockSub.return_value.pull.return_value.received_messages = []
    assert pull_events("projects/p/subscriptions/s") == []


@patch("consumer.pubsub_v1.SubscriberClient")
def test_acknowledge_messages(MockSub):
    mock_sub = MockSub.return_value
    acknowledge_messages("projects/p/subscriptions/s", ["ack-1", "ack-2"])
    mock_sub.acknowledge.assert_called_once_with(
        request={
            "subscription": "projects/p/subscriptions/s",
            "ack_ids": ["ack-1", "ack-2"],
        }
    )


@patch("consumer.bigquery.Client")
def test_write_to_bigquery_no_errors(MockBQ):
    MockBQ.return_value.insert_rows_json.return_value = []
    write_to_bigquery([{"event_type": "click"}])
    MockBQ.return_value.insert_rows_json.assert_called_once()


@patch("consumer.bigquery.Client")
def test_write_to_bigquery_raises_on_errors(MockBQ):
    MockBQ.return_value.insert_rows_json.return_value = [{"error": "bad row"}]
    with pytest.raises(RuntimeError, match="BigQuery insert errors"):
        write_to_bigquery([{"event_type": "click"}])


@patch("consumer.bigquery.Client")
@patch("consumer.pubsub_v1.SubscriberClient")
def test_event_consumer_process_batch_returns_count(MockSub, MockBQ):
    mock_sub = MockSub.return_value
    mock_sub.subscription_path.return_value = "projects/p/subscriptions/s"
    mock_sub.pull.return_value.received_messages = [
        _make_received_message("ack-1", {"event_type": "purchase"}),
        _make_received_message("ack-2", {"event_type": "click"}),
    ]
    MockBQ.return_value.insert_rows_json.return_value = []

    consumer = EventConsumer()
    count = consumer.process_batch()

    assert count == 2
    mock_sub.acknowledge.assert_called_once()


@patch("consumer.bigquery.Client")
@patch("consumer.pubsub_v1.SubscriberClient")
def test_event_consumer_process_batch_empty_returns_zero(MockSub, MockBQ):
    mock_sub = MockSub.return_value
    mock_sub.subscription_path.return_value = "projects/p/subscriptions/s"
    mock_sub.pull.return_value.received_messages = []

    consumer = EventConsumer()
    count = consumer.process_batch()

    assert count == 0
    mock_sub.acknowledge.assert_not_called()
