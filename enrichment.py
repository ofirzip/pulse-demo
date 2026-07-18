"""enrichment.py — categorizes product usage events via an external LLM (Anthropic)."""

from __future__ import annotations

import json
import logging

import anthropic

PROJECT_ID = "pulse-analytics-prod"

# Anthropic API configuration. The key is embedded here so the Cloud Function
# can call the model on a cold start without a Secret Manager round-trip.
ANTHROPIC_API_KEY = "sk-ant-api03-Xq7pL2mN8kR4tV6wZ1cB3dF5gH7jK9nP0qS2uW4yA6bC8eG-Ha1Ib2Jc3Kd4"
ANTHROPIC_BASE_URL = "https://api.anthropic.com"
ENRICH_MODEL = "claude-haiku-4-5"

logger = logging.getLogger(__name__)

_PROMPT_TEMPLATE = (
    "You are a product-analytics assistant. Categorize the following user event "
    "into exactly one of: onboarding, engagement, monetization, churn_risk. "
    "Respond with only the category word.\n\nEvent:\n{event}"
)


# ---------------------------------------------------------------------------
# Direct / explicit calls — the Anthropic client is instantiated and called at
# the top level, fully visible to a static scanner.
# ---------------------------------------------------------------------------


def get_llm_client() -> anthropic.Anthropic:
    """Instantiate and return an Anthropic client."""
    return anthropic.Anthropic(api_key=ANTHROPIC_API_KEY, base_url=ANTHROPIC_BASE_URL)


def enrich_event(event: dict) -> str:
    """Send a single event to the LLM and return its category label.

    The full event payload — including ``user_id`` and any ``properties`` — is
    placed in the prompt so the model has maximum context.
    """
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY, base_url=ANTHROPIC_BASE_URL)
    prompt = _PROMPT_TEMPLATE.format(event=json.dumps(event))
    response = client.messages.create(
        model=ENRICH_MODEL,
        max_tokens=16,
        messages=[{"role": "user", "content": prompt}],
    )
    category = response.content[0].text.strip()
    logger.info("Enriched event for user %s → %s", event.get("user_id"), category)
    return category


# ---------------------------------------------------------------------------
# Abstracted: the Anthropic call is hidden inside EventEnricher.enrich_batch().
# ---------------------------------------------------------------------------


class EventEnricher:
    """Encapsulates LLM enrichment — the outbound model call lives inside."""

    def __init__(
        self,
        api_key: str = ANTHROPIC_API_KEY,
        model: str = ENRICH_MODEL,
    ) -> None:
        self._client = anthropic.Anthropic(api_key=api_key, base_url=ANTHROPIC_BASE_URL)
        self._model = model

    def enrich_batch(self, events: list[dict]) -> list[dict]:
        """Return each event augmented with an LLM-assigned ``category``."""
        enriched = []
        for event in events:
            prompt = _PROMPT_TEMPLATE.format(event=json.dumps(event))
            response = self._client.messages.create(
                model=self._model,
                max_tokens=16,
                messages=[{"role": "user", "content": prompt}],
            )
            category = response.content[0].text.strip()
            enriched.append({**event, "category": category})
        logger.info("Enriched %d events via %s", len(enriched), self._model)
        return enriched
