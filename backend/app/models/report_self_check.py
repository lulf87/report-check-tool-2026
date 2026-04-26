from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class CheckStatus(StrEnum):
    PASS = "pass"
    WARNING = "warning"
    ERROR = "error"


class Confidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class FindingSeverity(StrEnum):
    WARNING = "warning"
    ERROR = "error"


class Finding(BaseModel):
    severity: FindingSeverity
    title: str
    detail: str
    expected: str | None = None
    actual: str | None = None
    pages: list[int]
    related_fields: list[str]


class EvidenceItem(BaseModel):
    source: str
    page: int | None = None
    label: str | None = None
    value: Any = None


class MissingEvidence(BaseModel):
    label: str
    reason: str
    expected_source: str | None = None


class FieldComparison(BaseModel):
    field: str
    source_a_name: str
    source_a_value: str
    source_a_page: int | None = Field(default=None, gt=0)
    source_b_name: str
    source_b_value: str
    source_b_page: int | None = Field(default=None, gt=0)
    matched: bool
    judgement: str = Field(min_length=1)


class CheckResult(BaseModel):
    check_id: str
    check_name: str
    status: CheckStatus
    confidence: Confidence = Confidence.MEDIUM
    summary: str = ""
    details: dict[str, Any] = Field(default_factory=dict)
    findings: list[Finding] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    missing_evidence: list[MissingEvidence] = Field(default_factory=list)


class ReportMeta(BaseModel):
    report_number: str = ""
    sample_number: str = ""
    sample_name: str = ""
    client: str = ""


class SummaryCounts(BaseModel):
    total_checks: int = 0
    pass_count: int = 0
    warning_count: int = 0
    error_count: int = 0


class ReportSelfCheckResult(BaseModel):
    task_id: str
    file_name: str
    overall_status: CheckStatus = CheckStatus.PASS
    report_meta: ReportMeta = Field(default_factory=ReportMeta)
    summary: SummaryCounts = Field(default_factory=SummaryCounts)
    check_results: list[CheckResult] = Field(default_factory=list)

    def refresh_summary(self) -> None:
        pass_count = sum(1 for item in self.check_results if item.status == CheckStatus.PASS)
        warning_count = sum(1 for item in self.check_results if item.status == CheckStatus.WARNING)
        error_count = sum(1 for item in self.check_results if item.status == CheckStatus.ERROR)

        self.summary = SummaryCounts(
            total_checks=len(self.check_results),
            pass_count=pass_count,
            warning_count=warning_count,
            error_count=error_count,
        )
        if error_count:
            self.overall_status = CheckStatus.ERROR
        elif warning_count:
            self.overall_status = CheckStatus.WARNING
        else:
            self.overall_status = CheckStatus.PASS
