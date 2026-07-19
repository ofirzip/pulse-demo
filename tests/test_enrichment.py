from unittest.mock import MagicMock, patch

import pytest

from enrichment import ANTHROPIC_API_KEY, EventEnricher, enrich_event, load_api_key


@pytest.fixture(autouse=True)
def mock_secret_manager():
    """Stub Secret Manager so no real client/credentials are needed in tests."""
    with patch("enrichment.secretmanager.SecretManagerServiceClient") as mock_cls:
        client = mock_cls.return_value
        client.access_secret_version.return_value.payload.data = b"sk-ant-from-secret-manager"
        yield client


def test_load_api_key_prefers_secret_manager(mock_secret_manager):
    assert load_api_key() == "sk-ant-from-secret-manager"
    mock_secret_manager.access_secret_version.assert_called_once()


def test_load_api_key_falls_back_to_embedded_key(mock_secret_manager):
    mock_secret_manager.access_secret_version.side_effect = RuntimeError("no creds")
    assert load_api_key() == ANTHROPIC_API_KEY


def _mock_response(text):
    """Build a fake anthropic messages.create() response with the given text."""
    block = MagicMock()
    block.text = text
    resp = MagicMock()
    resp.content = [block]
    return resp


@patch("enrichment.anthropic.Anthropic")
def test_enrich_event_returns_category(MockAnthropic):
    MockAnthropic.return_value.messages.create.return_value = _mock_response("engagement")

    category = enrich_event({"user_id": "u1", "event_type": "click"})

    assert category == "engagement"
    MockAnthropic.return_value.messages.create.assert_called_once()


@patch("enrichment.anthropic.Anthropic")
def test_enrich_event_sends_user_data_to_the_model(MockAnthropic):
    """The full event payload (incl. user_id / properties) is placed in the prompt."""
    MockAnthropic.return_value.messages.create.return_value = _mock_response("churn_risk")

    enrich_event({"user_id": "u-42", "properties": {"plan": "pro"}})

    _, kwargs = MockAnthropic.return_value.messages.create.call_args
    prompt = kwargs["messages"][0]["content"]
    assert "u-42" in prompt
    assert "pro" in prompt


@patch("enrichment.anthropic.Anthropic")
def test_enrich_batch_augments_each_event(MockAnthropic):
    MockAnthropic.return_value.messages.create.return_value = _mock_response("onboarding")

    enricher = EventEnricher()
    result = enricher.enrich_batch([{"user_id": "a"}, {"user_id": "b"}])

    assert [e["category"] for e in result] == ["onboarding", "onboarding"]
    assert result[0]["user_id"] == "a"
    assert MockAnthropic.return_value.messages.create.call_count == 2


@patch("enrichment.anthropic.Anthropic")
def test_enrich_batch_is_the_abstracted_path(MockAnthropic):
    """The model call is hidden inside EventEnricher, not a module-level symbol."""
    import enrichment

    enricher = EventEnricher()
    assert callable(enricher.enrich_batch)
    assert not hasattr(enrichment, "enrich_batch")
