from unittest.mock import MagicMock, patch

import pytest

from report_exporter import (
    ReportExporter,
    delete_old_report,
    list_existing_reports,
    results_to_csv,
    run_aggregation_query,
    upload_report,
)


@patch("report_exporter.bigquery.Client")
def test_run_aggregation_query_returns_list_of_dicts(MockBQ):
    fake_row = {"event_type": "click", "count": 5}
    MockBQ.return_value.query.return_value.result.return_value = [fake_row]

    result = run_aggregation_query("SELECT 1")

    assert result == [{"event_type": "click", "count": 5}]
    MockBQ.return_value.query.assert_called_once_with("SELECT 1")


def test_results_to_csv_empty():
    assert results_to_csv([]) == ""


def test_results_to_csv_produces_header_and_rows():
    rows = [
        {"event_type": "click", "count": 3},
        {"event_type": "view", "count": 10},
    ]
    csv_str = results_to_csv(rows)
    assert "event_type" in csv_str
    assert "count" in csv_str
    assert "click" in csv_str
    assert "view" in csv_str
    assert csv_str.count("\n") == 3  # header + 2 rows + trailing newline


@patch("report_exporter.storage.Client")
def test_upload_report_returns_gs_uri(MockStorage):
    mock_blob = MagicMock()
    MockStorage.return_value.bucket.return_value.blob.return_value = mock_blob

    uri = upload_report("my-bucket", "reports/r.csv", "col1,col2\n1,2\n")

    assert uri == "gs://my-bucket/reports/r.csv"
    mock_blob.upload_from_string.assert_called_once_with(
        "col1,col2\n1,2\n", content_type="text/csv"
    )


@patch("report_exporter.storage.Client")
def test_list_existing_reports(MockStorage):
    blob_a = MagicMock()
    blob_a.name = "daily/2026-06-07.csv"
    MockStorage.return_value.list_blobs.return_value = [blob_a]

    names = list_existing_reports("my-bucket", "daily/")

    assert names == ["daily/2026-06-07.csv"]
    MockStorage.return_value.list_blobs.assert_called_once_with(
        "my-bucket", prefix="daily/"
    )


@patch("report_exporter.storage.Client")
def test_delete_old_report(MockStorage):
    mock_blob = MagicMock()
    MockStorage.return_value.bucket.return_value.blob.return_value = mock_blob

    delete_old_report("my-bucket", "daily/old.csv")

    mock_blob.delete.assert_called_once()


@patch("report_exporter.storage.Client")
@patch("report_exporter.bigquery.Client")
def test_report_exporter_export_returns_uri(MockBQ, MockStorage):
    fake_row = {"event_type": "click", "count": 5}
    MockBQ.return_value.query.return_value.result.return_value = [fake_row]
    mock_blob = MagicMock()
    MockStorage.return_value.bucket.return_value.blob.return_value = mock_blob

    exporter = ReportExporter(bucket_name="test-bucket")
    uri = exporter.export("SELECT 1", "daily/test.csv")

    assert uri == "gs://test-bucket/daily/test.csv"
    mock_blob.upload_from_string.assert_called_once()


@patch("report_exporter.storage.Client")
@patch("report_exporter.bigquery.Client")
def test_report_exporter_upload_to_gcs_is_private(MockBQ, MockStorage):
    """_upload_to_gcs is the abstracted path — verify it's not top-level."""
    exporter = ReportExporter()
    assert callable(exporter._upload_to_gcs)
    assert not hasattr(report_exporter, "_upload_to_gcs")  # not a module-level symbol


import report_exporter  # noqa: E402 (needed for the attribute check above)
