from typing import Any, Callable
from uuid import uuid4

from pydantic import Field

from app.models.report_self_check import CheckResult, ReportSelfCheckResult
from app.services.codex_judge_client import CodexJudgeClient

try:
    from app.services.ptr_report_evidence_builder import PtrReportEvidenceBuilder
except ModuleNotFoundError:

    class PtrReportEvidenceBuilder:  # type: ignore[no-redef]
        def build_all(self, extracted_ptr: dict[str, Any], extracted_report: dict[str, Any]) -> list[dict[str, Any]]:
            raise RuntimeError("PtrReportEvidenceBuilder is not available")


ProgressCallback = Callable[[dict[str, Any]], None]


class PtrReportCheckResult(ReportSelfCheckResult):
    ptr_file_name: str = ""
    report_file_name: str = ""
    homepage_scope: dict[str, Any] = Field(default_factory=dict)
    ptr_report_scope_summary: dict[str, Any] = Field(default_factory=dict)


class PtrReportCheckService:
    def __init__(
        self,
        evidence_builder: PtrReportEvidenceBuilder | None = None,
        judge_client: CodexJudgeClient | None = None,
    ):
        self.evidence_builder = evidence_builder or PtrReportEvidenceBuilder()
        self.judge_client = judge_client or CodexJudgeClient()

    def check_extracted_pair(
        self,
        extracted_ptr: dict[str, Any],
        extracted_report: dict[str, Any],
        task_id: str | None = None,
        progress_callback: ProgressCallback | None = None,
    ) -> PtrReportCheckResult:
        packages = self.evidence_builder.build_all(extracted_ptr, extracted_report)
        runtime_packages = _with_scope_coverage_package(packages)
        check_results = []

        for index, package in enumerate(runtime_packages, start=1):
            if progress_callback is not None:
                progress_callback({"event": "start", "index": index, "total": len(runtime_packages), "package": package})

            deterministic_result = package.get("deterministic_result")
            if isinstance(deterministic_result, dict):
                check_result = CheckResult.model_validate(deterministic_result)
            else:
                check_result = self.judge_client.judge(package)
            _merge_deterministic_details(check_result, package)
            check_results.append(check_result)

            if progress_callback is not None:
                progress_callback(
                    {
                        "event": "done",
                        "index": index,
                        "total": len(runtime_packages),
                        "package": package,
                        "result": check_result,
                    }
                )

        result = PtrReportCheckResult(
            task_id=task_id or str(uuid4()),
            file_name=str(extracted_report.get("file_name", "")),
            ptr_file_name=str(extracted_ptr.get("file_name", "")),
            report_file_name=str(extracted_report.get("file_name", "")),
            homepage_scope=_extract_homepage_scope(packages),
            ptr_report_scope_summary=_extract_scope_coverage(packages),
            check_results=check_results,
        )
        result.refresh_summary()
        return result


def _extract_homepage_scope(packages: list[dict[str, Any]]) -> dict[str, Any]:
    for package in packages:
        scope = package.get("homepage_scope")
        if isinstance(scope, dict):
            return scope
        evidence = package.get("evidence")
        if isinstance(evidence, dict) and isinstance(evidence.get("homepage_scope"), dict):
            return evidence["homepage_scope"]
    return {}


def _with_scope_coverage_package(packages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if any(package.get("check_id") == "PTR-SCOPE-COVERAGE" for package in packages):
        return packages
    scope_coverage = _extract_scope_coverage(packages)
    if not scope_coverage:
        return packages
    return [_build_scope_coverage_package(scope_coverage), *packages]


def _build_scope_coverage_package(scope_coverage: dict[str, Any]) -> dict[str, Any]:
    missing = list(scope_coverage.get("missing_declared_clause_prefixes", []))
    extra = list(scope_coverage.get("extra_report_clause_prefixes", []))
    if missing:
        status = "error"
        summary = f"报告实际标准条款缺少首页声明的 {len(missing)} 个条款：{'、'.join(map(str, missing))}。"
    elif extra:
        status = "warning"
        summary = f"报告实际标准条款覆盖首页声明范围，并另出现 {len(extra)} 个未声明条款，建议确认。"
    else:
        status = "pass"
        summary = "报告实际标准条款覆盖首页声明的检验项目范围，未发现缺漏。"

    findings = []
    if missing:
        findings.append(
            {
                "severity": "error",
                "title": "报告实际条款缺漏",
                "detail": f"报告首页声明包含 {'、'.join(map(str, missing))}，但报告检验项目表的标准条款中未检出这些条款。",
                "expected": "、".join(map(str, scope_coverage.get("declared_clause_prefixes", []))),
                "actual": "、".join(map(str, scope_coverage.get("actual_report_clause_prefixes", []))),
                "pages": [],
                "related_fields": ["检验项目", "标准条款", "标准要求"],
            }
        )

    return {
        "check_id": "PTR-SCOPE-COVERAGE",
        "check_name": "PTR 与报告检验项目范围覆盖总览",
        "evidence": {"scope_coverage": scope_coverage},
        "deterministic_result": {
            "check_id": "PTR-SCOPE-COVERAGE",
            "check_name": "PTR 与报告检验项目范围覆盖总览",
            "status": status,
            "confidence": "high",
            "summary": summary,
            "details": {"scope_coverage": scope_coverage},
            "findings": findings,
            "evidence": [
                {
                    "source": "report",
                    "page": None,
                    "label": "报告首页检验项目",
                    "value": scope_coverage.get("report_scope_text", ""),
                }
            ],
            "missing_evidence": [],
        },
    }


def _extract_scope_coverage(packages: list[dict[str, Any]]) -> dict[str, Any]:
    for package in packages:
        evidence = package.get("evidence")
        if isinstance(evidence, dict) and isinstance(evidence.get("scope_coverage"), dict):
            return evidence["scope_coverage"]
    return {}


def _merge_deterministic_details(check_result: CheckResult, package: dict[str, Any]) -> None:
    evidence = package.get("evidence")
    if not isinstance(evidence, dict):
        return
    for key in [
        "scope_coverage",
        "ptr_clause_prefix",
        "leaf_clause_reviews",
        "report_candidate_pages",
        "scope_decision",
    ]:
        if key in evidence and key not in check_result.details:
            check_result.details[key] = evidence[key]
