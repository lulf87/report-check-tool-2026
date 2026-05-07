from typing import Any

from app.models.report_self_check import CheckResult, CheckStatus, Confidence, Finding, FindingSeverity, MissingEvidence
from app.services import record_report_check_service as record_report_service
from app.services.record_report_check_service import RecordReportCheckService


class FakeRecordReportEvidenceBuilder:
    def __init__(self, evidence: dict[str, Any]):
        self.evidence = evidence
        self.calls: list[tuple[dict[str, Any], dict[str, Any], str]] = []

    def build_all(
        self,
        extracted_record: dict[str, Any],
        extracted_report: dict[str, Any],
        record_report_standard: str = "gb9706_1",
    ) -> list[dict[str, Any]]:
        self.calls.append((extracted_record, extracted_report, record_report_standard))
        return [
            {
                "check_id": "RECORD-REPORT-GB9706-1",
                "check_name": "原始记录 vs 报告 GB 9706.1-2020 序号级核对",
                "evidence": self.evidence,
            }
        ]


class FakeJudge:
    def __init__(self):
        self.packages: list[dict[str, Any]] = []

    def judge(self, package: dict[str, Any]) -> CheckResult:
        self.packages.append(package)
        evidence = package["evidence"]
        status = CheckStatus(evidence.get("deterministic_status", "pass"))
        findings = []
        if status == CheckStatus.ERROR:
            findings.append(
                Finding(
                    severity=FindingSeverity.ERROR,
                    title="原始记录与报告判定不一致",
                    detail="fake mismatch",
                    expected=str(evidence.get("record_aggregate_judgement", "")),
                    actual=str(evidence.get("report_judgement", "")),
                    pages=[],
                    related_fields=["原始记录符合性", "报告单项结论"],
                )
            )
        if status == CheckStatus.WARNING:
            findings.append(
                Finding(
                    severity=FindingSeverity.WARNING,
                    title="原始记录证据缺失或无法映射",
                    detail="fake missing",
                    pages=[],
                    related_fields=["标准条款"],
                )
            )
        return CheckResult(
            check_id=str(package["check_id"]),
            check_name=str(package["check_name"]),
            status=status,
            confidence=Confidence.HIGH,
            summary=str(evidence.get("deterministic_summary", "fake")),
            details={"sequence": evidence.get("sequence")},
            findings=findings,
            missing_evidence=[
                MissingEvidence(label=f"报告序号 {evidence.get('sequence')} 原始记录映射", reason="fake missing")
            ]
            if status == CheckStatus.WARNING
            else [],
        )


def _clear_judge_cache() -> None:
    with record_report_service._JUDGE_CACHE_LOCK:
        record_report_service._JUDGE_CACHE.clear()


def _happy_evidence() -> dict[str, Any]:
    return {
        "record_report_standard": "gb9706_1",
        "record_file_name": "record.pdf",
        "report_file_name": "report.pdf",
        "comparisons": [
            {
                "sequence": 1,
                "report_standard_clauses": ["4.2"],
                "record_aggregate_judgement": "符合",
                "report_judgement": "符合",
                "matched": True,
                "issues": [],
            }
        ],
        "mismatches": [],
        "missing_mappings": [],
        "summary_counts": {
            "report_row_count": 1,
            "record_entry_count": 1,
            "matched_count": 1,
            "mismatch_count": 0,
            "missing_mapping_count": 0,
        },
    }


def test_record_report_service_happy_path_returns_pass_result_and_progress_events():
    _clear_judge_cache()
    builder = FakeRecordReportEvidenceBuilder(_happy_evidence())
    judge = FakeJudge()
    service = RecordReportCheckService(evidence_builder=builder, judge_client=judge)
    events: list[dict[str, Any]] = []
    extracted_record = {"file_name": "record.pdf", "pages": []}
    extracted_report = {"file_name": "report.pdf", "pages": []}

    result = service.check_extracted_pair(
        extracted_record,
        extracted_report,
        task_id="task-record-report",
        progress_callback=events.append,
    )

    assert builder.calls == [(extracted_record, extracted_report, "gb9706_1")]
    assert result.task_id == "task-record-report"
    assert result.file_name == "report.pdf"
    assert result.record_file_name == "record.pdf"
    assert result.report_file_name == "report.pdf"
    assert result.record_report_mode == "quick"
    assert result.record_report_standard == "gb9706_1"
    assert result.record_report_concurrency == 4
    assert result.overall_status == CheckStatus.PASS
    assert result.summary.total_checks == 1
    assert result.summary.pass_count == 1
    assert result.check_results[0].check_id == "RECORD-REPORT-GB9706-1-001"
    assert result.check_results[0].details["sequence"] == 1
    assert result.check_results[0].details["record_entry_count"] == 0
    assert result.check_results[0].details["codex_invoked"] is False
    assert result.check_results[0].details["record_report_mode"] == "quick"
    assert result.check_results[0].details["record_report_standard"] == "gb9706_1"
    assert result.check_results[0].details["record_report_concurrency"] == 4
    assert judge.packages == []
    assert [event["event"] for event in events] == ["start", "done"]
    assert events[1]["result"].status == CheckStatus.PASS
    assert events[1]["completed"] == 1


def test_record_report_service_full_codex_mode_calls_judge_even_for_pass():
    _clear_judge_cache()
    judge = FakeJudge()
    service = RecordReportCheckService(
        evidence_builder=FakeRecordReportEvidenceBuilder(_happy_evidence()),
        judge_client=judge,
    )

    result = service.check_extracted_pair(
        {"file_name": "record.pdf"},
        {"file_name": "report.pdf"},
        record_report_mode="full_codex",
        record_report_concurrency=12,
    )

    assert result.record_report_mode == "full_codex"
    assert result.record_report_concurrency == 8
    assert [package["check_id"] for package in judge.packages] == ["RECORD-REPORT-GB9706-1-001"]
    assert judge.packages[0]["required_details"]
    assert judge.packages[0]["evidence"]["deterministic_status"] == "pass"
    assert result.check_results[0].details["codex_invoked"] is True
    assert result.check_results[0].details["codex_cache_hit"] is False
    assert result.check_results[0].details["record_report_mode"] == "full_codex"
    assert result.check_results[0].details["record_report_concurrency"] == 8


def test_record_report_service_reuses_cached_judge_result_for_same_package():
    _clear_judge_cache()
    judge = FakeJudge()
    service = RecordReportCheckService(
        evidence_builder=FakeRecordReportEvidenceBuilder(_happy_evidence()),
        judge_client=judge,
    )

    first = service.check_extracted_pair(
        {"file_name": "record.pdf"},
        {"file_name": "report.pdf"},
        record_report_mode="full",
    )
    second = service.check_extracted_pair(
        {"file_name": "record.pdf"},
        {"file_name": "report.pdf"},
        record_report_mode="full",
    )

    assert len(judge.packages) == 1
    assert first.check_results[0].details["codex_cache_hit"] is False
    assert second.check_results[0].details["codex_cache_hit"] is True


def test_record_report_service_marks_mismatch_as_error():
    _clear_judge_cache()
    evidence = _happy_evidence()
    evidence["comparisons"][0]["matched"] = False
    evidence["comparisons"][0]["issue"] = "mismatch"
    evidence["comparisons"][0]["issues"] = ["mismatch"]
    evidence["comparisons"][0]["record_aggregate_judgement"] = "不符合"
    evidence["mismatches"] = [evidence["comparisons"][0]]
    evidence["summary_counts"]["mismatch_count"] = 1
    judge = FakeJudge()
    service = RecordReportCheckService(evidence_builder=FakeRecordReportEvidenceBuilder(evidence), judge_client=judge)

    result = service.check_extracted_pair({"file_name": "record.pdf"}, {"file_name": "report.pdf"})

    assert judge.packages[0]["evidence"]["deterministic_issues"] == ["mismatch"]
    assert result.overall_status == CheckStatus.ERROR
    assert result.summary.error_count == 1
    assert result.check_results[0].findings[0].severity == "error"


def test_record_report_service_marks_missing_mapping_as_warning():
    _clear_judge_cache()
    evidence = _happy_evidence()
    evidence["comparisons"][0]["matched"] = False
    evidence["comparisons"][0]["sequence"] = 118
    evidence["comparisons"][0]["issue"] = "record_evidence_missing"
    evidence["comparisons"][0]["issues"] = ["record_evidence_missing", "record_judgement_missing"]
    evidence["missing_mappings"] = [
        {
            "type": "report_row_mapping",
            "sequence": 118,
            "report_page": 79,
            "report_standard_clause": "17",
            "issues": ["record_evidence_missing", "record_judgement_missing"],
            "reason": "未找到与报告标准条款前缀匹配的原始记录条款。",
        }
    ]
    evidence["summary_counts"]["matched_count"] = 0
    evidence["summary_counts"]["missing_mapping_count"] = 1
    judge = FakeJudge()
    service = RecordReportCheckService(evidence_builder=FakeRecordReportEvidenceBuilder(evidence), judge_client=judge)

    result = service.check_extracted_pair({"file_name": "record.pdf"}, {"file_name": "report.pdf"})

    assert judge.packages[0]["evidence"]["deterministic_status"] == "warning"
    assert result.overall_status == CheckStatus.WARNING
    assert result.summary.warning_count == 1
    assert result.check_results[0].findings[0].severity == "warning"
    assert result.check_results[0].missing_evidence[0].label == "报告序号 118 原始记录映射"


def test_record_report_standard_is_normalized_and_passed_to_builder():
    _clear_judge_cache()
    evidence = _happy_evidence()
    evidence["record_report_standard"] = "gb9706_202"
    builder = FakeRecordReportEvidenceBuilder(evidence)
    service = RecordReportCheckService(evidence_builder=builder, judge_client=FakeJudge())

    result = service.check_extracted_pair(
        {"file_name": "record.pdf"},
        {"file_name": "report.pdf"},
        record_report_standard="GB 9706.202-2021",
    )

    assert builder.calls[0][2] == "gb9706_202"
    assert result.record_report_standard == "gb9706_202"
    assert result.check_results[0].details["record_report_standard"] == "gb9706_202"


def test_record_report_standard_defaults_to_gb9706_1_for_unknown_values():
    assert record_report_service.normalize_record_report_standard("") == "gb9706_1"
    assert record_report_service.normalize_record_report_standard("unknown") == "gb9706_1"
    assert record_report_service.normalize_record_report_standard("gb9706.202") == "gb9706_202"
