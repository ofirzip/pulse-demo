"""session_store.py — reads and writes user session state to Firestore."""

from __future__ import annotations

import logging
from datetime import datetime

from google.cloud import firestore

PROJECT_ID = "pulse-analytics-prod"
COLLECTION_NAME = "user_sessions"

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Direct / explicit calls
# ---------------------------------------------------------------------------


def get_firestore_client() -> firestore.Client:
    return firestore.Client(project=PROJECT_ID)


def set_session(user_id: str, session_data: dict) -> None:
    """Write (or overwrite) a user session document."""
    db = firestore.Client(project=PROJECT_ID)
    db.collection(COLLECTION_NAME).document(user_id).set(
        {**session_data, "updated_at": firestore.SERVER_TIMESTAMP}
    )
    logger.info("Set session for user %s", user_id)


def get_session(user_id: str) -> dict | None:
    """Return session dict for the user, or None if absent."""
    db = firestore.Client(project=PROJECT_ID)
    doc = db.collection(COLLECTION_NAME).document(user_id).get()
    return doc.to_dict() if doc.exists else None


def delete_session(user_id: str) -> None:
    """Delete a user's session document."""
    db = firestore.Client(project=PROJECT_ID)
    db.collection(COLLECTION_NAME).document(user_id).delete()
    logger.info("Deleted session for user %s", user_id)


def list_active_sessions(since: datetime) -> list[dict]:
    """Return all sessions updated at or after `since`."""
    db = firestore.Client(project=PROJECT_ID)
    docs = (
        db.collection(COLLECTION_NAME)
        .where("updated_at", ">=", since)
        .stream()
    )
    sessions = [doc.to_dict() | {"user_id": doc.id} for doc in docs]
    logger.info("Found %d active sessions since %s", len(sessions), since)
    return sessions


# ---------------------------------------------------------------------------
# Abstracted: all Firestore calls hidden inside SessionRepository
# ---------------------------------------------------------------------------


class SessionRepository:
    """Thin repository over Firestore — direct calls are inside instance methods."""

    def __init__(self, project_id: str = PROJECT_ID) -> None:
        self._client = firestore.Client(project=project_id)
        self._col = self._client.collection(COLLECTION_NAME)

    def save(self, user_id: str, data: dict) -> None:
        self._col.document(user_id).set(
            {**data, "updated_at": firestore.SERVER_TIMESTAMP}
        )

    def load(self, user_id: str) -> dict | None:
        doc = self._col.document(user_id).get()
        return doc.to_dict() if doc.exists else None

    def remove(self, user_id: str) -> None:
        self._col.document(user_id).delete()

    def active_since(self, since: datetime) -> list[dict]:
        docs = self._col.where("updated_at", ">=", since).stream()
        return [d.to_dict() | {"user_id": d.id} for d in docs]
