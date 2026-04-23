# Report Self-Check Codex Judge Requirements

## Goal

Build the report-internal self-check module for the report checking tool. The module checks one inspection report PDF at a time and uses Codex as the business judgement layer. Program code prepares evidence packages, but Codex decides whether each check passes, warns, or fails.

## Confirmed Scope

This module checks the report against itself only. It does not compare the report against the product technical requirement document.

Input:
- One inspection report PDF.
- Optional OCR/vision extraction artifacts for photos and Chinese labels.

Output:
- A structured JSON result with an overall status.
- Fourteen check results, each with summary, status, confidence, details, findings, evidence, and missing evidence.
- Each check result must expose the concrete values that were compared, not only pass/fail status.

## Non-Goals

- Do not implement PTR-to-report comparison in this module.
- Do not edit report PDFs or source materials.
- Do not use regex as the business judgement mechanism.
- Do not hide uncertainty. If evidence is missing or OCR is unreliable, return `warning` with `missing_evidence`.
- Do not fabricate page numbers, fields, OCR values, dates, captions, or conclusions.

## Codex Role

Codex is the judge. The application may use deterministic code for:
- PDF page extraction.
- OCR and image rendering.
- Table extraction.
- Candidate field extraction.
- Candidate caption and label grouping.
- Evidence package assembly.
- JSON schema validation.

The application must not use deterministic code for final business judgement such as:
- Whether two names are materially the same.
- Whether a field mismatch is substantive.
- Whether a caption covers a component.
- Whether a conclusion is logically consistent when the evidence is ambiguous.

Hard numerical helpers are allowed when they only prepare evidence. For example, extracting printed page numbers and sequence numbers into the evidence package is allowed; the Codex judgement still owns the final check result.

## Status Semantics

- `pass`: No issue found from the available evidence.
- `warning`: Evidence is incomplete, OCR is uncertain, or Codex cannot judge confidently.
- `error`: A concrete internal inconsistency or missing required item is found.

Overall status:
- If any check is `error`, overall status is `error`.
- Else if any check is `warning`, overall status is `warning`.
- Else overall status is `pass`.

## Top-Level Result Schema

```json
{
  "task_id": "uuid",
  "file_name": "QW2025-1539 Draft.pdf",
  "overall_status": "pass | warning | error",
  "report_meta": {
    "report_number": "国医检（设）字 QW2025 第 1539 号",
    "sample_number": "QW2025-1539",
    "sample_name": "射频脉冲电场消融系统",
    "client": "美敦力（上海）管理有限公司"
  },
  "summary": {
    "total_checks": 14,
    "pass_count": 0,
    "warning_count": 0,
    "error_count": 0
  },
  "check_results": []
}
```

## Per-Check Common Schema

```json
{
  "check_id": "C02",
  "check_name": "首页基础字段一致性",
  "status": "pass | warning | error",
  "confidence": "high | medium | low",
  "summary": "封面与报告首页的委托方、样品名称、型号规格、检验类别一致。",
  "details": {},
  "findings": [],
  "evidence": [],
  "missing_evidence": []
}
```

## Finding Schema

```json
{
  "severity": "error | warning",
  "title": "型号规格不一致",
  "detail": "封面型号规格为 RMD01，报告首页型号规格为 RMD-01，Codex 判断为实质不一致。",
  "expected": "RMD01",
  "actual": "RMD-01",
  "pages": [1, 3],
  "related_fields": ["型号规格"]
}
```

## Common Field Comparison Detail

Use this shape wherever a check compares two concrete values.

```json
{
  "field": "样品名称",
  "source_a_name": "封面",
  "source_a_value": "消化道脉冲电场消融仪",
  "source_a_page": 1,
  "source_b_name": "检验报告首页",
  "source_b_value": "消化道脉冲电场消融仪",
  "source_b_page": 3,
  "matched": true,
  "judgement": "内容一致，排版换行差异不影响判断。"
}
```

## Checks

### C00 文档结构完整性

Question for Codex:
- Does the report contain the required internal sections, and is the order materially normal?

Evidence package:
- Page index.
- Candidate page type for each page.
- Key text lines from each page.

Required details:
- `detected_sections`: section name, pages, evidence text.
- `missing_sections`: missing required section names.
- `section_order_ok`: boolean.

Required sections:
- 封面.
- 注意事项.
- 检验报告首页.
- 样品描述.
- 检验项目表.
- 照片页.

### C01 报告编号与样品编号一致性

Question for Codex:
- Are the report number and sample number consistent across cover, report home page, and headers?
- Does the sample number tail correspond to the report number tail?

Evidence package:
- Cover report number.
- Report home report number.
- Header report numbers from sampled or all report pages.
- Sample numbers from report home and headers where available.
- Extracted tail candidates.

Required details:
- `report_number.cover`.
- `report_number.report_home`.
- `report_number.headers`.
- `sample_number.report_home`.
- `sample_number.headers`.
- `tail_match.report_tail`.
- `tail_match.sample_tail`.
- `tail_match.matched`.

### C02 首页基础字段一致性

Question for Codex:
- Do cover and report home page express the same `委托方`, `样品名称`, `型号规格`, and `检验类别`?

Evidence package:
- Cover field candidates and raw text.
- Report home field candidates and raw text.

Required details:
- `field_comparisons` for `委托方`, `样品名称`, `型号规格`, `检验类别`.

### C03 首页扩展字段一致性

Question for Codex:
- Are report home fields supported by the main sample label or sample description?
- If report home uses `见样品描述栏`, is the usage consistent and supported?

Evidence package:
- Report home values for `型号规格`, `生产日期`, `产品编号/批号`, `委托方`, `委托方地址`.
- Main sample Chinese label OCR fields.
- Main sample row from sample description.
- Flags for fields that say `见样品描述栏`.

Required details:
- `field_comparisons`: field, report home value, label value, sample description value, support source, matched.
- `see_sample_desc_consistent`.

### C04 时间逻辑一致性

Question for Codex:
- Do production date, arrival date, inspection start date, inspection end date, and issue date follow a valid timeline?

Evidence package:
- Date values with source page and raw text.
- Normalized date candidates prepared by code.

Required details:
- `dates.production_date`.
- `dates.arrival_date`.
- `dates.inspection_start_date`.
- `dates.inspection_end_date`.
- `dates.issue_date`.
- `timeline_checks`: each relationship with left value, right value, and matched.

Required timeline relationships:
- 生产日期 <= 到样日期.
- 到样日期 <= 检验开始日期.
- 检验开始日期 <= 检验结束日期.
- 检验结束日期 <= 签发日期, when issue date exists.

### C06 样品描述字段一致性

Question for Codex:
- For each component row, do the sample description fields match the corresponding Chinese label fields?

Evidence package:
- Sample description table rows.
- Matched label OCR result for each component.
- Candidate matching reason, such as caption or component name.

Fields to compare:
- 部件名称.
- 型号/规格.
- 批号/序列号.
- 生产日期.
- 失效日期.

Excluded fields:
- 序号.
- 备注.

Required details:
- `rows`: component name, sample description row, label fields, field comparisons.

### C07 照片覆盖性

Question for Codex:
- Does each component in sample description have at least one corresponding photo caption?

Evidence package:
- Component list from sample description.
- Photo captions.
- Candidate matches.
- Remarks that include `本次检测未使用`.

Required details:
- `components`: component name, remark, matched photo captions, covered.

Exception:
- Components marked `本次检测未使用` do not fail when photos are absent.

### C08 中文标签覆盖性

Question for Codex:
- Does each component in sample description have at least one corresponding Chinese label or label sample caption?

Evidence package:
- Component list from sample description.
- Chinese label captions.
- OCR text attached to label captions.
- Candidate matches.
- Remarks that include `本次检测未使用`.

Required details:
- `components`: component name, remark, matched label captions, covered.

Exception:
- Components marked `本次检测未使用` do not fail when labels are absent.

### C12 检验结果与单项结论逻辑

Question for Codex:
- For each sequence number, does the actual item conclusion match the expected conclusion implied by the test results?

Evidence package:
- Inspection table grouped by sequence number.
- All test results under each sequence.
- Actual item conclusion.

Decision rules:
- If any test result clearly says `不符合要求` or is clearly negative, expected conclusion is `不符合`.
- Else if all test results under the sequence are `/` or `——`, expected conclusion is `/`.
- Else expected conclusion is `符合`.

Required details:
- `sequence_results`: sequence number, page, inspection project, test results, actual conclusion, expected conclusion, matched.

### C13 单项结论与总结论逻辑

Question for Codex:
- Is the overall report conclusion consistent with all item conclusions?

Evidence package:
- All item conclusions.
- Report home overall conclusion text.

Decision rule:
- If any item conclusion is `不符合`, the overall conclusion must not state that all tested items comply.

Required details:
- `overall_conclusion_text`.
- `nonconforming_sequences`.
- `overall_consistent`.

### C14 非空字段核对

Question for Codex:
- Are `检验结果`, `单项结论`, and `备注` non-empty for inspection table rows, considering merged-cell inheritance?

Evidence package:
- Inspection table rows.
- Merged row or continuation row metadata if available.
- Raw values for `检验结果`, `单项结论`, `备注`.

Decision rule:
- Only judge whether a value exists.
- Do not judge whether `/` or `——` is reasonable.

Required details:
- `rows`: sequence number, page, project, test result, item conclusion, remark.
- `empty_field_rows`: rows with empty field names.

### C15 序号连续性与续表正确性

Question for Codex:
- Are inspection sequence numbers continuous, unique, and correctly marked when continuing across pages?

Evidence package:
- Sequence text for each inspection table row.
- Row page numbers.
- Continuation metadata if available.
- Raw sequence text with `续` markers.

Required details:
- `sequence_list`.
- `missing_numbers`.
- `duplicate_numbers`.
- `continuation_marker_findings`.

### C16 页码连续性

Question for Codex:
- From report home page onward, are printed page numbers continuous, total page count consistent, and final page closed?

Evidence package:
- Printed page number text from each report page.
- Parsed total and current page candidates.
- PDF page index.

Required details:
- `page_infos`: pdf page, printed page, total pages, raw text.
- `missing_pages`.
- `duplicate_pages`.
- `total_consistent`.
- `final_page_match`.

### C17 术语与格式一致性

Question for Codex:
- Are repeated names and formats internally consistent for the same object?

Evidence package:
- Occurrences of product names.
- Occurrences of component names.
- Occurrences of company names.
- Occurrences of date formats and model formats.
- Program-clustered candidate groups for likely same objects.

Scope:
- 产品名称.
- 部件名称.
- 公司名称.
- 同一字段的日期写法.
- 同一字段的型号写法.

Required details:
- `term_groups`: term type, canonical value, occurrences, consistent.

## Codex Prompt Contract

Each check prompt must:
- Identify the check ID and check name.
- Include only the evidence needed for that check.
- Instruct Codex not to invent missing evidence.
- Instruct Codex to return only JSON matching the check schema.
- Ask Codex to set confidence to `low` when OCR quality or evidence coverage is weak.

## Codex CLI Integration

The implementation should use an adapter so the judgement backend can be replaced.

Primary local adapter:

```bash
codex exec --sandbox read-only --ask-for-approval never --output-schema path/to/schema.json -
```

The prompt is passed through stdin. The output is parsed from the final assistant message or an output file configured by the adapter.

## Sample Corpus

Available paired sample IDs:
- `1539`
- `2795`
- `3940`
- `5332`
- `5780`
- `5782`

Report self-check uses files under `素材/report/<id>/`.

Known extraction risks:
- Some PDFs are Word-generated and have usable text layers.
- Some supporting PTR PDFs are scans, but PTR files are outside this module.
- Photo and label checks may require OCR or rendered page crops.

## Acceptance Criteria

- A user can upload or select one report PDF.
- The system returns exactly fourteen check results: C00, C01, C02, C03, C04, C06, C07, C08, C12, C13, C14, C15, C16, C17.
- Every check result includes `details`.
- C02 details show concrete cover and report home values for each compared field.
- C12 details show concrete sequence number, test results, actual conclusion, and expected conclusion.
- C14 checks only non-empty status and does not judge whether `/` or `——` is reasonable.
- Missing OCR, missing captions, or uncertain extraction returns `warning`, not fabricated pass/fail evidence.
- No raw files under `素材/` are modified.
