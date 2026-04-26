from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.report_self_check import CheckResult, CheckStatus, Confidence
from app.services.codex_judge_client import CodexJudgeClient


WORKTREE_ROOT = Path(__file__).resolve().parents[2]
PTR_3940 = WORKTREE_ROOT / "素材" / "ptr" / "3940" / "3940 产品技术要求 Edora 8 改批注zx260218 260225更新.pdf"
REPORT_3940 = WORKTREE_ROOT / "素材" / "report" / "3940" / "3940.pdf"
requires_local_3940 = pytest.mark.skipif(
    not PTR_3940.exists() or not REPORT_3940.exists(),
    reason="local 3940 PDF fixtures are not committed to the repository",
)


class FakePtrReportEvidenceBuilder:
    def build_all(self, extracted_ptr: dict[str, Any], extracted_report: dict[str, Any]) -> list[dict[str, Any]]:
        assert extracted_ptr["file_name"].endswith(".pdf")
        assert extracted_report["file_name"] == "3940.pdf"
        ptr_images = [
            str(page["image_path"])
            for page in extracted_ptr["pages"]
            if page.get("image_path")
        ]
        return [
            {
                "check_id": "PTR01",
                "check_name": "PTR 与报告首页一致性",
                "evidence": {
                    "ptr_page_count": extracted_ptr["page_count"],
                    "report_page_count": extracted_report["page_count"],
                },
                "image_paths": ptr_images[:1],
            },
            {
                "check_id": "PTR02",
                "check_name": "PTR 与报告检验项目一致性",
                "evidence": {
                    "ptr_file_name": extracted_ptr["file_name"],
                    "report_file_name": extracted_report["file_name"],
                },
            },
        ]


def test_ptr_report_check_rejects_non_pdf():
    client = TestClient(app)
    response = client.post(
        "/api/report-self-check/ptr-report/check",
        files={
            "ptr_file": ("ptr.txt", b"not a pdf", "text/plain"),
            "report_file": ("report.pdf", b"%PDF-1.4\n%%EOF", "application/pdf"),
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Only PDF files are supported"


def test_ptr_report_check_rejects_invalid_pdf_without_calling_service(monkeypatch):
    def fail_if_called():
        raise AssertionError("PtrReportCheckService should not be called for invalid PDFs")

    monkeypatch.setattr("app.routers.report_self_check.PtrReportCheckService", fail_if_called)

    client = TestClient(app)
    response = client.post(
        "/api/report-self-check/ptr-report/check",
        files={
            "ptr_file": ("ptr.pdf", b"not a pdf", "application/pdf"),
            "report_file": ("report.pdf", b"not a pdf either", "application/pdf"),
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid PDF file"


@requires_local_3940
def test_ptr_report_check_sample_pair_uses_pipeline_without_live_codex(monkeypatch):
    monkeypatch.setattr(
        "app.services.ptr_report_check_service.PtrReportEvidenceBuilder",
        FakePtrReportEvidenceBuilder,
    )

    def mock_judge(self, evidence_package: dict[str, Any]) -> CheckResult:
        return CheckResult(
            check_id=str(evidence_package["check_id"]),
            check_name=str(evidence_package["check_name"]),
            status=CheckStatus.PASS,
            confidence=Confidence.HIGH,
            summary="mocked ptr-report pass",
            details={
                "source": "mock_codex_judge",
                "received_image_paths": evidence_package.get("image_paths", []),
            },
        )

    monkeypatch.setattr(CodexJudgeClient, "judge", mock_judge)

    client = TestClient(app)
    with PTR_3940.open("rb") as ptr_file_obj, REPORT_3940.open("rb") as report_file_obj:
        response = client.post(
            "/api/report-self-check/ptr-report/check",
            files={
                "ptr_file": (PTR_3940.name, ptr_file_obj, "application/pdf"),
                "report_file": ("3940.pdf", report_file_obj, "application/pdf"),
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ptr_file_name"] == PTR_3940.name
    assert payload["report_file_name"] == "3940.pdf"
    assert payload["summary"]["total_checks"] == 2
    assert payload["summary"]["pass_count"] == 2
    assert [item["check_id"] for item in payload["check_results"]] == ["PTR01", "PTR02"]
    assert "received_image_paths" in payload["check_results"][0]["details"]


@requires_local_3940
def test_ptr_report_check_sample_pair_uses_actual_scope_builder_without_live_codex(monkeypatch):
    def mock_judge(self, evidence_package: dict[str, Any]) -> CheckResult:
        evidence = evidence_package["evidence"]
        return CheckResult(
            check_id=str(evidence_package["check_id"]),
            check_name=str(evidence_package["check_name"]),
            status=CheckStatus.PASS,
            confidence=Confidence.HIGH,
            summary="mocked ptr-report pass",
            details={
                "ptr_clause_prefix": evidence["ptr_clause_prefix"],
                "ptr_clause_count": len(evidence["ptr_clauses"]),
                "candidate_page_count": len(evidence["report_candidate_pages"]),
            },
        )

    monkeypatch.setattr(CodexJudgeClient, "judge", mock_judge)

    client = TestClient(app)
    with PTR_3940.open("rb") as ptr_file_obj, REPORT_3940.open("rb") as report_file_obj:
        response = client.post(
            "/api/report-self-check/ptr-report/check",
            files={
                "ptr_file": (PTR_3940.name, ptr_file_obj, "application/pdf"),
                "report_file": ("3940.pdf", report_file_obj, "application/pdf"),
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert [item["check_id"] for item in payload["check_results"]] == [
        "PTR-SCOPE-COVERAGE",
        "PTR-2.1",
        "PTR-2.7",
        "PTR-2.10",
    ]
    assert payload["homepage_scope"]["included_clause_prefixes"] == ["2.1", "2.7", "2.10"]
    assert payload["ptr_report_scope_summary"]["missing_declared_clause_prefixes"] == ["2.1.6"]
    assert payload["check_results"][1]["details"]["ptr_clause_count"] > 0
    assert payload["check_results"][1]["details"]["candidate_page_count"] > 0
    assert any(item["prefix"] == "2.1.2" for item in payload["check_results"][1]["details"]["leaf_clause_reviews"])


@requires_local_3940
def test_ptr_report_check_start_sample_pair_completes_task(monkeypatch):
    monkeypatch.setattr(
        "app.services.ptr_report_check_service.PtrReportEvidenceBuilder",
        FakePtrReportEvidenceBuilder,
    )

    def mock_judge(self, evidence_package: dict[str, Any]) -> CheckResult:
        return CheckResult(
            check_id=str(evidence_package["check_id"]),
            check_name=str(evidence_package["check_name"]),
            status=CheckStatus.PASS,
            confidence=Confidence.HIGH,
            summary="mocked ptr-report pass",
            details={"source": "mock_codex_judge"},
        )

    monkeypatch.setattr(CodexJudgeClient, "judge", mock_judge)

    client = TestClient(app)
    with PTR_3940.open("rb") as ptr_file_obj, REPORT_3940.open("rb") as report_file_obj:
        response = client.post(
            "/api/report-self-check/ptr-report/check/start",
            files={
                "ptr_file": (PTR_3940.name, ptr_file_obj, "application/pdf"),
                "report_file": ("3940.pdf", report_file_obj, "application/pdf"),
            },
        )

    assert response.status_code == 200
    start_payload = response.json()
    task_response = client.get(f"/api/report-self-check/tasks/{start_payload['task_id']}")

    assert task_response.status_code == 200
    task_payload = task_response.json()
    assert task_payload["status"] == "completed"
    assert task_payload["completed_checks"] == 2
    assert task_payload["total_checks"] == 2
    assert any("PTR-report" in log for log in task_payload["logs"])
    assert task_payload["result"]["summary"]["total_checks"] == 2
    assert task_payload["result"]["ptr_file_name"] == PTR_3940.name
