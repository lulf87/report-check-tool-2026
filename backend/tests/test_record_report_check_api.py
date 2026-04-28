from typing import Any

from fastapi.testclient import TestClient

from app.main import app
from app.models.report_self_check import CheckResult, CheckStatus, Confidence
from app.services.record_report_check_service import RecordReportCheckResult


class FakeRecordReportCheckService:
    def check_extracted_pair(
        self,
        extracted_record: dict[str, Any],
        extracted_report: dict[str, Any],
        task_id: str | None = None,
        progress_callback=None,
        record_report_mode: str = "quick",
        record_report_concurrency: int = 4,
    ) -> RecordReportCheckResult:
        package = {
            "check_id": "RECORD-REPORT-GB9706-1",
            "check_name": "原始记录 vs 报告 GB 9706.1-2020 序号级核对",
        }
        if progress_callback is not None:
            progress_callback({"event": "start", "index": 1, "total": 1, "package": package})

        check_result = CheckResult(
            check_id=package["check_id"],
            check_name=package["check_name"],
            status=CheckStatus.PASS,
            confidence=Confidence.HIGH,
            summary="mocked record-report pass",
            details={
                "record_file": extracted_record["file_name"],
                "report_file": extracted_report["file_name"],
                "record_report_mode": record_report_mode,
                "record_report_concurrency": record_report_concurrency,
            },
        )
        if progress_callback is not None:
            progress_callback(
                {
                    "event": "done",
                    "index": 1,
                    "completed": 1,
                    "total": 1,
                    "package": package,
                    "result": check_result,
                }
            )

        result = RecordReportCheckResult(
            task_id=task_id or "task-record-report",
            file_name=extracted_report["file_name"],
            record_file_name=extracted_record["file_name"],
            report_file_name=extracted_report["file_name"],
            record_report_mode=record_report_mode,
            record_report_concurrency=record_report_concurrency,
            record_report_summary={"matched_count": 1},
            check_results=[check_result],
        )
        result.refresh_summary()
        return result


async def _fake_loader(record_file, report_file) -> tuple[dict[str, Any], dict[str, Any]]:
    return (
        {"file_name": record_file.filename, "pages": [], "_render_dir": ""},
        {"file_name": report_file.filename, "pages": [], "_render_dir": ""},
    )


def test_record_report_check_rejects_non_pdf():
    client = TestClient(app)
    response = client.post(
        "/api/report-self-check/record-report/check",
        files={
            "record_file": ("record.txt", b"not a pdf", "text/plain"),
            "report_file": ("report.pdf", b"%PDF-1.4\n%%EOF", "application/pdf"),
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Only PDF files are supported"


def test_record_report_check_uses_record_and_report_file_fields(monkeypatch):
    monkeypatch.setattr("app.routers.report_self_check._load_record_report_pdf_pair", _fake_loader)
    monkeypatch.setattr("app.routers.report_self_check.RecordReportCheckService", FakeRecordReportCheckService)

    client = TestClient(app)
    response = client.post(
        "/api/report-self-check/record-report/check",
        files={
            "record_file": ("record.pdf", b"record bytes", "application/pdf"),
            "report_file": ("report.pdf", b"report bytes", "application/pdf"),
        },
        data={"record_report_mode": "full", "record_report_concurrency": "12"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["record_file_name"] == "record.pdf"
    assert payload["report_file_name"] == "report.pdf"
    assert payload["record_report_mode"] == "full_codex"
    assert payload["record_report_concurrency"] == 8
    assert payload["summary"]["pass_count"] == 1
    assert payload["check_results"][0]["details"] == {
        "record_file": "record.pdf",
        "report_file": "report.pdf",
        "record_report_mode": "full_codex",
        "record_report_concurrency": 8,
    }


def test_record_report_check_start_completes_task(monkeypatch):
    monkeypatch.setattr("app.routers.report_self_check._load_record_report_pdf_pair", _fake_loader)
    monkeypatch.setattr("app.routers.report_self_check.RecordReportCheckService", FakeRecordReportCheckService)

    client = TestClient(app)
    response = client.post(
        "/api/report-self-check/record-report/check/start",
        files={
            "record_file": ("record.pdf", b"record bytes", "application/pdf"),
            "report_file": ("report.pdf", b"report bytes", "application/pdf"),
        },
        data={"record_report_mode": "full_codex", "record_report_concurrency": "6"},
    )

    assert response.status_code == 200
    task = client.get(f"/api/report-self-check/tasks/{response.json()['task_id']}").json()
    assert task["status"] == "completed"
    assert task["record_report_mode"] == "full_codex"
    assert task["record_report_concurrency"] == 6
    assert task["completed_checks"] == 1
    assert task["total_checks"] == 1
    assert any("record-report" in log for log in task["logs"])
    assert task["result"]["record_file_name"] == "record.pdf"
    assert task["result"]["record_report_mode"] == "full_codex"
    assert task["result"]["record_report_concurrency"] == 6
