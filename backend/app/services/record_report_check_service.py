import hashlib
import json
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from typing import Any, Callable
from uuid import uuid4

from pydantic import Field

from app.models.report_self_check import (
    CheckResult,
    CheckStatus,
    Confidence,
    EvidenceItem,
    Finding,
    FindingSeverity,
    MissingEvidence,
    ReportSelfCheckResult,
)
from app.services.codex_judge_client import CodexJudgeClient
from app.services.record_report_evidence_builder import (
    RECORD_REPORT_CHECK_ID,
    RECORD_REPORT_CHECK_NAME,
    RecordReportEvidenceBuilder,
)


ProgressCallback = Callable[[dict[str, Any]], None]
RECORD_REPORT_MODE_QUICK = "quick"
RECORD_REPORT_MODE_FULL = "full_codex"
DEFAULT_RECORD_REPORT_CONCURRENCY = 4
MAX_RECORD_REPORT_CONCURRENCY = 8
JUDGE_CACHE_MAX_SIZE = 512
_JUDGE_CACHE_LOCK = Lock()
_JUDGE_CACHE: OrderedDict[str, dict[str, Any]] = OrderedDict()


class RecordReportCheckResult(ReportSelfCheckResult):
    record_file_name: str = ""
    report_file_name: str = ""
    record_report_mode: str = RECORD_REPORT_MODE_QUICK
    record_report_concurrency: int = DEFAULT_RECORD_REPORT_CONCURRENCY
    record_report_summary: dict[str, Any] = Field(default_factory=dict)


class RecordReportCheckService:
    def __init__(
        self,
        evidence_builder: RecordReportEvidenceBuilder | None = None,
        judge_client: CodexJudgeClient | None = None,
    ):
        self.evidence_builder = evidence_builder or RecordReportEvidenceBuilder()
        self.judge_client = judge_client or CodexJudgeClient()

    def check_extracted_pair(
        self,
        extracted_record: dict[str, Any],
        extracted_report: dict[str, Any],
        task_id: str | None = None,
        progress_callback: ProgressCallback | None = None,
        record_report_mode: str = RECORD_REPORT_MODE_QUICK,
        record_report_concurrency: int = DEFAULT_RECORD_REPORT_CONCURRENCY,
    ) -> RecordReportCheckResult:
        packages = self.evidence_builder.build_all(extracted_record, extracted_report)
        runtime_packages = _comparison_runtime_packages(packages)
        mode, concurrency = normalize_record_report_options(record_report_mode, record_report_concurrency)
        check_results = _run_runtime_packages(
            runtime_packages,
            self.judge_client,
            mode,
            concurrency,
            progress_callback,
        )

        result = RecordReportCheckResult(
            task_id=task_id or str(uuid4()),
            file_name=str(extracted_report.get("file_name", "")),
            record_file_name=str(extracted_record.get("file_name", "")),
            report_file_name=str(extracted_report.get("file_name", "")),
            record_report_mode=mode,
            record_report_concurrency=concurrency,
            record_report_summary=_extract_summary(packages),
            check_results=check_results,
        )
        result.refresh_summary()
        return result


def _run_runtime_packages(
    runtime_packages: list[dict[str, Any]],
    judge_client: CodexJudgeClient,
    mode: str,
    concurrency: int,
    progress_callback: ProgressCallback | None,
) -> list[CheckResult]:
    total = len(runtime_packages)
    results: list[CheckResult | None] = [None] * total
    codex_jobs: list[tuple[int, dict[str, Any]]] = []
    completed_count = 0

    for index, package in enumerate(runtime_packages, start=1):
        if _should_use_deterministic_result(package, mode):
            if progress_callback is not None:
                progress_callback({"event": "start", "index": index, "total": total, "package": package, "mode": mode})
            check_result = _build_deterministic_check_result(package, mode)
            check_result.details["record_report_concurrency"] = concurrency
            results[index - 1] = check_result
            completed_count += 1
            if progress_callback is not None:
                progress_callback(
                    {
                        "event": "done",
                        "index": index,
                        "completed": completed_count,
                        "total": total,
                        "package": package,
                        "result": check_result,
                        "mode": mode,
                        "cached": False,
                    }
                )
            continue
        codex_jobs.append((index, package))

    if codex_jobs:
        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            futures = {}
            for index, package in codex_jobs:
                if progress_callback is not None:
                    progress_callback({"event": "start", "index": index, "total": total, "package": package, "mode": mode})
                future = executor.submit(_judge_package_with_cache, judge_client, package)
                futures[future] = (index, package)

            for future in as_completed(futures):
                index, package = futures[future]
                check_result, cached = future.result()
                _merge_comparison_details(check_result, package)
                check_result.details["record_report_mode"] = mode
                check_result.details["record_report_concurrency"] = concurrency
                check_result.details["codex_invoked"] = True
                check_result.details["codex_cache_hit"] = cached
                results[index - 1] = check_result
                completed_count += 1
                if progress_callback is not None:
                    progress_callback(
                        {
                            "event": "done",
                            "index": index,
                            "completed": completed_count,
                            "total": total,
                            "package": package,
                            "result": check_result,
                            "mode": mode,
                            "cached": cached,
                        }
                    )

    return [result for result in results if result is not None]


def _should_use_deterministic_result(package: dict[str, Any], mode: str) -> bool:
    if mode != RECORD_REPORT_MODE_QUICK:
        return False
    evidence = package.get("evidence")
    return isinstance(evidence, dict) and evidence.get("deterministic_status") == "pass"


def _judge_package_with_cache(judge_client: CodexJudgeClient, package: dict[str, Any]) -> tuple[CheckResult, bool]:
    cache_key = _package_cache_key(package)
    with _JUDGE_CACHE_LOCK:
        cached_payload = _JUDGE_CACHE.get(cache_key)
        if cached_payload is not None:
            _JUDGE_CACHE.move_to_end(cache_key)
    if cached_payload is not None:
        return CheckResult.model_validate(cached_payload), True

    check_result = judge_client.judge(package)
    with _JUDGE_CACHE_LOCK:
        _JUDGE_CACHE[cache_key] = check_result.model_dump(mode="json")
        _JUDGE_CACHE.move_to_end(cache_key)
        while len(_JUDGE_CACHE) > JUDGE_CACHE_MAX_SIZE:
            _JUDGE_CACHE.popitem(last=False)
    return check_result, False


def _package_cache_key(package: dict[str, Any]) -> str:
    payload = json.dumps(package, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _normalize_record_report_mode(value: str) -> str:
    normalized = str(value or "").strip().lower().replace("-", "_")
    if normalized in {"full", "full_codex", "codex", "complete"}:
        return RECORD_REPORT_MODE_FULL
    return RECORD_REPORT_MODE_QUICK


def _normalize_concurrency(value: Any) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = DEFAULT_RECORD_REPORT_CONCURRENCY
    return max(1, min(MAX_RECORD_REPORT_CONCURRENCY, number))


def normalize_record_report_options(mode: str, concurrency: Any) -> tuple[str, int]:
    return _normalize_record_report_mode(mode), _normalize_concurrency(concurrency)


def _build_deterministic_check_result(package: dict[str, Any], mode: str) -> CheckResult:
    evidence = package.get("evidence") if isinstance(package.get("evidence"), dict) else {}
    status = CheckStatus(str(evidence.get("deterministic_status") or CheckStatus.PASS))
    issues = [str(issue) for issue in evidence.get("deterministic_issues", []) if issue]
    comparison = {
        "sequence": evidence.get("sequence"),
        "report_page": evidence.get("report_page"),
        "report_standard_clause": evidence.get("report_standard_clause", ""),
        "report_standard_clauses": list(evidence.get("report_standard_clauses", [])),
        "report_standard_requirement": evidence.get("report_standard_requirement", ""),
        "report_result": evidence.get("report_result", ""),
        "report_conclusion": evidence.get("report_conclusion", ""),
        "report_judgement": evidence.get("report_judgement", ""),
        "record_aggregate_judgement": evidence.get("record_aggregate_judgement", ""),
        "record_entry_count": evidence.get("record_entry_count", 0),
        "record_entries": list(evidence.get("record_entries", [])),
        "issues": issues,
    }
    details = {
        **comparison,
        "deterministic_issues": issues,
        "deterministic_status": evidence.get("deterministic_status", ""),
        "deterministic_summary": evidence.get("deterministic_summary", ""),
        "judgement_consistency": evidence.get("judgement_consistency"),
        "record_report_mode": mode,
        "codex_invoked": False,
        "codex_cache_hit": False,
    }
    return CheckResult(
        check_id=str(package.get("check_id") or RECORD_REPORT_CHECK_ID),
        check_name=str(package.get("check_name") or RECORD_REPORT_CHECK_NAME),
        status=status,
        confidence=Confidence.HIGH,
        summary=str(evidence.get("deterministic_summary") or ""),
        details=details,
        findings=_build_comparison_findings(comparison, issues),
        evidence=_build_comparison_evidence(comparison),
        missing_evidence=_build_comparison_missing_evidence(comparison, issues),
    )


RECORD_REPORT_REQUIRED_DETAILS = [
    "sequence",
    "report_standard_clause",
    "report_page",
    "report_judgement",
    "record_aggregate_judgement",
    "record_entries",
    "record_entry_count",
    "deterministic_issues",
    "judgement_consistency",
]

RECORD_REPORT_CHECK_RULES = [
    "本轮只判断一个 report 序号对应的 GB 9706.1-2020 判定是否与原始记录一致。",
    "必须优先使用 evidence.report_judgement、evidence.record_aggregate_judgement 和 evidence.record_entries。",
    "若 evidence.deterministic_issues 为空，且报告判定与原始记录聚合判定一致，应判定 pass。",
    "若 deterministic_issues 包含 mismatch，应判定 error，并说明报告判定与原始记录聚合判定的差异。",
    "若存在 record_evidence_missing、record_judgement_missing 或 report_judgement_missing，应判定 warning，不得编造缺失证据。",
    "原始记录小项用于支持聚合判定；应在 details.record_entries 中保留用于判定的小项摘要。",
    "不得把报告中没有的序号或原始记录中没有的条款补写为证据。",
]


def _comparison_runtime_packages(packages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    runtime_packages: list[dict[str, Any]] = []
    for package in packages:
        evidence = package.get("evidence") if isinstance(package.get("evidence"), dict) else {}
        comparisons = evidence.get("comparisons")
        if isinstance(comparisons, list) and comparisons:
            for comparison in comparisons:
                if isinstance(comparison, dict):
                    runtime_packages.append(_build_comparison_package(package, evidence, comparison))
            continue
        runtime_packages.append(package)
    return runtime_packages or [{"check_id": RECORD_REPORT_CHECK_ID, "check_name": RECORD_REPORT_CHECK_NAME, "evidence": {}}]


def _build_comparison_package(
    package: dict[str, Any],
    evidence: dict[str, Any],
    comparison: dict[str, Any],
) -> dict[str, Any]:
    sequence = _positive_int(comparison.get("sequence"))
    issues = [str(issue) for issue in comparison.get("issues", []) if issue]
    report_clause = str(comparison.get("report_standard_clause") or "")
    record_judgement = str(comparison.get("record_aggregate_judgement") or "")
    report_judgement = str(comparison.get("report_judgement") or "")
    record_entry_count = _positive_int(comparison.get("record_entry_count")) or 0
    if "mismatch" in issues:
        deterministic_status = "error"
        deterministic_summary = (
            f"序号 {sequence}：原始记录聚合判定为「{record_judgement}」，"
            f"报告判定为「{report_judgement}」。"
        )
    elif issues:
        deterministic_status = "warning"
        deterministic_summary = f"序号 {sequence}：未能完整映射原始记录证据或判定，需人工复核。"
    else:
        deterministic_status = "pass"
        deterministic_summary = f"序号 {sequence}：判定一致，匹配原始记录小项 {record_entry_count} 项。"

    return {
        "check_id": f"{RECORD_REPORT_CHECK_ID}-{sequence:03d}" if sequence is not None else str(package.get("check_id") or RECORD_REPORT_CHECK_ID),
        "check_name": f"序号 {sequence} / 条款 {report_clause} 原始记录核对" if sequence is not None else str(package.get("check_name") or RECORD_REPORT_CHECK_NAME),
        "required_details": list(RECORD_REPORT_REQUIRED_DETAILS),
        "check_rules": list(RECORD_REPORT_CHECK_RULES),
        "evidence": {
            "record_file_name": evidence.get("record_file_name", ""),
            "report_file_name": evidence.get("report_file_name", ""),
            "summary_counts": dict(evidence.get("summary_counts", {})),
            "sequence": sequence,
            "report_page": comparison.get("report_page"),
            "report_standard_clause": report_clause,
            "report_standard_clauses": list(comparison.get("report_standard_clauses", [])),
            "report_standard_requirement": comparison.get("report_standard_requirement", ""),
            "report_result": comparison.get("report_result", ""),
            "report_conclusion": comparison.get("report_conclusion", ""),
            "report_judgement": report_judgement,
            "record_aggregate_judgement": record_judgement,
            "record_entry_count": record_entry_count,
            "record_entries": list(comparison.get("record_entries", [])),
            "deterministic_issues": issues,
            "deterministic_status": deterministic_status,
            "deterministic_summary": deterministic_summary,
            "judgement_consistency": not issues,
        },
    }


def _merge_comparison_details(check_result: CheckResult, package: dict[str, Any]) -> None:
    evidence = package.get("evidence")
    if not isinstance(evidence, dict):
        return
    for key in [
        "sequence",
        "report_page",
        "report_standard_clause",
        "report_standard_clauses",
        "report_standard_requirement",
        "report_result",
        "report_conclusion",
        "report_judgement",
        "record_aggregate_judgement",
        "record_entry_count",
        "record_entries",
        "deterministic_issues",
        "deterministic_status",
        "deterministic_summary",
        "judgement_consistency",
    ]:
        if key in evidence and key not in check_result.details:
            check_result.details[key] = evidence[key]


def _build_aggregate_check_result(package: dict[str, Any]) -> CheckResult:
    evidence = package.get("evidence") if isinstance(package.get("evidence"), dict) else {}
    summary_counts = dict(evidence.get("summary_counts", {}))
    mismatches = list(evidence.get("mismatches", []))
    missing_mappings = list(evidence.get("missing_mappings", []))

    mismatch_count = int(summary_counts.get("mismatch_count") or len(mismatches))
    missing_mapping_count = int(summary_counts.get("missing_mapping_count") or len(missing_mappings))
    if mismatch_count:
        status = CheckStatus.ERROR
        summary = f"发现 {mismatch_count} 个报告序号与原始记录聚合判定不一致。"
    elif missing_mapping_count:
        status = CheckStatus.WARNING
        summary = f"未发现真实判定不一致，但有 {missing_mapping_count} 项缺失或无法映射证据。"
    else:
        status = CheckStatus.PASS
        summary = "报告序号 1-118 与原始记录聚合判定一致。"

    return CheckResult(
        check_id=str(package.get("check_id") or RECORD_REPORT_CHECK_ID),
        check_name=str(package.get("check_name") or RECORD_REPORT_CHECK_NAME),
        status=status,
        confidence=Confidence.HIGH if summary_counts.get("report_row_count") and summary_counts.get("record_entry_count") else Confidence.MEDIUM,
        summary=summary,
        details={
            "comparisons": list(evidence.get("comparisons", [])),
            "mismatches": mismatches,
            "missing_mappings": missing_mappings,
            "summary_counts": summary_counts,
        },
        findings=_build_findings(mismatches, missing_mappings),
        evidence=[
            EvidenceItem(source="record", label="原始记录文件", value=evidence.get("record_file_name", "")),
            EvidenceItem(source="report", label="报告文件", value=evidence.get("report_file_name", "")),
        ],
        missing_evidence=_build_missing_evidence(missing_mappings),
    )


def _build_comparison_check_result(package: dict[str, Any], comparison: dict[str, Any]) -> CheckResult:
    issues = [str(issue) for issue in comparison.get("issues", []) if issue]
    sequence = _positive_int(comparison.get("sequence"))
    report_clause = str(comparison.get("report_standard_clause") or "")
    record_judgement = str(comparison.get("record_aggregate_judgement") or "")
    report_judgement = str(comparison.get("report_judgement") or "")
    record_entry_count = _positive_int(comparison.get("record_entry_count")) or 0

    if "mismatch" in issues:
        status = CheckStatus.ERROR
        summary = (
            f"序号 {sequence}：原始记录聚合判定为「{record_judgement}」，"
            f"报告判定为「{report_judgement}」。"
        )
    elif issues:
        status = CheckStatus.WARNING
        summary = f"序号 {sequence}：未能完整映射原始记录证据或判定，需人工复核。"
    else:
        status = CheckStatus.PASS
        summary = f"序号 {sequence}：报告判定与原始记录聚合判定一致，匹配原始记录小项 {record_entry_count} 项。"

    return CheckResult(
        check_id=f"{RECORD_REPORT_CHECK_ID}-{sequence:03d}" if sequence is not None else RECORD_REPORT_CHECK_ID,
        check_name=f"序号 {sequence} / 条款 {report_clause} 原始记录核对" if sequence is not None else RECORD_REPORT_CHECK_NAME,
        status=status,
        confidence=Confidence.HIGH,
        summary=summary,
        details={
            "sequence": sequence,
            "report_page": comparison.get("report_page"),
            "report_standard_clause": report_clause,
            "report_standard_clauses": list(comparison.get("report_standard_clauses", [])),
            "report_standard_requirement": comparison.get("report_standard_requirement", ""),
            "report_result": comparison.get("report_result", ""),
            "report_conclusion": comparison.get("report_conclusion", ""),
            "report_judgement": report_judgement,
            "record_aggregate_judgement": record_judgement,
            "record_entry_count": record_entry_count,
            "record_entries": list(comparison.get("record_entries", [])),
            "issues": issues,
        },
        findings=_build_comparison_findings(comparison, issues),
        evidence=_build_comparison_evidence(comparison),
        missing_evidence=_build_comparison_missing_evidence(comparison, issues),
    )


def _build_comparison_findings(comparison: dict[str, Any], issues: list[str]) -> list[Finding]:
    if not issues:
        return []

    sequence = comparison.get("sequence")
    report_clause = str(comparison.get("report_standard_clause") or "")
    report_pages = _dedupe_pages([comparison.get("report_page")])
    record_judgement = str(comparison.get("record_aggregate_judgement") or "")
    report_judgement = str(comparison.get("report_judgement") or "")

    if "mismatch" in issues:
        return [
            Finding(
                severity=FindingSeverity.ERROR,
                title="原始记录与报告判定不一致",
                detail=f"报告序号 {sequence}（条款 {report_clause}）存在真实判定不一致。",
                expected=record_judgement,
                actual=report_judgement,
                pages=report_pages,
                related_fields=["原始记录符合性", "报告单项结论"],
            )
        ]

    return [
        Finding(
            severity=FindingSeverity.WARNING,
            title="原始记录证据缺失或无法映射",
            detail=f"报告序号 {sequence}（条款 {report_clause}）未能完整找到原始记录证据。",
            expected="能映射到原始记录条款并识别双方判定",
            actual=_missing_mapping_reason(issues),
            pages=report_pages,
            related_fields=["标准条款", "原始记录条款", "单项结论"],
        )
    ]


def _build_comparison_evidence(comparison: dict[str, Any]) -> list[EvidenceItem]:
    return [
        EvidenceItem(
            source="report",
            page=_positive_int(comparison.get("report_page")),
            label="报告序号/条款/判定",
            value={
                "sequence": comparison.get("sequence"),
                "standard_clause": comparison.get("report_standard_clause", ""),
                "judgement": comparison.get("report_judgement", ""),
            },
        ),
        EvidenceItem(
            source="record",
            label="匹配到的原始记录小项",
            value=list(comparison.get("record_entries", [])),
        ),
    ]


def _build_comparison_missing_evidence(comparison: dict[str, Any], issues: list[str]) -> list[MissingEvidence]:
    if not issues or "mismatch" in issues:
        return []
    return [
        MissingEvidence(
            label=f"报告序号 {comparison.get('sequence')} 原始记录映射",
            reason=_missing_mapping_reason(issues),
            expected_source="record",
        )
    ]


def _build_findings(mismatches: list[dict[str, Any]], missing_mappings: list[dict[str, Any]]) -> list[Finding]:
    findings: list[Finding] = []
    if mismatches:
        pages = _dedupe_pages(item.get("report_page") for item in mismatches)
        sample = mismatches[0]
        findings.append(
            Finding(
                severity=FindingSeverity.ERROR,
                title="原始记录与报告判定不一致",
                detail=f"发现 {len(mismatches)} 个报告序号存在真实判定不一致，首个为序号 {sample.get('sequence')}。",
                expected=str(sample.get("record_aggregate_judgement", "")),
                actual=str(sample.get("report_judgement", "")),
                pages=pages,
                related_fields=["原始记录符合性", "报告单项结论"],
            )
        )
    if missing_mappings:
        pages = _dedupe_pages(item.get("report_page") for item in missing_mappings)
        findings.append(
            Finding(
                severity=FindingSeverity.WARNING,
                title="存在缺失或无法映射证据",
                detail=f"发现 {len(missing_mappings)} 项报告或原始记录证据缺失/无法映射，需人工复核。",
                expected="报告序号应能映射到原始记录条款并识别双方判定",
                actual="部分条款或判定缺失",
                pages=pages,
                related_fields=["标准条款", "原始记录条款", "单项结论"],
            )
        )
    return findings


def _build_missing_evidence(missing_mappings: list[dict[str, Any]]) -> list[MissingEvidence]:
    items = []
    for mapping in missing_mappings[:50]:
        if mapping.get("type") == "record_entry_mapping":
            label = f"原始记录第 {mapping.get('record_sequence')} 行映射"
            expected_source = "report"
        elif mapping.get("type") == "report_table_missing":
            label = "报告序号 1-118 表格"
            expected_source = "report"
        elif mapping.get("type") == "record_table_missing":
            label = "原始记录主检查表"
            expected_source = "record"
        else:
            label = f"报告序号 {mapping.get('sequence')} 原始记录映射"
            expected_source = "record"
        items.append(
            MissingEvidence(
                label=label,
                reason=str(mapping.get("reason") or "缺失或无法映射"),
                expected_source=expected_source,
            )
        )
    return items


def _missing_mapping_reason(issues: list[str]) -> str:
    reason_map = {
        "report_clause_missing": "报告行未能抽取到标准条款号。",
        "record_evidence_missing": "未找到与报告标准条款前缀匹配的原始记录条款。",
        "record_judgement_missing": "原始记录匹配条款未能识别有效勾选判定。",
        "report_judgement_missing": "报告行未能识别有效单项结论/检验结果判定。",
    }
    return " ".join(reason_map.get(issue, issue) for issue in issues)


def _extract_summary(packages: list[dict[str, Any]]) -> dict[str, Any]:
    for package in packages:
        evidence = package.get("evidence")
        if isinstance(evidence, dict) and isinstance(evidence.get("summary_counts"), dict):
            return dict(evidence["summary_counts"])
    return {}


def _dedupe_pages(values: Any) -> list[int]:
    pages: list[int] = []
    for value in values:
        try:
            page = int(value)
        except (TypeError, ValueError):
            continue
        if page > 0 and page not in pages:
            pages.append(page)
    return pages


def _positive_int(value: Any) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None
