from typing import Any

from app.models.report_self_check import CheckResult, CheckStatus, Confidence
from app.services.ptr_report_check_service import PtrReportCheckService


class FakeBuilder:
    def __init__(self):
        self.calls: list[tuple[dict[str, Any], dict[str, Any]]] = []

    def build_all(self, extracted_ptr: dict[str, Any], extracted_report: dict[str, Any]) -> list[dict[str, Any]]:
        self.calls.append((extracted_ptr, extracted_report))
        return [
            {
                "check_id": "PTR-SCOPE-COVERAGE",
                "check_name": "PTR 与报告检验项目范围覆盖总览",
                "evidence": {
                    "scope_coverage": {
                        "declared_clause_prefixes": ["2.2"],
                        "actual_report_clause_prefixes": ["2.2"],
                        "missing_declared_clause_prefixes": [],
                    }
                },
                "deterministic_result": {
                    "check_id": "PTR-SCOPE-COVERAGE",
                    "check_name": "PTR 与报告检验项目范围覆盖总览",
                    "status": "pass",
                    "confidence": "high",
                    "summary": "报告实际条款覆盖首页声明范围。",
                    "details": {
                        "scope_coverage": {
                            "declared_clause_prefixes": ["2.2"],
                            "actual_report_clause_prefixes": ["2.2"],
                            "missing_declared_clause_prefixes": [],
                        }
                    },
                    "findings": [],
                    "evidence": [],
                    "missing_evidence": [],
                },
            },
            {
                "check_id": "PTR01",
                "check_name": "产品名称一致性",
                "evidence": {"ptr": "a", "report": "a"},
            },
            {
                "check_id": "PTR02",
                "check_name": "型号规格一致性",
                "evidence": {"ptr": "b", "report": "c"},
                "image_paths": ["/tmp/ptr-page-001.png"],
            },
        ]


class FakeJudge:
    def __init__(self):
        self.packages: list[dict[str, Any]] = []

    def judge(self, package: dict[str, Any]) -> CheckResult:
        self.packages.append(package)
        status = CheckStatus.PASS if package["check_id"] == "PTR01" else CheckStatus.WARNING
        return CheckResult(
            check_id=str(package["check_id"]),
            check_name=str(package["check_name"]),
            status=status,
            confidence=Confidence.HIGH,
            summary=f"{package['check_id']} judged",
            details={"has_images": bool(package.get("image_paths"))},
        )


def test_ptr_service_builds_packages_judges_each_package_and_refreshes_summary():
    builder = FakeBuilder()
    judge = FakeJudge()
    service = PtrReportCheckService(evidence_builder=builder, judge_client=judge)
    extracted_ptr = {"file_name": "ptr.pdf", "pages": []}
    extracted_report = {"file_name": "report.pdf", "pages": []}

    result = service.check_extracted_pair(extracted_ptr, extracted_report, task_id="task-ptr")

    assert builder.calls == [(extracted_ptr, extracted_report)]
    assert [package["check_id"] for package in judge.packages] == ["PTR01", "PTR02"]
    assert judge.packages[1]["image_paths"] == ["/tmp/ptr-page-001.png"]
    assert result.task_id == "task-ptr"
    assert result.file_name == "report.pdf"
    assert result.ptr_file_name == "ptr.pdf"
    assert result.report_file_name == "report.pdf"
    assert result.summary.total_checks == 3
    assert result.summary.pass_count == 2
    assert result.summary.warning_count == 1
    assert result.summary.error_count == 0
    assert result.overall_status == CheckStatus.WARNING


def test_ptr_service_progress_callback_receives_start_and_done_events():
    events: list[dict[str, Any]] = []
    service = PtrReportCheckService(evidence_builder=FakeBuilder(), judge_client=FakeJudge())

    service.check_extracted_pair(
        {"file_name": "ptr.pdf", "pages": []},
        {"file_name": "report.pdf", "pages": []},
        progress_callback=events.append,
    )

    assert [event["event"] for event in events] == ["start", "done", "start", "done", "start", "done"]
    assert [event["index"] for event in events] == [1, 1, 2, 2, 3, 3]
    assert all(event["total"] == 3 for event in events)
    assert events[0]["package"]["check_id"] == "PTR-SCOPE-COVERAGE"
    assert events[1]["result"].check_id == "PTR-SCOPE-COVERAGE"
