from unittest.mock import MagicMock, patch

from enrichment import EventEnricher, enrich_event


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
