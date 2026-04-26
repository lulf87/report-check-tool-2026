from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.models.report_self_check import CheckResult, CheckStatus, Confidence
from app.services.codex_judge_client import CodexJudgeClient, CodexJudgeRuntimeError


def test_health_endpoint():
    client = TestClient(app)
    response = client.get("/api/report-self-check/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_check_upload_rejects_non_pdf():
    client = TestClient(app)
    response = client.post(
        "/api/report-self-check/check",
        files={"file": ("sample.txt", b"not a pdf", "text/plain")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Only PDF files are supported"


def test_check_start_rejects_non_pdf():
    client = TestClient(app)
    response = client.post(
        "/api/report-self-check/check/start",
        files={"file": ("sample.txt", b"not a pdf", "text/plain")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Only PDF files are supported"


def test_check_upload_rejects_invalid_pdf_without_calling_codex(monkeypatch):
    def fail_if_called():
        raise AssertionError("ReportSelfCheckService should not be called for invalid PDFs")

    monkeypatch.setattr("app.routers.report_self_check.ReportSelfCheckService", fail_if_called)

    client = TestClient(app)
    response = client.post(
        "/api/report-self-check/check",
        files={"file": ("fake.pdf", b"not a pdf", "application/pdf")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid PDF file"


def test_get_unknown_task_returns_404():
    client = TestClient(app)
    response = client.get("/api/report-self-check/tasks/not-found")

    assert response.status_code == 404
    assert response.json()["detail"] == "Task not found"


def test_check_upload_sample_pdf_uses_full_pipeline_without_live_codex(monkeypatch):
    expected_check_ids = [
        "C00",
        "C01",
        "C02",
        "C03",
        "C04",
        "C06",
        "C07",
        "C08",
        "C12",
        "C13",
        "C14",
        "C15",
        "C16",
    ]
    sample_pdf = Path(__file__).resolve().parents[2] / "素材" / "report" / "3940" / "3940.pdf"

    def mock_judge(self, evidence_package: dict) -> CheckResult:
        return CheckResult(
            check_id=str(evidence_package["check_id"]),
            check_name=str(evidence_package["check_name"]),
            status=CheckStatus.PASS,
            confidence=Confidence.HIGH,
            summary="mocked pass",
            details={
                "source": "mock_codex_judge",
                "evidence_keys": sorted(evidence_package.keys()),
            },
        )

    monkeypatch.setattr(CodexJudgeClient, "judge", mock_judge)

    client = TestClient(app)
    with sample_pdf.open("rb") as file_obj:
        response = client.post(
            "/api/report-self-check/check",
            files={"file": ("3940.pdf", file_obj, "application/pdf")},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["total_checks"] == 13
    assert [item["check_id"] for item in payload["check_results"]] == expected_check_ids
    assert all(item["details"] for item in payload["check_results"])


def test_check_start_sample_pdf_exposes_progress_without_live_codex(monkeypatch):
    expected_check_ids = [
        "C00",
        "C01",
        "C02",
        "C03",
        "C04",
        "C06",
        "C07",
        "C08",
        "C12",
        "C13",
        "C14",
        "C15",
        "C16",
    ]
    sample_pdf = Path(__file__).resolve().parents[2] / "素材" / "report" / "3940" / "3940.pdf"

    def mock_judge(self, evidence_package: dict) -> CheckResult:
        return CheckResult(
            check_id=str(evidence_package["check_id"]),
            check_name=str(evidence_package["check_name"]),
            status=CheckStatus.PASS,
            confidence=Confidence.HIGH,
            summary="mocked pass",
            details={"source": "mock_codex_judge"},
        )

    monkeypatch.setattr(CodexJudgeClient, "judge", mock_judge)

    client = TestClient(app)
    with sample_pdf.open("rb") as file_obj:
        response = client.post(
            "/api/report-self-check/check/start",
            files={"file": ("3940.pdf", file_obj, "application/pdf")},
        )

    assert response.status_code == 200
    start_payload = response.json()
    task_response = client.get(f"/api/report-self-check/tasks/{start_payload['task_id']}")

    assert task_response.status_code == 200
    task_payload = task_response.json()
    assert task_payload["status"] == "completed"
    assert task_payload["completed_checks"] == 13
    assert task_payload["total_checks"] == 13
    assert task_payload["logs"]
    assert task_payload["result"]["summary"]["total_checks"] == 13
    assert [item["check_id"] for item in task_payload["result"]["check_results"]] == expected_check_ids


def test_check_start_marks_task_error_when_codex_runtime_fails(monkeypatch):
    sample_pdf = Path(__file__).resolve().parents[2] / "素材" / "report" / "3940" / "3940.pdf"

    def mock_judge(self, evidence_package: dict) -> CheckResult:
        raise CodexJudgeRuntimeError("Codex 调用失败：model unavailable")

    monkeypatch.setattr(CodexJudgeClient, "judge", mock_judge)

    client = TestClient(app)
    with sample_pdf.open("rb") as file_obj:
        response = client.post(
            "/api/report-self-check/check/start",
            files={"file": ("3940.pdf", file_obj, "application/pdf")},
        )

    assert response.status_code == 200
    start_payload = response.json()
    task_response = client.get(f"/api/report-self-check/tasks/{start_payload['task_id']}")

    assert task_response.status_code == 200
    task_payload = task_response.json()
    assert task_payload["status"] == "error"
    assert "model unavailable" in task_payload["error"]
    assert task_payload["result"] is None
