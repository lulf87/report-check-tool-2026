import re
from uuid import uuid4
from typing import Any, Callable

from app.models.report_self_check import CheckResult, CheckStatus, Confidence, Finding, FindingSeverity, ReportSelfCheckResult
from app.services.codex_judge_client import CodexJudgeClient
from app.services.report_evidence_builder import ReportEvidenceBuilder

ProgressCallback = Callable[[dict[str, Any]], None]


class ReportSelfCheckService:
    def __init__(
        self,
        evidence_builder: ReportEvidenceBuilder | None = None,
        judge_client: CodexJudgeClient | None = None,
    ):
        self.evidence_builder = evidence_builder or ReportEvidenceBuilder()
        self.judge_client = judge_client or CodexJudgeClient()

    def check_extracted_report(
        self,
        extracted_report: dict,
        task_id: str | None = None,
        progress_callback: ProgressCallback | None = None,
    ) -> ReportSelfCheckResult:
        packages = self.evidence_builder.build_all(extracted_report)
        check_results = []

        for index, package in enumerate(packages, start=1):
            if progress_callback is not None:
                progress_callback({"event": "start", "index": index, "total": len(packages), "package": package})

            check_result = self.judge_client.judge(package)
            _enrich_evidence_values(check_result, package)
            _apply_deterministic_findings(check_result, package)
            check_results.append(check_result)

            if progress_callback is not None:
                progress_callback(
                    {
                        "event": "done",
                        "index": index,
                        "total": len(packages),
                        "package": package,
                        "result": check_result,
                    }
                )

        result = ReportSelfCheckResult(
            task_id=task_id or str(uuid4()),
            file_name=str(extracted_report.get("file_name", "")),
            check_results=check_results,
        )
        result.refresh_summary()
        return result


def _enrich_evidence_values(check_result: CheckResult, package: dict[str, Any]) -> None:
    evidence = package.get("evidence", {})
    if not isinstance(evidence, dict):
        return

    pages = evidence.get("pages", [])
    pages_by_number = {
        int(page["page"]): str(page.get("text", ""))
        for page in pages
        if isinstance(page, dict) and isinstance(page.get("page"), int)
    }
    named_sources = {
        "cover_text": str(evidence.get("cover_text") or ""),
        "report_home_text": str(evidence.get("report_home_text") or ""),
        "sample_description_text": str(evidence.get("sample_description_text") or ""),
        "inspection_table_text": str(evidence.get("inspection_table_text") or ""),
        "photo_text": str(evidence.get("photo_text") or ""),
    }

    for item in check_result.evidence:
        if item.value not in (None, ""):
            continue

        source = item.source or ""
        page_number = item.page or _extract_page_number(source)
        if page_number and pages_by_number.get(page_number):
            item.page = page_number
            item.value = _excerpt(pages_by_number[page_number])
            continue

        for source_key, source_text in named_sources.items():
            if source_key in source and source_text:
                item.value = _excerpt(source_text)
                break


def _apply_deterministic_findings(check_result: CheckResult, package: dict[str, Any]) -> None:
    evidence = package.get("evidence", {})
    if not isinstance(evidence, dict):
        return

    findings: list[Finding] = []
    if check_result.check_id == "C14":
        findings.extend(_c14_deterministic_findings(evidence))
        if findings:
            check_result.details["deterministic_empty_field_rows"] = list(
                evidence.get("candidate_empty_field_rows", [])
            )

    if check_result.check_id == "C15":
        findings.extend(_c15_deterministic_findings(evidence))
        if findings:
            check_result.details["continuation_marker_findings"] = list(
                evidence.get("continuation_marker_candidates", [])
            )

    existing_titles = {finding.title for finding in check_result.findings}
    new_findings = [finding for finding in findings if finding.title not in existing_titles]
    if not new_findings:
        return

    check_result.findings.extend(new_findings)
    if check_result.status == CheckStatus.PASS:
        check_result.status = CheckStatus.WARNING
    check_result.confidence = Confidence.HIGH
    check_result.summary = _append_summary_note(check_result.summary, "后端确定性核对发现表格字段问题。")


def _c14_deterministic_findings(evidence: dict[str, Any]) -> list[Finding]:
    findings = []
    for candidate in evidence.get("candidate_empty_field_rows", []):
        if not isinstance(candidate, dict):
            continue
        reason = str(candidate.get("reason", ""))
        if "版式词坐标" not in reason:
            continue

        page = _positive_int(candidate.get("page"))
        row_no = str(candidate.get("row_no") or "")
        fields = [str(field) for field in candidate.get("suspected_fields", []) if field]
        field_text = "、".join(fields) or "结果值列"
        findings.append(
            Finding(
                severity=FindingSeverity.WARNING,
                title=f"序号{row_no}{field_text}为空",
                detail=reason,
                expected=f"{field_text}列应填写内容或“/”等空白标记",
                actual=str(candidate.get("nearby_text") or ""),
                pages=[page] if page else [],
                related_fields=[f"C14.{field}" for field in fields] or ["C14"],
            )
        )
    return findings


def _c15_deterministic_findings(evidence: dict[str, Any]) -> list[Finding]:
    findings = []
    for candidate in evidence.get("continuation_marker_candidates", []):
        if not isinstance(candidate, dict):
            continue

        issue = str(candidate.get("issue", ""))
        page = _positive_int(candidate.get("page"))
        sequence = str(candidate.get("sequence") or "")
        if issue == "missing_continuation_marker":
            title = f"序号{sequence}再次出现时缺少“续”"
        elif issue == "unexpected_continuation_marker":
            title = f"序号{sequence}首次出现时不应标“续”"
        else:
            title = f"序号{sequence}续表标记异常"
        findings.append(
            Finding(
                severity=FindingSeverity.WARNING,
                title=title,
                detail=str(candidate.get("reason") or ""),
                expected=str(candidate.get("expected") or ""),
                actual=str(candidate.get("actual") or ""),
                pages=[page] if page else [],
                related_fields=["C15.序号", "C15.续表标记"],
            )
        )
    return findings


def _positive_int(value: Any) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _append_summary_note(summary: str, note: str) -> str:
    summary = summary.strip()
    if not summary:
        return note
    if note in summary:
        return summary
    return f"{summary} {note}"


def _extract_page_number(source: str) -> int | None:
    match = re.search(r"(?:page|pages|第)\s*(\d+)", source, flags=re.IGNORECASE)
    if not match:
        return None
    return int(match.group(1))


def _excerpt(text: str, max_chars: int = 500) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) <= max_chars:
        return compact
    return f"{compact[:max_chars]}..."
