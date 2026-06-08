from unittest.mock import MagicMock, patch
import pytest
from ingestor import (
    get_publisher,
    ensure_topic_exists,
    publish_event,
    publish_batch,
    list_topics_gapic,
    get_topic_gapic,
    EventPublisher,
)


@patch("ingestor.pubsub_v1.PublisherClient")
def test_get_publisher_returns_client(MockClient):
    result = get_publisher()
    MockClient.assert_called_once()
    assert result is MockClient.return_value


@patch("ingestor.pubsub_v1.PublisherClient")
def test_ensure_topic_exists_creates_topic(MockClient):
    mock_pub = MockClient.return_value
    mock_pub.topic_path.return_value = "projects/p/topics/t"
    ensure_topic_exists("p", "t")
    mock_pub.create_topic.assert_called_once_with(
        request={"name": "projects/p/topics/t"}
    )


@patch("ingestor.pubsub_v1.PublisherClient")
def test_ensure_topic_exists_ignores_already_exists(MockClient):
    mock_pub = MockClient.return_value
    mock_pub.topic_path.return_value = "projects/p/topics/t"
    mock_pub.create_topic.side_effect = Exception("AlreadyExists")
    ensure_topic_exists("p", "t")  # must not raise


@patch("ingestor.pubsub_v1.PublisherClient")
def test_publish_event_returns_message_id(MockClient):
    mock_pub = MockClient.return_value
    mock_pub.topic_path.return_value = "projects/p/topics/pulse-events"
    mock_future = MagicMock()
    mock_future.result.return_value = "msg-001"
    mock_pub.publish.return_value = mock_future

    result = publish_event({"event_type": "page_view", "user_id": "u1"})

    assert result == "msg-001"
    mock_pub.publish.assert_called_once()


@patch("ingestor.pubsub_v1.PublisherClient")
def test_publish_batch_returns_all_ids(MockClient):
    mock_pub = MockClient.return_value
    mock_pub.topic_path.return_value = "projects/p/topics/pulse-events"
    ids = ["id-1", "id-2", "id-3"]
    futures = [MagicMock() for _ in ids]
    for f, i in zip(futures, ids):
        f.result.return_value = i
    mock_pub.publish.side_effect = futures

    result = publish_batch([{"event_type": "click"} for _ in ids])

    assert result == ids


@patch("ingestor.GapicPublisherClient")
def test_list_topics_gapic(MockGapic):
    topic_a = MagicMock()
    topic_a.name = "projects/p/topics/a"
    topic_b = MagicMock()
    topic_b.name = "projects/p/topics/b"
    MockGapic.return_value.list_topics.return_value = [topic_a, topic_b]

    result = list_topics_gapic("p")

    assert result == ["projects/p/topics/a", "projects/p/topics/b"]


@patch("ingestor.GapicPublisherClient")
def test_get_topic_gapic(MockGapic):
    mock_topic = MagicMock()
    mock_topic.name = "projects/p/topics/pulse-events"
    MockGapic.return_value.get_topic.return_value = mock_topic

    result = get_topic_gapic("p", "pulse-events")

    assert result.name == "projects/p/topics/pulse-events"
    MockGapic.return_value.get_topic.assert_called_once_with(
        request={"topic": "projects/p/topics/pulse-events"}
    )


@patch("ingestor.pubsub_v1.PublisherClient")
def test_event_publisher_send(MockClient):
    mock_pub = MockClient.return_value
    mock_pub.topic_path.return_value = "projects/p/topics/pulse-events"
    mock_future = MagicMock()
    mock_future.result.return_value = "msg-xyz"
    mock_pub.publish.return_value = mock_future

    publisher = EventPublisher()
    result = publisher.send({"event_type": "signup"})

    assert result == "msg-xyz"
    mock_pub.publish.assert_called_once()


@patch("ingestor.pubsub_v1.PublisherClient")
def test_event_publisher_send_many(MockClient):
    mock_pub = MockClient.return_value
    mock_pub.topic_path.return_value = "projects/p/topics/pulse-events"
    counter = [0]

    def make_future(*args, **kwargs):
        counter[0] += 1
        f = MagicMock()
        f.result.return_value = f"msg-{counter[0]}"
        return f

    mock_pub.publish.side_effect = make_future

    publisher = EventPublisher()
    results = publisher.send_many([{"event_type": "click"}, {"event_type": "view"}])

    assert len(results) == 2
    assert results[0] == "msg-1"
    assert results[1] == "msg-2"
