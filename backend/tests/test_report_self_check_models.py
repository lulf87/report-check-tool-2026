import json
from pathlib import Path

import jsonschema
import pytest
from pydantic import ValidationError

from app.models.report_self_check import (
    CheckResult,
    CheckStatus,
    Finding,
    FieldComparison,
    ReportSelfCheckResult,
    SummaryCounts,
)


def test_overall_status_is_error_when_any_check_errors():
    result = ReportSelfCheckResult(
        task_id="task-1",
        file_name="sample.pdf",
        check_results=[
            CheckResult(check_id="C00", check_name="文档结构完整性", status=CheckStatus.PASS),
            CheckResult(check_id="C02", check_name="首页基础字段一致性", status=CheckStatus.ERROR),
        ],
    )

    result.refresh_summary()

    assert result.overall_status == CheckStatus.ERROR
    assert result.summary == SummaryCounts(total_checks=2, pass_count=1, warning_count=0, error_count=1)


def test_field_comparison_keeps_concrete_values():
    comparison = FieldComparison(
        field="样品名称",
        source_a_name="封面",
        source_a_value="消化道脉冲电场消融仪",
        source_a_page=1,
        source_b_name="检验报告首页",
        source_b_value="消化道脉冲电场消融仪",
        source_b_page=3,
        matched=True,
        judgement="一致",
    )

    assert comparison.field == "样品名称"
    assert comparison.source_a_value == comparison.source_b_value


def test_finding_rejects_pass_severity():
    with pytest.raises(ValidationError):
        Finding(severity="pass", title="标题", detail="明细", pages=[], related_fields=[])


def test_field_comparison_rejects_empty_judgement():
    with pytest.raises(ValidationError):
        FieldComparison(
            field="样品名称",
            source_a_name="封面",
            source_a_value="消化道脉冲电场消融仪",
            source_b_name="检验报告首页",
            source_b_value="消化道脉冲电场消融仪",
            matched=True,
            judgement="",
        )


def test_field_comparison_rejects_non_positive_pages():
    with pytest.raises(ValidationError):
        FieldComparison(
            field="样品名称",
            source_a_name="封面",
            source_a_value="消化道脉冲电场消融仪",
            source_a_page=0,
            source_b_name="检验报告首页",
            source_b_value="消化道脉冲电场消融仪",
            source_b_page=-1,
            matched=True,
            judgement="一致",
        )


def test_codex_check_result_schema_is_loadable():
    schema_path = Path("app/schemas/codex_check_result.schema.json")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    assert schema["required"] == [
        "check_id",
        "check_name",
        "status",
        "confidence",
        "summary",
        "details",
        "findings",
        "evidence",
        "missing_evidence",
    ]


def test_codex_check_result_validates_against_schema_and_model():
    schema_path = Path("app/schemas/codex_check_result.schema.json")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    payload = {
        "check_id": "C01",
        "check_name": "首页基础字段一致性",
        "status": "warning",
        "confidence": "medium",
        "summary": "部分字段一致。",
        "details": {"matched": 1},
        "findings": [
            {
                "severity": "warning",
                "title": "样品名称存在差异",
                "detail": "首页样品名称与封面不一致。",
                "expected": "消化道脉冲电场消融仪",
                "actual": "消化道脉冲电场消融仪（样品）",
                "pages": [1, 3],
                "related_fields": ["样品名称"],
            }
        ],
        "evidence": [
            {
                "source": "封面",
                "page": 1,
                "label": "样品名称",
                "value": "消化道脉冲电场消融仪",
            }
        ],
        "missing_evidence": [
            {
                "label": "检验报告首页",
                "reason": "首页字段摘录缺失。",
                "expected_source": "检验报告首页",
            }
        ],
    }

    jsonschema.validate(payload, schema)

    result = CheckResult.model_validate(payload)
    assert result.check_id == payload["check_id"]
    assert result.findings[0].pages == [1, 3]


def test_codex_check_result_rejects_empty_evidence_item_in_schema():
    schema_path = Path("app/schemas/codex_check_result.schema.json")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    payload = {
        "check_id": "C01",
        "check_name": "首页基础字段一致性",
        "status": "warning",
        "confidence": "medium",
        "summary": "部分字段一致。",
        "details": {},
        "findings": [],
        "evidence": [{}],
        "missing_evidence": [],
    }

    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(payload, schema)


def test_codex_check_result_accepts_nullable_evidence_fields():
    schema_path = Path("app/schemas/codex_check_result.schema.json")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    payload = {
        "check_id": "C01",
        "check_name": "首页基础字段一致性",
        "status": "warning",
        "confidence": "medium",
        "summary": "部分字段一致。",
        "details": {},
        "findings": [],
        "evidence": [
            {
                "source": "unit-test",
                "page": None,
                "label": None,
                "value": None,
            }
        ],
        "missing_evidence": [],
    }

    jsonschema.validate(payload, schema)
    result = CheckResult.model_validate(payload)
    assert result.evidence[0].source == "unit-test"
