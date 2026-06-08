from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from session_store import (
    SessionRepository,
    delete_session,
    get_firestore_client,
    get_session,
    list_active_sessions,
    set_session,
)


@patch("session_store.firestore.Client")
def test_get_firestore_client(MockClient):
    result = get_firestore_client()
    MockClient.assert_called_once()
    assert result is MockClient.return_value


@patch("session_store.firestore.Client")
def test_set_session_calls_document_set(MockClient):
    db = MockClient.return_value
    set_session("user-1", {"plan": "pro"})
    db.collection.assert_called_with("user_sessions")
    db.collection().document.assert_called_with("user-1")
    db.collection().document().set.assert_called_once()


@patch("session_store.firestore.Client")
def test_get_session_returns_dict_when_found(MockClient):
    db = MockClient.return_value
    mock_doc = MagicMock()
    mock_doc.exists = True
    mock_doc.to_dict.return_value = {"plan": "pro"}
    db.collection().document().get.return_value = mock_doc

    result = get_session("user-1")

    assert result == {"plan": "pro"}


@patch("session_store.firestore.Client")
def test_get_session_returns_none_when_missing(MockClient):
    db = MockClient.return_value
    mock_doc = MagicMock()
    mock_doc.exists = False
    db.collection().document().get.return_value = mock_doc

    assert get_session("ghost") is None


@patch("session_store.firestore.Client")
def test_delete_session_calls_delete(MockClient):
    db = MockClient.return_value
    delete_session("user-1")
    db.collection().document().delete.assert_called_once()


@patch("session_store.firestore.Client")
def test_list_active_sessions_returns_enriched_dicts(MockClient):
    db = MockClient.return_value
    doc_a = MagicMock()
    doc_a.id = "user-1"
    doc_a.to_dict.return_value = {"plan": "free"}
    doc_b = MagicMock()
    doc_b.id = "user-2"
    doc_b.to_dict.return_value = {"plan": "pro"}
    db.collection().where().stream.return_value = [doc_a, doc_b]

    since = datetime(2026, 6, 1, tzinfo=timezone.utc)
    results = list_active_sessions(since)

    assert results == [
        {"plan": "free", "user_id": "user-1"},
        {"plan": "pro", "user_id": "user-2"},
    ]


@patch("session_store.firestore.Client")
def test_session_repository_save(MockClient):
    db = MockClient.return_value
    repo = SessionRepository()
    repo.save("user-3", {"plan": "enterprise"})
    db.collection().document().set.assert_called_once()


@patch("session_store.firestore.Client")
def test_session_repository_load_found(MockClient):
    db = MockClient.return_value
    mock_doc = MagicMock()
    mock_doc.exists = True
    mock_doc.to_dict.return_value = {"plan": "enterprise"}
    db.collection().document().get.return_value = mock_doc

    repo = SessionRepository()
    result = repo.load("user-3")

    assert result == {"plan": "enterprise"}


@patch("session_store.firestore.Client")
def test_session_repository_remove(MockClient):
    db = MockClient.return_value
    repo = SessionRepository()
    repo.remove("user-1")
    db.collection().document().delete.assert_called_once()


@patch("session_store.firestore.Client")
def test_session_repository_active_since(MockClient):
    db = MockClient.return_value
    doc = MagicMock()
    doc.id = "user-5"
    doc.to_dict.return_value = {"plan": "free"}
    db.collection().where().stream.return_value = [doc]

    repo = SessionRepository()
    results = repo.active_since(datetime(2026, 6, 1, tzinfo=timezone.utc))

    assert results == [{"plan": "free", "user_id": "user-5"}]
