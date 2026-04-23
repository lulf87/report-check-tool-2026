# Report Self-Check Codex Judge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a report-internal self-check module that prepares evidence from one report PDF and uses Codex as the judgement layer for fourteen approved check items.

**Architecture:** The backend extracts PDF text, rendered pages, tables, captions, labels, and candidate fields into typed evidence packages. A Codex judge adapter sends one evidence package per check to `codex exec` with a JSON schema and validates the returned judgement. The frontend renders the top-level summary plus each check's `details`, `findings`, and evidence.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, PyMuPDF, pdfplumber, optional PaddleOCR, Codex CLI, React 19, TypeScript, Vite, pytest.

---

## Reference Documents

- Requirements: `docs/superpowers/specs/2026-04-23-report-self-check-codex-judge-spec.md`
- Sample reports: `素材/report/1539`, `素材/report/2795`, `素材/report/3940`, `素材/report/5332`, `素材/report/5780`, `素材/report/5782`

## File Structure

Create this structure in the current repository:

```text
backend/
  app/
    main.py
    config.py
    models/
      report_self_check.py
    services/
      pdf_document_loader.py
      report_evidence_extractor.py
      report_evidence_builder.py
      codex_judge_client.py
      report_self_check_service.py
    prompts/
      report_self_check_prompts.py
    schemas/
      codex_check_result.schema.json
    routers/
      report_self_check.py
  tests/
    fixtures/
      minimal_report_pages.json
      codex_c02_pass.json
      codex_c12_error.json
    test_report_self_check_models.py
    test_report_evidence_builder.py
    test_codex_judge_client.py
    test_report_self_check_service.py
frontend/
  src/
    api/
      reportSelfCheck.ts
    pages/
      ReportSelfCheckPage.tsx
    components/
      report-self-check/
        CheckResultCard.tsx
        CheckDetailsTable.tsx
        FindingsList.tsx
        OverallSummary.tsx
    types/
      reportSelfCheck.ts
docs/
  superpowers/
    specs/
      2026-04-23-report-self-check-codex-judge-spec.md
    plans/
      2026-04-23-report-self-check-codex-judge.md
```

Responsibilities:
- `pdf_document_loader.py`: Load PDF pages, text, dimensions, and optional rendered image paths.
- `report_evidence_extractor.py`: Extract candidate sections, fields, tables, captions, dates, numbers, and terms without final business judgement.
- `report_evidence_builder.py`: Build one evidence package for each approved check.
- `codex_judge_client.py`: Call Codex through an adapter and validate JSON output.
- `report_self_check_service.py`: Orchestrate extraction, evidence building, judgement, and overall summary.
- `report_self_check.py` router: Expose upload and check API.
- Frontend components: Display overall summary, per-check status, details, findings, evidence, and missing evidence.

## Approved Checks

The implementation must return exactly these checks:

```python
APPROVED_CHECK_IDS = [
    "C00", "C01", "C02", "C03", "C04", "C06", "C07", "C08",
    "C12", "C13", "C14", "C15", "C16", "C17",
]
```

Do not implement C05, C09, C10, C11, or C18.

## Task 1: Backend Project Skeleton and Dependencies

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/app/__init__.py`
- Create: `backend/app/main.py`
- Create: `backend/app/config.py`
- Create: `backend/app/models/__init__.py`
- Create: `backend/app/services/__init__.py`
- Create: `backend/app/routers/__init__.py`
- Create: `backend/tests/conftest.py`

- [ ] **Step 1: Create backend package files**

Create empty `__init__.py` files in:

```text
backend/app/__init__.py
backend/app/models/__init__.py
backend/app/services/__init__.py
backend/app/routers/__init__.py
```

- [ ] **Step 2: Add Python project configuration**

Write `backend/pyproject.toml`:

```toml
[project]
name = "report-self-checker"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
  "fastapi>=0.115.0",
  "uvicorn>=0.30.0",
  "pydantic>=2.8.0",
  "pydantic-settings>=2.4.0",
  "python-multipart>=0.0.9",
  "pymupdf>=1.24.0",
  "pdfplumber>=0.11.0"
]

[project.optional-dependencies]
test = [
  "pytest>=8.2.0",
  "pytest-asyncio>=0.23.0"
]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
```

- [ ] **Step 3: Add runtime config**

Write `backend/app/config.py`:

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    codex_command: str = "codex"
    codex_model: str = ""
    codex_timeout_seconds: int = 300
    render_pages: bool = True
    ocr_enabled: bool = False


settings = Settings()
```

- [ ] **Step 4: Add FastAPI app**

Write `backend/app/main.py`:

```python
from fastapi import FastAPI

from app.routers.report_self_check import router as report_self_check_router


app = FastAPI(title="Report Self Check Codex Judge")
app.include_router(report_self_check_router, prefix="/api/report-self-check", tags=["report-self-check"])
```

- [ ] **Step 5: Add temporary router stub**

Write `backend/app/routers/report_self_check.py`:

```python
from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
```

- [ ] **Step 6: Add pytest config fixture**

Write `backend/tests/conftest.py`:

```python
import pathlib


ROOT = pathlib.Path(__file__).resolve().parents[1]
```

- [ ] **Step 7: Verify backend imports**

Run:

```bash
cd backend
python -m pytest -q
```

Expected: pytest starts successfully and reports no tests collected or zero failures.

- [ ] **Step 8: Commit**

```bash
git add backend/pyproject.toml backend/app backend/tests/conftest.py
git commit -m "chore: scaffold report self-check backend"
```

## Task 2: Define Result and Evidence Models

**Files:**
- Create: `backend/app/models/report_self_check.py`
- Test: `backend/tests/test_report_self_check_models.py`

- [ ] **Step 1: Write model tests**

Write `backend/tests/test_report_self_check_models.py`:

```python
from app.models.report_self_check import (
    CheckResult,
    CheckStatus,
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
```

- [ ] **Step 2: Run model tests to verify failure**

Run:

```bash
cd backend
python -m pytest tests/test_report_self_check_models.py -q
```

Expected: FAIL because `app.models.report_self_check` does not exist.

- [ ] **Step 3: Implement models**

Write `backend/app/models/report_self_check.py`:

```python
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


class Finding(BaseModel):
    severity: CheckStatus
    title: str
    detail: str
    expected: str | None = None
    actual: str | None = None
    pages: list[int] = Field(default_factory=list)
    related_fields: list[str] = Field(default_factory=list)


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
    source_a_page: int | None = None
    source_b_name: str
    source_b_value: str
    source_b_page: int | None = None
    matched: bool
    judgement: str = ""


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
```

- [ ] **Step 4: Run model tests**

Run:

```bash
cd backend
python -m pytest tests/test_report_self_check_models.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/report_self_check.py backend/tests/test_report_self_check_models.py
git commit -m "feat: define report self-check result models"
```

## Task 3: Add JSON Schema for Codex Check Results

**Files:**
- Create: `backend/app/schemas/codex_check_result.schema.json`
- Test: `backend/tests/test_report_self_check_models.py`

- [ ] **Step 1: Add schema file**

Write `backend/app/schemas/codex_check_result.schema.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["check_id", "check_name", "status", "confidence", "summary", "details", "findings", "evidence", "missing_evidence"],
  "additionalProperties": false,
  "properties": {
    "check_id": {"type": "string"},
    "check_name": {"type": "string"},
    "status": {"type": "string", "enum": ["pass", "warning", "error"]},
    "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
    "summary": {"type": "string"},
    "details": {"type": "object"},
    "findings": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["severity", "title", "detail", "pages", "related_fields"],
        "additionalProperties": true,
        "properties": {
          "severity": {"type": "string", "enum": ["warning", "error"]},
          "title": {"type": "string"},
          "detail": {"type": "string"},
          "expected": {"type": ["string", "null"]},
          "actual": {"type": ["string", "null"]},
          "pages": {"type": "array", "items": {"type": "integer"}},
          "related_fields": {"type": "array", "items": {"type": "string"}}
        }
      }
    },
    "evidence": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": true
      }
    },
    "missing_evidence": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["label", "reason"],
        "additionalProperties": true,
        "properties": {
          "label": {"type": "string"},
          "reason": {"type": "string"},
          "expected_source": {"type": ["string", "null"]}
        }
      }
    }
  }
}
```

- [ ] **Step 2: Add schema existence test**

Append to `backend/tests/test_report_self_check_models.py`:

```python
import json
from pathlib import Path


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
```

- [ ] **Step 3: Run tests**

Run:

```bash
cd backend
python -m pytest tests/test_report_self_check_models.py -q
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/app/schemas/codex_check_result.schema.json backend/tests/test_report_self_check_models.py
git commit -m "feat: add codex check result schema"
```

## Task 4: Build Evidence Package Models and Builders

**Files:**
- Modify: `backend/app/models/report_self_check.py`
- Create: `backend/app/services/report_evidence_builder.py`
- Test: `backend/tests/fixtures/minimal_report_pages.json`
- Test: `backend/tests/test_report_evidence_builder.py`

- [ ] **Step 1: Add fixture**

Write `backend/tests/fixtures/minimal_report_pages.json`:

```json
{
  "file_name": "minimal.pdf",
  "pages": [
    {"page": 1, "text": "检验报告\n报告编号：国医检（设）字 QW2025 第 1539 号\n委 托 方 美敦力（上海）管理有限公司\n样品名称 射频脉冲电场消融系统\n型号规格 AFR-00008\n检验类别 委托检验"},
    {"page": 2, "text": "注意事项\n一、报告无检测机构检验报告专用章或检验单位公章无效。"},
    {"page": 3, "text": "检验报告首页\n报告编号：国医检（设）字 QW2025 第 1539 号 共 108 页 第 1 页\n样品名称 射频脉冲电场消融系统 样品编号 QW2025-1539\n型号规格 AFR-00008\n委托方 美敦力（上海）管理有限公司\n检验类别 委托检验"},
    {"page": 4, "text": "样品描述\n序号 部件名称 组件号 批号/序列号 生产日期\n1 心脏脉冲电场消融仪（主机） ASM-00094 2521001CPO 2025/05/21"},
    {"page": 5, "text": "序号 检验项目 标准条款 标准要求 检验结果 单项结论 备注\n1 ME设备 4.1 应符合要求 符合要求 符合 /"},
    {"page": 6, "text": "照片页\n心脏脉冲电场消融仪（主机）照片\n心脏脉冲电场消融仪（主机）中文标签"}
  ]
}
```

- [ ] **Step 2: Write builder tests**

Write `backend/tests/test_report_evidence_builder.py`:

```python
import json
from pathlib import Path

from app.services.report_evidence_builder import APPROVED_CHECK_IDS, ReportEvidenceBuilder


def load_fixture() -> dict:
    return json.loads(Path("tests/fixtures/minimal_report_pages.json").read_text(encoding="utf-8"))


def test_builder_creates_exactly_approved_check_packages():
    evidence = ReportEvidenceBuilder().build_all(load_fixture())

    assert [item["check_id"] for item in evidence] == APPROVED_CHECK_IDS
    assert "C05" not in [item["check_id"] for item in evidence]
    assert "C18" not in [item["check_id"] for item in evidence]


def test_c02_package_contains_concrete_cover_and_home_fields():
    evidence = ReportEvidenceBuilder().build_all(load_fixture())
    c02 = next(item for item in evidence if item["check_id"] == "C02")

    assert c02["check_name"] == "首页基础字段一致性"
    assert "cover_text" in c02["evidence"]
    assert "report_home_text" in c02["evidence"]
    assert c02["required_details"] == ["field_comparisons"]
```

- [ ] **Step 3: Run builder tests to verify failure**

Run:

```bash
cd backend
python -m pytest tests/test_report_evidence_builder.py -q
```

Expected: FAIL because `report_evidence_builder.py` does not exist.

- [ ] **Step 4: Implement evidence builder**

Write `backend/app/services/report_evidence_builder.py`:

```python
from typing import Any


APPROVED_CHECK_IDS = [
    "C00", "C01", "C02", "C03", "C04", "C06", "C07", "C08",
    "C12", "C13", "C14", "C15", "C16", "C17",
]


CHECK_NAMES = {
    "C00": "文档结构完整性",
    "C01": "报告编号与样品编号一致性",
    "C02": "首页基础字段一致性",
    "C03": "首页扩展字段一致性",
    "C04": "时间逻辑一致性",
    "C06": "样品描述字段一致性",
    "C07": "照片覆盖性",
    "C08": "中文标签覆盖性",
    "C12": "检验结果与单项结论逻辑",
    "C13": "单项结论与总结论逻辑",
    "C14": "非空字段核对",
    "C15": "序号连续性与续表正确性",
    "C16": "页码连续性",
    "C17": "术语与格式一致性",
}


REQUIRED_DETAILS = {
    "C00": ["detected_sections", "missing_sections", "section_order_ok"],
    "C01": ["report_number", "sample_number", "tail_match"],
    "C02": ["field_comparisons"],
    "C03": ["field_comparisons", "see_sample_desc_consistent"],
    "C04": ["dates", "timeline_checks"],
    "C06": ["rows"],
    "C07": ["components"],
    "C08": ["components"],
    "C12": ["sequence_results"],
    "C13": ["overall_conclusion_text", "nonconforming_sequences", "overall_consistent"],
    "C14": ["rows", "empty_field_rows"],
    "C15": ["sequence_list", "missing_numbers", "duplicate_numbers", "continuation_marker_findings"],
    "C16": ["page_infos", "missing_pages", "duplicate_pages", "total_consistent", "final_page_match"],
    "C17": ["term_groups"],
}


class ReportEvidenceBuilder:
    def build_all(self, extracted_report: dict[str, Any]) -> list[dict[str, Any]]:
        return [self.build_one(check_id, extracted_report) for check_id in APPROVED_CHECK_IDS]

    def build_one(self, check_id: str, extracted_report: dict[str, Any]) -> dict[str, Any]:
        pages = extracted_report.get("pages", [])
        cover_text = self._page_text(pages, 1)
        report_home_text = self._first_text_containing(pages, "检验报告首页")
        sample_description_text = self._first_text_containing(pages, "样品描述")
        inspection_table_text = self._first_text_containing(pages, "检验项目")
        photo_text = self._first_text_containing(pages, "照片")

        evidence = {
            "file_name": extracted_report.get("file_name", ""),
            "pages": pages,
            "cover_text": cover_text,
            "report_home_text": report_home_text,
            "sample_description_text": sample_description_text,
            "inspection_table_text": inspection_table_text,
            "photo_text": photo_text,
        }

        return {
            "check_id": check_id,
            "check_name": CHECK_NAMES[check_id],
            "required_details": REQUIRED_DETAILS[check_id],
            "evidence": evidence,
        }

    def _page_text(self, pages: list[dict[str, Any]], page_number: int) -> str:
        for page in pages:
            if page.get("page") == page_number:
                return str(page.get("text", ""))
        return ""

    def _first_text_containing(self, pages: list[dict[str, Any]], marker: str) -> str:
        for page in pages:
            text = str(page.get("text", ""))
            if marker in text:
                return text
        return ""
```

- [ ] **Step 5: Run builder tests**

Run:

```bash
cd backend
python -m pytest tests/test_report_evidence_builder.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/report_evidence_builder.py backend/tests/fixtures/minimal_report_pages.json backend/tests/test_report_evidence_builder.py
git commit -m "feat: build evidence packages for approved checks"
```

## Task 5: Implement PDF Document Loader

**Files:**
- Create: `backend/app/services/pdf_document_loader.py`
- Test: `backend/tests/test_pdf_document_loader.py`

- [ ] **Step 1: Write loader test using sample report**

Write `backend/tests/test_pdf_document_loader.py`:

```python
from pathlib import Path

from app.services.pdf_document_loader import PDFDocumentLoader


def test_loader_reads_report_pages_from_sample_pdf():
    sample = Path("../素材/report/3940/3940.pdf")
    pages = PDFDocumentLoader().load(sample)

    assert len(pages["pages"]) >= 30
    assert "国医检" in pages["pages"][0]["text"]
    assert pages["pages"][0]["page"] == 1
```

- [ ] **Step 2: Run loader test to verify failure**

Run:

```bash
cd backend
python -m pytest tests/test_pdf_document_loader.py -q
```

Expected: FAIL because `PDFDocumentLoader` does not exist.

- [ ] **Step 3: Implement loader**

Write `backend/app/services/pdf_document_loader.py`:

```python
from pathlib import Path
from typing import Any

import fitz


class PDFDocumentLoader:
    def load(self, pdf_path: Path) -> dict[str, Any]:
        if not pdf_path.exists():
            raise FileNotFoundError(str(pdf_path))

        pages: list[dict[str, Any]] = []
        with fitz.open(pdf_path) as doc:
            for index, page in enumerate(doc, start=1):
                rect = page.rect
                pages.append(
                    {
                        "page": index,
                        "text": page.get_text("text"),
                        "width": rect.width,
                        "height": rect.height,
                    }
                )

        return {
            "file_name": pdf_path.name,
            "path": str(pdf_path),
            "page_count": len(pages),
            "pages": pages,
        }
```

- [ ] **Step 4: Run loader test**

Run:

```bash
cd backend
python -m pytest tests/test_pdf_document_loader.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/pdf_document_loader.py backend/tests/test_pdf_document_loader.py
git commit -m "feat: load report pdf pages"
```

## Task 6: Implement Codex Judge Client

**Files:**
- Create: `backend/app/services/codex_judge_client.py`
- Create: `backend/tests/fixtures/codex_c02_pass.json`
- Create: `backend/tests/fixtures/codex_c12_error.json`
- Test: `backend/tests/test_codex_judge_client.py`

- [ ] **Step 1: Add Codex response fixtures**

Write `backend/tests/fixtures/codex_c02_pass.json`:

```json
{
  "check_id": "C02",
  "check_name": "首页基础字段一致性",
  "status": "pass",
  "confidence": "high",
  "summary": "封面与报告首页字段一致。",
  "details": {
    "field_comparisons": [
      {
        "field": "样品名称",
        "source_a_name": "封面",
        "source_a_value": "射频脉冲电场消融系统",
        "source_a_page": 1,
        "source_b_name": "检验报告首页",
        "source_b_value": "射频脉冲电场消融系统",
        "source_b_page": 3,
        "matched": true,
        "judgement": "一致"
      }
    ]
  },
  "findings": [],
  "evidence": [],
  "missing_evidence": []
}
```

Write `backend/tests/fixtures/codex_c12_error.json`:

```json
{
  "check_id": "C12",
  "check_name": "检验结果与单项结论逻辑",
  "status": "error",
  "confidence": "high",
  "summary": "第 27 序号全部检验结果为 / 或 ——，但单项结论写为符合。",
  "details": {
    "sequence_results": [
      {
        "sequence_number": "27",
        "page": 38,
        "inspection_project": "某检验项目",
        "test_results": ["/", "——", "/"],
        "actual_conclusion": "符合",
        "expected_conclusion": "/",
        "matched": false
      }
    ]
  },
  "findings": [
    {
      "severity": "error",
      "title": "单项结论逻辑错误",
      "detail": "该序号全部检验结果为 / 或 ——，单项结论应为 /。",
      "expected": "/",
      "actual": "符合",
      "pages": [38],
      "related_fields": ["检验结果", "单项结论"]
    }
  ],
  "evidence": [],
  "missing_evidence": []
}
```

- [ ] **Step 2: Write client tests**

Write `backend/tests/test_codex_judge_client.py`:

```python
import json
from pathlib import Path

from app.models.report_self_check import CheckStatus
from app.services.codex_judge_client import CodexJudgeClient, StaticJudgeTransport


def test_client_parses_valid_codex_json():
    payload = Path("tests/fixtures/codex_c02_pass.json").read_text(encoding="utf-8")
    client = CodexJudgeClient(transport=StaticJudgeTransport(payload))

    result = client.judge({"check_id": "C02", "check_name": "首页基础字段一致性", "evidence": {}})

    assert result.check_id == "C02"
    assert result.status == CheckStatus.PASS
    assert result.details["field_comparisons"][0]["field"] == "样品名称"


def test_client_converts_invalid_json_to_warning():
    client = CodexJudgeClient(transport=StaticJudgeTransport("not json"))

    result = client.judge({"check_id": "C02", "check_name": "首页基础字段一致性", "evidence": {}})

    assert result.status == CheckStatus.WARNING
    assert result.missing_evidence[0].label == "codex_json"
```

- [ ] **Step 3: Run client tests to verify failure**

Run:

```bash
cd backend
python -m pytest tests/test_codex_judge_client.py -q
```

Expected: FAIL because `codex_judge_client.py` does not exist.

- [ ] **Step 4: Implement client**

Write `backend/app/services/codex_judge_client.py`:

```python
import json
import subprocess
from pathlib import Path
from typing import Protocol

from app.config import settings
from app.models.report_self_check import CheckResult, CheckStatus, Confidence, MissingEvidence


class JudgeTransport(Protocol):
    def send(self, prompt: str, schema_path: Path) -> str:
        raise NotImplementedError


class StaticJudgeTransport:
    def __init__(self, response: str):
        self.response = response

    def send(self, prompt: str, schema_path: Path) -> str:
        return self.response


class CodexCliTransport:
    def send(self, prompt: str, schema_path: Path) -> str:
        command = [
            settings.codex_command,
            "exec",
            "--sandbox",
            "read-only",
            "--ask-for-approval",
            "never",
            "--output-schema",
            str(schema_path),
            "-",
        ]
        if settings.codex_model:
            command.extend(["--model", settings.codex_model])

        completed = subprocess.run(
            command,
            input=prompt,
            text=True,
            capture_output=True,
            timeout=settings.codex_timeout_seconds,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr.strip() or completed.stdout.strip())
        return completed.stdout.strip()


class CodexJudgeClient:
    def __init__(self, transport: JudgeTransport | None = None):
        self.transport = transport or CodexCliTransport()
        self.schema_path = Path(__file__).resolve().parents[1] / "schemas" / "codex_check_result.schema.json"

    def judge(self, evidence_package: dict) -> CheckResult:
        prompt = self._build_prompt(evidence_package)
        try:
            raw = self.transport.send(prompt, self.schema_path)
            payload = json.loads(raw)
            return CheckResult.model_validate(payload)
        except Exception as exc:
            return CheckResult(
                check_id=str(evidence_package.get("check_id", "")),
                check_name=str(evidence_package.get("check_name", "")),
                status=CheckStatus.WARNING,
                confidence=Confidence.LOW,
                summary="Codex 判断结果无法解析，需人工复核。",
                missing_evidence=[
                    MissingEvidence(
                        label="codex_json",
                        reason=str(exc),
                        expected_source="Codex JSON output",
                    )
                ],
            )

    def _build_prompt(self, evidence_package: dict) -> str:
        return (
            "你是医疗器械检验报告内部核对的判断器。"
            "只能依据输入证据判断，不得编造证据。"
            "请只输出符合 JSON Schema 的 JSON，不要输出解释性正文。\\n\\n"
            f"核对证据包：\\n{json.dumps(evidence_package, ensure_ascii=False, indent=2)}"
        )
```

- [ ] **Step 5: Run client tests**

Run:

```bash
cd backend
python -m pytest tests/test_codex_judge_client.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/codex_judge_client.py backend/tests/fixtures/codex_c02_pass.json backend/tests/fixtures/codex_c12_error.json backend/tests/test_codex_judge_client.py
git commit -m "feat: add codex judge client"
```

## Task 7: Orchestrate Report Self-Check Service

**Files:**
- Create: `backend/app/services/report_self_check_service.py`
- Test: `backend/tests/test_report_self_check_service.py`

- [ ] **Step 1: Write service test**

Write `backend/tests/test_report_self_check_service.py`:

```python
import json
from pathlib import Path

from app.models.report_self_check import CheckStatus
from app.services.codex_judge_client import CodexJudgeClient, StaticJudgeTransport
from app.services.report_self_check_service import ReportSelfCheckService


def test_service_returns_fourteen_checks_with_summary():
    codex_payload = Path("tests/fixtures/codex_c02_pass.json").read_text(encoding="utf-8")
    service = ReportSelfCheckService(judge_client=CodexJudgeClient(transport=StaticJudgeTransport(codex_payload)))
    extracted = json.loads(Path("tests/fixtures/minimal_report_pages.json").read_text(encoding="utf-8"))

    result = service.check_extracted_report(extracted, task_id="task-1")

    assert result.summary.total_checks == 14
    assert result.overall_status == CheckStatus.PASS
    assert result.check_results[0].details["field_comparisons"][0]["field"] == "样品名称"
```

- [ ] **Step 2: Run service test to verify failure**

Run:

```bash
cd backend
python -m pytest tests/test_report_self_check_service.py -q
```

Expected: FAIL because service does not exist.

- [ ] **Step 3: Implement service**

Write `backend/app/services/report_self_check_service.py`:

```python
from uuid import uuid4

from app.models.report_self_check import ReportSelfCheckResult
from app.services.codex_judge_client import CodexJudgeClient
from app.services.report_evidence_builder import ReportEvidenceBuilder


class ReportSelfCheckService:
    def __init__(
        self,
        evidence_builder: ReportEvidenceBuilder | None = None,
        judge_client: CodexJudgeClient | None = None,
    ):
        self.evidence_builder = evidence_builder or ReportEvidenceBuilder()
        self.judge_client = judge_client or CodexJudgeClient()

    def check_extracted_report(self, extracted_report: dict, task_id: str | None = None) -> ReportSelfCheckResult:
        packages = self.evidence_builder.build_all(extracted_report)
        check_results = [self.judge_client.judge(package) for package in packages]
        result = ReportSelfCheckResult(
            task_id=task_id or str(uuid4()),
            file_name=str(extracted_report.get("file_name", "")),
            check_results=check_results,
        )
        result.refresh_summary()
        return result
```

- [ ] **Step 4: Run service test**

Run:

```bash
cd backend
python -m pytest tests/test_report_self_check_service.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/report_self_check_service.py backend/tests/test_report_self_check_service.py
git commit -m "feat: orchestrate codex report self-check"
```

## Task 8: Implement Upload API

**Files:**
- Modify: `backend/app/routers/report_self_check.py`
- Test: `backend/tests/test_report_self_check_api.py`

- [ ] **Step 1: Write API test**

Write `backend/tests/test_report_self_check_api.py`:

```python
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app


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
```

- [ ] **Step 2: Run API test to verify failure**

Run:

```bash
cd backend
python -m pytest tests/test_report_self_check_api.py -q
```

Expected: FAIL because `/check` endpoint does not exist.

- [ ] **Step 3: Implement upload endpoint**

Replace `backend/app/routers/report_self_check.py` with:

```python
from pathlib import Path
from tempfile import NamedTemporaryFile

from fastapi import APIRouter, HTTPException, UploadFile

from app.services.pdf_document_loader import PDFDocumentLoader
from app.services.report_self_check_service import ReportSelfCheckService

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/check")
async def check_report(file: UploadFile):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    with NamedTemporaryFile(suffix=".pdf", delete=True) as tmp:
        tmp.write(await file.read())
        tmp.flush()
        extracted = PDFDocumentLoader().load(Path(tmp.name))
        extracted["file_name"] = file.filename

    result = ReportSelfCheckService().check_extracted_report(extracted)
    return result.model_dump(mode="json")
```

- [ ] **Step 4: Run API tests**

Run:

```bash
cd backend
python -m pytest tests/test_report_self_check_api.py -q
```

Expected: PASS for health and non-PDF rejection. The test suite does not call live Codex.

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/report_self_check.py backend/tests/test_report_self_check_api.py
git commit -m "feat: expose report self-check api"
```

## Task 9: Frontend Project Skeleton

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/index.html`
- Create: `frontend/tsconfig.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/App.tsx`

- [ ] **Step 1: Add frontend package file**

Write `frontend/package.json`:

```json
{
  "name": "report-self-check-frontend",
  "version": "0.1.0",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "@vitejs/plugin-react": "^5.0.0",
    "vite": "^7.0.0",
    "typescript": "^5.8.0",
    "react": "^19.0.0",
    "react-dom": "^19.0.0"
  },
  "devDependencies": {
    "@types/react": "^19.0.0",
    "@types/react-dom": "^19.0.0"
  }
}
```

- [ ] **Step 2: Add HTML entry**

Write `frontend/index.html`:

```html
<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>报告自身核对</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 3: Add TypeScript config**

Write `frontend/tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "useDefineForClassFields": true,
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "allowJs": false,
    "skipLibCheck": true,
    "esModuleInterop": true,
    "allowSyntheticDefaultImports": true,
    "strict": true,
    "forceConsistentCasingInFileNames": true,
    "module": "ESNext",
    "moduleResolution": "Node",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx"
  },
  "include": ["src"],
  "references": []
}
```

- [ ] **Step 4: Add Vite config**

Write `frontend/vite.config.ts`:

```ts
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
});
```

- [ ] **Step 5: Add React entry files**

Write `frontend/src/main.tsx`:

```tsx
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';

createRoot(document.getElementById('root') as HTMLElement).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
```

Write `frontend/src/App.tsx`:

```tsx
export default function App() {
  return <main>报告自身核对</main>;
}
```

- [ ] **Step 6: Install and build**

Run:

```bash
cd frontend
npm install
npm run build
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add frontend
git commit -m "chore: scaffold report self-check frontend"
```

## Task 10: Frontend Types and API Client

**Files:**
- Create: `frontend/src/types/reportSelfCheck.ts`
- Create: `frontend/src/api/reportSelfCheck.ts`

- [ ] **Step 1: Add TypeScript result types**

Write `frontend/src/types/reportSelfCheck.ts`:

```ts
export type CheckStatus = 'pass' | 'warning' | 'error';
export type Confidence = 'high' | 'medium' | 'low';

export interface Finding {
  severity: 'warning' | 'error';
  title: string;
  detail: string;
  expected?: string | null;
  actual?: string | null;
  pages: number[];
  related_fields: string[];
}

export interface CheckResult {
  check_id: string;
  check_name: string;
  status: CheckStatus;
  confidence: Confidence;
  summary: string;
  details: Record<string, unknown>;
  findings: Finding[];
  evidence: Array<Record<string, unknown>>;
  missing_evidence: Array<Record<string, unknown>>;
}

export interface ReportSelfCheckResult {
  task_id: string;
  file_name: string;
  overall_status: CheckStatus;
  report_meta: {
    report_number: string;
    sample_number: string;
    sample_name: string;
    client: string;
  };
  summary: {
    total_checks: number;
    pass_count: number;
    warning_count: number;
    error_count: number;
  };
  check_results: CheckResult[];
}
```

- [ ] **Step 2: Add API client**

Write `frontend/src/api/reportSelfCheck.ts`:

```ts
import type { ReportSelfCheckResult } from '../types/reportSelfCheck';

export async function runReportSelfCheck(file: File): Promise<ReportSelfCheckResult> {
  const formData = new FormData();
  formData.append('file', file);

  const response = await fetch('/api/report-self-check/check', {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || '报告自身核对失败');
  }

  return response.json() as Promise<ReportSelfCheckResult>;
}
```

- [ ] **Step 3: Run frontend type check**

Run:

```bash
cd frontend
npm run build
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/reportSelfCheck.ts frontend/src/api/reportSelfCheck.ts
git commit -m "feat: add report self-check frontend types"
```

## Task 11: Frontend Result Components

**Files:**
- Create: `frontend/src/components/report-self-check/OverallSummary.tsx`
- Create: `frontend/src/components/report-self-check/FindingsList.tsx`
- Create: `frontend/src/components/report-self-check/CheckDetailsTable.tsx`
- Create: `frontend/src/components/report-self-check/CheckResultCard.tsx`

- [ ] **Step 1: Add overall summary component**

Write `frontend/src/components/report-self-check/OverallSummary.tsx`:

```tsx
import type { ReportSelfCheckResult } from '../../types/reportSelfCheck';

export function OverallSummary({ result }: { result: ReportSelfCheckResult }) {
  return (
    <section>
      <h2>报告自身核对结果</h2>
      <p>文件：{result.file_name}</p>
      <p>总体状态：{result.overall_status}</p>
      <p>
        共 {result.summary.total_checks} 项，通过 {result.summary.pass_count} 项，警告{' '}
        {result.summary.warning_count} 项，错误 {result.summary.error_count} 项
      </p>
    </section>
  );
}
```

- [ ] **Step 2: Add findings list component**

Write `frontend/src/components/report-self-check/FindingsList.tsx`:

```tsx
import type { Finding } from '../../types/reportSelfCheck';

export function FindingsList({ findings }: { findings: Finding[] }) {
  if (findings.length === 0) {
    return <p>未发现具体问题。</p>;
  }

  return (
    <ul>
      {findings.map((finding, index) => (
        <li key={`${finding.title}-${index}`}>
          <strong>{finding.title}</strong>
          <p>{finding.detail}</p>
          {finding.pages.length > 0 && <p>页码：{finding.pages.join('、')}</p>}
        </li>
      ))}
    </ul>
  );
}
```

- [ ] **Step 3: Add generic details renderer**

Write `frontend/src/components/report-self-check/CheckDetailsTable.tsx`:

```tsx
function renderValue(value: unknown): string {
  if (value === null || value === undefined) return '';
  if (typeof value === 'string') return value;
  return JSON.stringify(value, null, 2);
}

export function CheckDetailsTable({ details }: { details: Record<string, unknown> }) {
  return (
    <table>
      <thead>
        <tr>
          <th>明细项</th>
          <th>内容</th>
        </tr>
      </thead>
      <tbody>
        {Object.entries(details).map(([key, value]) => (
          <tr key={key}>
            <td>{key}</td>
            <td>
              <pre>{renderValue(value)}</pre>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
```

- [ ] **Step 4: Add check result card**

Write `frontend/src/components/report-self-check/CheckResultCard.tsx`:

```tsx
import type { CheckResult } from '../../types/reportSelfCheck';
import { CheckDetailsTable } from './CheckDetailsTable';
import { FindingsList } from './FindingsList';

export function CheckResultCard({ check }: { check: CheckResult }) {
  return (
    <article>
      <header>
        <h3>
          {check.check_id} {check.check_name}
        </h3>
        <p>状态：{check.status}；置信度：{check.confidence}</p>
        <p>{check.summary}</p>
      </header>
      <CheckDetailsTable details={check.details} />
      <FindingsList findings={check.findings} />
    </article>
  );
}
```

- [ ] **Step 5: Build frontend**

Run:

```bash
cd frontend
npm run build
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/report-self-check
git commit -m "feat: render report self-check results"
```

## Task 12: Frontend Page

**Files:**
- Create: `frontend/src/pages/ReportSelfCheckPage.tsx`

- [ ] **Step 1: Add page**

Write `frontend/src/pages/ReportSelfCheckPage.tsx`:

```tsx
import { useState } from 'react';
import { runReportSelfCheck } from '../api/reportSelfCheck';
import { CheckResultCard } from '../components/report-self-check/CheckResultCard';
import { OverallSummary } from '../components/report-self-check/OverallSummary';
import type { ReportSelfCheckResult } from '../types/reportSelfCheck';

export function ReportSelfCheckPage() {
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<ReportSelfCheckResult | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  async function handleRun() {
    if (!file) return;
    setLoading(true);
    setError('');
    try {
      setResult(await runReportSelfCheck(file));
    } catch (err) {
      setError(err instanceof Error ? err.message : '核对失败');
    } finally {
      setLoading(false);
    }
  }

  return (
    <main>
      <h1>报告自身核对</h1>
      <input
        type="file"
        accept="application/pdf,.pdf"
        onChange={(event) => setFile(event.target.files?.[0] ?? null)}
      />
      <button type="button" disabled={!file || loading} onClick={handleRun}>
        {loading ? '核对中' : '开始核对'}
      </button>
      {error && <p role="alert">{error}</p>}
      {result && (
        <>
          <OverallSummary result={result} />
          {result.check_results.map((check) => (
            <CheckResultCard key={check.check_id} check={check} />
          ))}
        </>
      )}
    </main>
  );
}
```

- [ ] **Step 2: Wire page into app routing**

Modify the existing frontend app entry to render `ReportSelfCheckPage` at the report self-check route. If the app has no router yet, render `ReportSelfCheckPage` from `frontend/src/App.tsx`:

```tsx
import { ReportSelfCheckPage } from './pages/ReportSelfCheckPage';

export default function App() {
  return <ReportSelfCheckPage />;
}
```

- [ ] **Step 3: Build frontend**

Run:

```bash
cd frontend
npm run build
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/ReportSelfCheckPage.tsx frontend/src/App.tsx
git commit -m "feat: add report self-check page"
```

## Task 13: End-to-End Smoke Test

**Files:**
- Modify only test files if failures reveal test assumptions.

- [ ] **Step 1: Run backend tests**

Run:

```bash
cd backend
python -m pytest -q
```

Expected: PASS.

- [ ] **Step 2: Run frontend build**

Run:

```bash
cd frontend
npm run build
```

Expected: PASS.

- [ ] **Step 3: Run API against a sample report with mocked Codex transport**

Add a test-only dependency override or service injection so the API can use `StaticJudgeTransport` and does not call live Codex. The smoke assertion must verify:

```python
assert response.status_code == 200
payload = response.json()
assert payload["summary"]["total_checks"] == 14
assert [item["check_id"] for item in payload["check_results"]] == [
    "C00", "C01", "C02", "C03", "C04", "C06", "C07", "C08",
    "C12", "C13", "C14", "C15", "C16", "C17",
]
```

- [ ] **Step 4: Run one manual live Codex check**

Run the backend service with a small sample report and Codex enabled. Use the smallest sample first, `素材/report/3940/3940.pdf`.

Expected:
- The API returns 14 check results.
- Each check result has a non-empty `details` object.
- Any uncertain OCR or missing label evidence is returned as `warning`.

- [ ] **Step 5: Commit**

```bash
git add backend/tests frontend/src
git commit -m "test: add report self-check smoke coverage"
```

## Self-Review Checklist

- Spec coverage: all approved checks C00, C01, C02, C03, C04, C06, C07, C08, C12, C13, C14, C15, C16, C17 are represented in the spec and implementation tasks.
- Removed checks: C05, C09, C10, C11, C18 are explicitly excluded.
- Result details: every check has a required `details` shape.
- C12 rule: all `/` or `——` test results imply expected conclusion `/`.
- C14 rule: only non-empty status is checked; placeholder reasonableness is not judged.
- Raw data safety: files under `素材/` are read-only inputs and are never modified.
- Codex boundary: program prepares evidence; Codex performs business judgement.

## Execution Options

Plan complete and saved to `docs/superpowers/plans/2026-04-23-report-self-check-codex-judge.md`. Two execution options:

1. **Subagent-Driven (recommended)** - dispatch a fresh worker per task, review between tasks, and keep changes small.
2. **Inline Execution** - execute tasks in this session using executing-plans, with checkpoints after each group of tasks.
