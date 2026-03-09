from types import SimpleNamespace
from unittest.mock import MagicMock, patch


def test_start_flood_and_classification_jobs(client, mock_auth, auth_headers):
    with patch(
        "app.api.v1.endpoints.jobs.analyze_flood_task.delay",
        return_value=SimpleNamespace(id="job-flood-1"),
    ), patch(
        "app.api.v1.endpoints.jobs.supervised_classification_task.delay",
        return_value=SimpleNamespace(id="job-class-1"),
    ):
        flood_response = client.post(
            "/api/v1/jobs/flood-analysis",
            headers=auth_headers,
            json={"start_date": "2026-01-01", "end_date": "2026-01-10", "method": "fusion"},
        )
        class_response = client.post(
            "/api/v1/jobs/classification?start_date=2026-01-01&end_date=2026-01-10",
            headers=auth_headers,
            json={},
        )

    assert flood_response.status_code == 200
    assert flood_response.json()["job_id"] == "job-flood-1"
    assert class_response.status_code == 200
    assert class_response.json()["job_id"] == "job-class-1"


def test_get_job_status_returns_pending_or_result(client, mock_auth, auth_headers):
    pending = MagicMock()
    pending.status = "PENDING"
    pending.ready.return_value = False

    done = MagicMock()
    done.status = "SUCCESS"
    done.ready.return_value = True
    done.successful.return_value = True
    done.result = {"ok": True}

    failed = MagicMock()
    failed.status = "FAILURE"
    failed.ready.return_value = True
    failed.successful.return_value = False
    failed.result = RuntimeError("failed")

    with patch("app.api.v1.endpoints.jobs.AsyncResult", side_effect=[pending, done, failed]):
        pending_response = client.get("/api/v1/jobs/job-1", headers=auth_headers)
        done_response = client.get("/api/v1/jobs/job-2", headers=auth_headers)
        fail_response = client.get("/api/v1/jobs/job-3", headers=auth_headers)

    assert pending_response.status_code == 200
    assert pending_response.json()["status"] == "PENDING"
    assert done_response.json()["result"] == {"ok": True}
    assert "failed" in fail_response.json()["error"]
