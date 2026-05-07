import re
from typing import Any


RECORD_REPORT_STANDARD_GB9706_1 = "gb9706_1"
RECORD_REPORT_STANDARD_GB9706_202 = "gb9706_202"
RECORD_REPORT_CHECK_ID = "RECORD-REPORT-GB9706-1"
RECORD_REPORT_CHECK_NAME = "原始记录 vs 报告 GB 9706.1-2020 序号级核对"
RECORD_REPORT_GB9706_202_CHECK_ID = "RECORD-REPORT-GB9706-202"
RECORD_REPORT_GB9706_202_CHECK_NAME = "原始记录 vs 报告 GB 9706.202-2021 序号级核对"

VALID_JUDGEMENTS = {"符合", "不符合", "不适用"}
MISSING_JUDGEMENT = "缺失"
CHECK_MARK_TOKENS = {"☑", "✓", "✔", "√", "■", "●", "X", "x", "×"}
CHECKBOX_TOKENS = {"□", "☐", ""}


class RecordReportEvidenceBuilder:
    def build_all(
        self,
        extracted_record: dict[str, Any],
        extracted_report: dict[str, Any],
        record_report_standard: str = RECORD_REPORT_STANDARD_GB9706_1,
    ) -> list[dict[str, Any]]:
        if record_report_standard == RECORD_REPORT_STANDARD_GB9706_202:
            return self._build_gb9706_202(extracted_record, extracted_report)
        return self._build_gb9706_1(extracted_record, extracted_report)

    def _build_gb9706_1(
        self,
        extracted_record: dict[str, Any],
        extracted_report: dict[str, Any],
    ) -> list[dict[str, Any]]:
        record_entries = extract_record_entries(list(extracted_record.get("pages", [])))
        report_rows = extract_report_rows(list(extracted_report.get("pages", [])))
        comparison_bundle = build_record_report_comparisons(record_entries, report_rows)

        evidence = {
            "record_report_standard": RECORD_REPORT_STANDARD_GB9706_1,
            "record_file_name": extracted_record.get("file_name", ""),
            "report_file_name": extracted_report.get("file_name", ""),
            "record_entries": record_entries,
            "report_rows": report_rows,
            **comparison_bundle,
        }
        return [
            {
                "check_id": RECORD_REPORT_CHECK_ID,
                "check_name": RECORD_REPORT_CHECK_NAME,
                "required_details": [
                    "comparisons",
                    "mismatches",
                    "missing_mappings",
                    "summary_counts",
                ],
                "check_rules": [
                    "按报告序号 1-118 逐项核对 GB 9706.1-2020 标准条款。",
                    "原始记录条款按报告标准条款前缀归并到报告序号。",
                    "原始记录聚合判定：任一不符合为不符合；否则任一符合为符合；否则全不适用为不适用；无证据为缺失。",
                    "真实判定不一致为 error；缺失或无法映射为 warning。",
                ],
                "evidence": evidence,
            }
        ]

    def _build_gb9706_202(
        self,
        extracted_record: dict[str, Any],
        extracted_report: dict[str, Any],
    ) -> list[dict[str, Any]]:
        record_entries = extract_gb9706_202_record_entries(list(extracted_record.get("pages", [])))
        report_rows = extract_gb9706_202_report_rows(list(extracted_report.get("pages", [])))
        reference_ranges = _filter_reference_ranges_for_report_rows(
            extract_gb9706_202_report_reference_ranges(list(extracted_report.get("pages", []))),
            report_rows,
        )
        comparison_bundle = build_gb9706_202_record_report_comparisons(
            record_entries,
            report_rows,
            reference_ranges,
        )

        evidence = {
            "record_report_standard": RECORD_REPORT_STANDARD_GB9706_202,
            "record_file_name": extracted_record.get("file_name", ""),
            "report_file_name": extracted_report.get("file_name", ""),
            "record_entries": record_entries,
            "report_rows": report_rows,
            "report_reference_ranges": reference_ranges,
            **comparison_bundle,
        }
        return [
            {
                "check_id": RECORD_REPORT_GB9706_202_CHECK_ID,
                "check_name": RECORD_REPORT_GB9706_202_CHECK_NAME,
                "required_details": [
                    "comparisons",
                    "mismatches",
                    "missing_mappings",
                    "summary_counts",
                ],
                "check_rules": [
                    "按报告中自动识别的 GB 9706.202-2021 检验项目表序号逐项核对。",
                    "优先按 201.* 或 208 条款号映射；条款拆分无法唯一匹配时，允许按报告连续范围与原始记录序号顺序兜底。",
                    "若 deterministic_issues 为空且报告判定与原始记录聚合判定一致，应判定 pass；不得仅因兜底映射、父条款分支映射或 OCR 条款号差异给 warning。",
                    "原始记录判定来自实测数据、备注和绘图符号；无法确定时必须 warning 或交给 Codex，不得静默通过。",
                    "报告产品技术要求 2.x 行即使引用 GB 9706.202-2021，也不属于本原始记录核对范围。",
                    "真实判定不一致为 error；缺失、无法映射或符号不确定为 warning。",
                ],
                "evidence": evidence,
            }
        ]


def normalize_clause_number(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""

    text = text.translate(str.maketrans({"．": ".", "。": ".", "｡": "."}))
    text = re.sub(r"(?<=\d)\s*\.\s*(?=\d)", ".", text)
    text = re.sub(r"\.+", ".", text).strip(". ")
    text = _remove_repeated_clause_prefix(text)
    if not re.fullmatch(r"\d+(?:\.\d+)+", text):
        return ""

    first_part = int(text.split(".", 1)[0])
    if first_part < 4 or first_part > 17:
        return ""
    return text


def extract_clause_numbers(text: str) -> list[str]:
    clauses: list[str] = []
    pattern = re.compile(r"(?<!\d)(\d{1,4}(?:\s*[.．。]\s*\d{1,4}){1,6})(?!\s*[.．。]\s*\d)")
    for match in pattern.finditer(str(text or "")):
        clause = normalize_clause_number(match.group(1))
        if clause and clause not in clauses:
            clauses.append(clause)
    return clauses


def normalize_gb9706_202_clause_number(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""

    text = text.translate(str.maketrans({"．": ".", "。": ".", "｡": "."}))
    text = re.sub(r"(?<=\d)\s*\.\s*(?=\d)", ".", text)
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"\.+", ".", text).strip(". ")
    text = _remove_repeated_clause_prefix(text)
    if text == "208":
        return text
    if re.fullmatch(r"201(?:\.\d+){1,6}", text):
        return text
    return ""


def extract_gb9706_202_clause_numbers(text: str) -> list[str]:
    clauses: list[str] = []
    pattern = re.compile(
        r"(?<!\d)(208|201(?:\s*[.．。]\s*\d{1,4}){1,6}(?:\s+\d{1,4})?)(?!\s*[.．。]\s*\d)"
    )
    for match in pattern.finditer(str(text or "")):
        clause = normalize_gb9706_202_clause_number(match.group(1))
        if clause and clause not in clauses:
            clauses.append(clause)
    return clauses


def _extract_top_level_clause_numbers(text: str) -> list[str]:
    clauses: list[str] = []
    for match in re.finditer(r"(?<![\d.])([4-9]|1[0-7])(?![\d.A-Za-zµμ°%])", str(text or "")):
        clause = match.group(1)
        if clause not in clauses:
            clauses.append(clause)
    return clauses


def _primary_scope_clauses(clauses: list[str]) -> list[str]:
    if not clauses:
        return []
    primary_top_level = clauses[0].split(".", 1)[0]
    return [
        clause
        for clause in clauses
        if clause == primary_top_level or clause.startswith(f"{primary_top_level}.")
    ]


def normalize_judgement(value: Any) -> str:
    text = re.sub(r"\s+", "", str(value or ""))
    if not text:
        return ""
    if any(token in text for token in ["不适用", "不涉及", "不适合", "N/A", "NA"]):
        return "不适用"
    if any(token in text for token in ["不符合", "不合格", "未符合"]):
        return "不符合"
    if any(token in text for token in ["符合", "合格"]):
        return "符合"
    return ""


def normalize_report_judgement(conclusion: Any, result: Any = "", remark: Any = "") -> str:
    conclusion_text = re.sub(r"\s+", "", str(conclusion or ""))
    result_text = re.sub(r"\s+", "", str(result or ""))
    combined = "".join([conclusion_text, result_text, re.sub(r"\s+", "", str(remark or ""))])

    explicit = normalize_judgement(conclusion_text) or normalize_judgement(result_text)
    if explicit:
        return explicit
    if conclusion_text and _is_not_applicable_marker(conclusion_text):
        return "不适用"
    if result_text and _is_not_applicable_marker(result_text):
        return "不适用"
    if combined and _is_not_applicable_marker(combined):
        return "不适用"
    return ""


def aggregate_record_judgement(record_entries: list[dict[str, Any]]) -> str:
    judgements = [str(entry.get("judgement") or "") for entry in record_entries]
    judgements = [judgement for judgement in judgements if judgement in VALID_JUDGEMENTS]
    if not judgements:
        return MISSING_JUDGEMENT
    if "不符合" in judgements:
        return "不符合"
    if "符合" in judgements:
        return "符合"
    if all(judgement == "不适用" for judgement in judgements):
        return "不适用"
    return MISSING_JUDGEMENT


def extract_record_entries(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for page in pages:
        if not _looks_like_record_checklist_page(page):
            continue

        layout_entries = _extract_record_entries_from_layout(page)
        if layout_entries:
            entries.extend(layout_entries)
            continue
        entries.extend(_extract_record_entries_from_text(page))
    return _dedupe_entries(entries)


def extract_report_rows(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for page in pages:
        if not _looks_like_report_table_page(page):
            continue

        stop_after_page = _report_page_has_sequence_after_gb9706(page)
        layout_rows = _extract_report_rows_from_layout(page)
        if layout_rows:
            rows.extend(layout_rows)
        else:
            rows.extend(_extract_report_rows_from_text(page))
        if stop_after_page:
            break
    return _dedupe_report_rows(rows)


def build_record_report_comparisons(
    record_entries: list[dict[str, Any]], report_rows: list[dict[str, Any]]
) -> dict[str, Any]:
    comparisons: list[dict[str, Any]] = []
    mapped_record_entry_ids: set[int] = set()
    missing_mappings: list[dict[str, Any]] = []

    if not report_rows:
        missing_mappings.append(
            {
                "type": "report_table_missing",
                "issues": ["report_rows_missing"],
                "reason": "未能从报告中抽取到 GB 9706.1-2020 序号 1-118 检验表行。",
            }
        )
    if not record_entries:
        missing_mappings.append(
            {
                "type": "record_table_missing",
                "issues": ["record_entries_missing"],
                "reason": "未能从原始记录主检查表中抽取到带条款号和勾选判定的记录行。",
            }
        )

    for row in sorted(report_rows, key=lambda item: int(item.get("sequence") or 0)):
        report_clauses = [str(clause) for clause in row.get("standard_clauses", []) if clause]
        matched_record_entries = [
            entry for entry in record_entries if _record_entry_matches_report_clauses(entry, report_clauses)
        ]
        for entry in matched_record_entries:
            mapped_record_entry_ids.add(id(entry))

        record_judgement = aggregate_record_judgement(matched_record_entries)
        report_judgement = str(row.get("report_judgement") or "") or MISSING_JUDGEMENT
        issues = _comparison_issues(report_clauses, matched_record_entries, record_judgement, report_judgement)

        comparison = {
            "sequence": row.get("sequence"),
            "report_page": row.get("page"),
            "report_standard_clause": row.get("standard_clause", ""),
            "report_standard_clauses": report_clauses,
            "report_standard_requirement": row.get("standard_requirement", ""),
            "report_result": row.get("inspection_result", ""),
            "report_conclusion": row.get("single_conclusion", ""),
            "report_judgement": report_judgement,
            "record_aggregate_judgement": record_judgement,
            "record_entry_count": len(matched_record_entries),
            "record_entries": _record_entry_summaries(matched_record_entries),
            "matched": not issues,
            "issue": issues[0] if issues else "",
            "issues": issues,
        }
        comparisons.append(comparison)

        if issues and "mismatch" not in issues:
            missing_mappings.append(
                {
                    "type": "report_row_mapping",
                    "sequence": row.get("sequence"),
                    "report_page": row.get("page"),
                    "report_standard_clause": row.get("standard_clause", ""),
                    "issues": issues,
                    "reason": _missing_mapping_reason(issues),
                }
            )

    for entry in record_entries:
        if id(entry) in mapped_record_entry_ids:
            continue
        if not entry.get("clauses"):
            issue = "record_clause_missing"
            reason = "原始记录行未能抽取到可映射的标准条款号。"
        else:
            issue = "record_clause_unmapped"
            reason = "原始记录条款未能匹配到报告序号 1-118 的标准条款前缀。"
        missing_mappings.append(
            {
                "type": "record_entry_mapping",
                "record_page": entry.get("page"),
                "record_sequence": entry.get("record_sequence"),
                "record_clauses": entry.get("clauses", []),
                "record_judgement": entry.get("judgement", ""),
                "issues": [issue],
                "reason": reason,
            }
        )

    mismatches = [comparison for comparison in comparisons if comparison["issue"] == "mismatch"]
    summary_counts = {
        "report_row_count": len(report_rows),
        "record_entry_count": len(record_entries),
        "compared_count": sum(
            1 for comparison in comparisons if not comparison["issues"] or comparison["issues"] == ["mismatch"]
        ),
        "matched_count": sum(1 for comparison in comparisons if comparison["matched"]),
        "mismatch_count": len(mismatches),
        "missing_mapping_count": len(missing_mappings),
        "unmapped_record_entry_count": sum(
            1 for item in missing_mappings if item.get("type") == "record_entry_mapping"
        ),
        "record_judgement_counts": _judgement_counts(entry.get("judgement") for entry in record_entries),
        "report_judgement_counts": _judgement_counts(row.get("report_judgement") for row in report_rows),
    }
    return {
        "comparisons": comparisons,
        "mismatches": mismatches,
        "missing_mappings": missing_mappings,
        "summary_counts": summary_counts,
    }


def extract_gb9706_202_report_reference_ranges(pages: list[dict[str, Any]]) -> list[dict[str, int]]:
    ranges: list[dict[str, int]] = []
    range_pattern = re.compile(r"序号\s*(\d{1,3})\s*(?:~|～|至|到|-)\s*(?:序号)?\s*(\d{1,3})")
    for page in pages:
        text = str(page.get("text", ""))
        normalized = _normalize_text(text)
        if "9706.202" not in normalized and "9706202" not in normalized:
            continue
        for match in range_pattern.finditer(text):
            if not _range_belongs_to_gb9706_202(text, match.start(), match.end()):
                continue
            start = _positive_int(match.group(1))
            end = _positive_int(match.group(2))
            if start is None or end is None or end < start:
                continue
            ranges.append({"start": start, "end": end, "page": _positive_int(page.get("page")) or 0})
    return _dedupe_ranges(ranges)


def _range_belongs_to_gb9706_202(text: str, range_start: int, range_end: int) -> bool:
    prior_window_start = max(0, range_start - 120)
    prior_mentions = _standard_mentions(text[prior_window_start:range_start], prior_window_start)
    if prior_mentions:
        prior_start, prior_end, prior_standard = prior_mentions[-1]
        between_prior = text[prior_end:range_start]
        if "见" in between_prior and not re.search(r"[。；;\n]", between_prior):
            return prior_standard == RECORD_REPORT_STANDARD_GB9706_202

    following_mentions = _standard_mentions(text[range_end : range_end + 140], range_end)
    if following_mentions:
        return following_mentions[0][2] == RECORD_REPORT_STANDARD_GB9706_202

    if prior_mentions:
        return prior_mentions[-1][2] == RECORD_REPORT_STANDARD_GB9706_202
    return False


def _standard_mentions(text: str, offset: int = 0) -> list[tuple[int, int, str]]:
    mentions: list[tuple[int, int, str]] = []
    pattern = re.compile(
        r"9706\s*[.．]?\s*202|9706202|9706\s*[.．]?\s*1(?!\s*\d)|97061(?!\d)",
        re.IGNORECASE,
    )
    for match in pattern.finditer(str(text or "")):
        raw = _normalize_text(match.group(0))
        standard = RECORD_REPORT_STANDARD_GB9706_202 if "9706202" in raw or "9706.202" in raw else RECORD_REPORT_STANDARD_GB9706_1
        mentions.append((offset + match.start(), offset + match.end(), standard))
    return mentions


def extract_gb9706_202_report_rows(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    reference_ranges = extract_gb9706_202_report_reference_ranges(pages)
    rows: list[dict[str, Any]] = []
    last_columns: dict[str, Any] | None = None
    for page in pages:
        if not _looks_like_report_table_page(page):
            continue

        words = _layout_words(page)
        columns = _report_layout_columns(words, page.get("width")) if words else None
        if columns is not None:
            last_columns = columns
        elif last_columns is not None:
            columns = last_columns
        if columns is None:
            text_rows = _extract_gb9706_202_report_rows_from_text(page)
            rows.extend(text_rows)
            continue

        for row in _layout_row_spans(words, columns["sequence"], columns["header_bottom"], page.get("height"), 1, 240):
            parsed = _parse_gb9706_202_report_layout_row(page, words, columns, row)
            if parsed is not None:
                rows.append(parsed)

    deduped_rows = _dedupe_gb9706_202_report_rows(rows)
    if reference_ranges:
        ranged = [
            row
            for row in deduped_rows
            if _sequence_in_ranges(_positive_int(row.get("sequence")), reference_ranges)
        ]
        if ranged:
            return ranged
    return deduped_rows


def extract_gb9706_202_record_entries(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for page in pages:
        if not _looks_like_gb9706_202_record_page(page):
            continue
        layout_entries = _extract_gb9706_202_record_entries_from_layout(page)
        if layout_entries:
            entries.extend(layout_entries)
            continue
        entries.extend(_extract_gb9706_202_record_entries_from_text(page))
    return _merge_gb9706_202_record_entries(entries)


def build_gb9706_202_record_report_comparisons(
    record_entries: list[dict[str, Any]],
    report_rows: list[dict[str, Any]],
    reference_ranges: list[dict[str, int]],
) -> dict[str, Any]:
    comparisons: list[dict[str, Any]] = []
    mapped_record_entry_ids: set[int] = set()
    missing_mappings: list[dict[str, Any]] = []

    if not report_rows:
        missing_mappings.append(
            {
                "type": "report_table_missing",
                "issues": ["report_rows_missing"],
                "reason": "未能从报告中抽取到 GB 9706.202-2021 检验项目表行。",
            }
        )
    if not record_entries:
        missing_mappings.append(
            {
                "type": "record_table_missing",
                "issues": ["record_entries_missing"],
                "reason": "未能从 GB 9706.202-2021 原始记录表 2 中抽取到序号行。",
            }
        )

    sequence_mapping_start = _gb9706_202_sequence_mapping_start(report_rows, reference_ranges)
    for row in sorted(report_rows, key=lambda item: int(item.get("sequence") or 0)):
        report_clauses = [str(clause) for clause in row.get("standard_clauses", []) if clause]
        clause_matches = [
            entry for entry in record_entries if _record_entry_matches_gb9706_202_report_clauses(entry, report_clauses)
        ]
        fallback_entry = _gb9706_202_fallback_record_entry(row, record_entries, sequence_mapping_start)
        matched_record_entries = clause_matches
        mapping_method = "clause"
        if (
            fallback_entry is not None
            and len(clause_matches) != 1
            and _gb9706_202_parent_clause_sequence_match(fallback_entry, report_clauses)
        ):
            matched_record_entries = [fallback_entry]
            mapping_method = "parent_clause_sequence"
        elif fallback_entry is not None and len(clause_matches) != 1:
            matched_record_entries = [fallback_entry]
            mapping_method = "sequence_fallback"

        for entry in matched_record_entries:
            mapped_record_entry_ids.add(id(entry))

        record_judgement = aggregate_record_judgement(matched_record_entries)
        report_judgement = str(row.get("report_judgement") or "") or MISSING_JUDGEMENT
        issues = _comparison_issues(report_clauses, matched_record_entries, record_judgement, report_judgement)

        comparison = {
            "record_report_standard": RECORD_REPORT_STANDARD_GB9706_202,
            "sequence": row.get("sequence"),
            "report_page": row.get("page"),
            "report_standard_clause": row.get("standard_clause", ""),
            "report_standard_clauses": report_clauses,
            "report_standard_requirement": row.get("standard_requirement", ""),
            "report_result": row.get("inspection_result", ""),
            "report_conclusion": row.get("single_conclusion", ""),
            "report_judgement": report_judgement,
            "record_aggregate_judgement": record_judgement,
            "record_entry_count": len(matched_record_entries),
            "record_entries": _record_entry_summaries(matched_record_entries),
            "matched": not issues,
            "issue": issues[0] if issues else "",
            "issues": issues,
            "mapping_method": mapping_method,
        }
        comparisons.append(comparison)

        if issues and "mismatch" not in issues:
            missing_mappings.append(
                {
                    "type": "report_row_mapping",
                    "sequence": row.get("sequence"),
                    "report_page": row.get("page"),
                    "report_standard_clause": row.get("standard_clause", ""),
                    "issues": issues,
                    "reason": _missing_mapping_reason(issues),
                }
            )

    for entry in record_entries:
        if id(entry) in mapped_record_entry_ids:
            continue
        if not entry.get("clauses"):
            issue = "record_clause_missing"
            reason = "GB 9706.202 原始记录行未能抽取到可映射的条款号。"
        else:
            issue = "record_clause_unmapped"
            reason = "GB 9706.202 原始记录条款未能匹配到报告中的 201.* 或 208 条款。"
        missing_mappings.append(
            {
                "type": "record_entry_mapping",
                "record_page": entry.get("page"),
                "record_sequence": entry.get("record_sequence"),
                "record_clauses": entry.get("clauses", []),
                "record_judgement": entry.get("judgement", ""),
                "issues": [issue],
                "reason": reason,
            }
        )

    mismatches = [comparison for comparison in comparisons if comparison["issue"] == "mismatch"]
    summary_counts = {
        "record_report_standard": RECORD_REPORT_STANDARD_GB9706_202,
        "report_row_count": len(report_rows),
        "record_entry_count": len(record_entries),
        "compared_count": sum(
            1 for comparison in comparisons if not comparison["issues"] or comparison["issues"] == ["mismatch"]
        ),
        "matched_count": sum(1 for comparison in comparisons if comparison["matched"]),
        "mismatch_count": len(mismatches),
        "missing_mapping_count": len(missing_mappings),
        "unmapped_record_entry_count": sum(
            1 for item in missing_mappings if item.get("type") == "record_entry_mapping"
        ),
        "record_judgement_counts": _judgement_counts(entry.get("judgement") for entry in record_entries),
        "report_judgement_counts": _judgement_counts(row.get("report_judgement") for row in report_rows),
        "report_reference_ranges": reference_ranges,
    }
    return {
        "comparisons": comparisons,
        "mismatches": mismatches,
        "missing_mappings": missing_mappings,
        "summary_counts": summary_counts,
    }


def _looks_like_record_checklist_page(page: dict[str, Any]) -> bool:
    text = _normalize_text(str(page.get("text", "")))
    if all(marker in text for marker in ["序号", "要求描述", "建议观察记录", "符合性"]):
        return True
    page_number = _positive_int(page.get("page"))
    return bool(page_number and 6 <= page_number <= 96 and "符合性" in text)


def _looks_like_report_table_page(page: dict[str, Any]) -> bool:
    text = _normalize_text(str(page.get("text", "")))
    return (
        "序号" in text
        and ("标准条款" in text or "检验项目" in text)
        and "标准要求" in text
        and "单项结论" in text
    )


def _looks_like_gb9706_202_record_page(page: dict[str, Any]) -> bool:
    text = _normalize_text(str(page.get("text", "")))
    return "检测原始记录" in text and ("GB9706.202-2021" in text or "GB9706202-2021" in text)


def _parse_gb9706_202_report_layout_row(
    page: dict[str, Any],
    words: list[dict[str, Any]],
    columns: dict[str, Any],
    row: dict[str, Any],
) -> dict[str, Any] | None:
    sequence = _positive_int(row.get("row_no"))
    if sequence is None:
        return None
    clause_text = _join_words(_words_in_column_span(words, columns["clause"], row["top"], row["bottom"]))
    requirement_text = _join_words(
        _words_in_column_span(words, columns["requirement"], row["top"], row["bottom"])
    )
    result_text = _join_words(_words_in_column_span(words, columns["result"], row["top"], row["bottom"]))
    conclusion_text = _join_words(
        _words_in_column_span(words, columns["conclusion"], row["top"], row["bottom"])
    )
    remark_text = _join_words(_words_in_column_span(words, columns["remark"], row["top"], row["bottom"]))
    clauses = extract_gb9706_202_clause_numbers(clause_text)
    if not clauses:
        clauses = extract_gb9706_202_clause_numbers(requirement_text)
    if not clauses:
        return None

    return {
        "sequence": sequence,
        "page": page.get("page"),
        "standard_clause": "、".join(clauses),
        "standard_clauses": clauses,
        "standard_requirement": requirement_text,
        "inspection_result": result_text,
        "single_conclusion": conclusion_text,
        "remark": remark_text,
        "report_judgement": normalize_report_judgement(conclusion_text, result_text, remark_text),
        "raw_text": " ".join(
            [
                str(sequence),
                clause_text,
                requirement_text,
                result_text,
                conclusion_text,
                remark_text,
            ]
        ).strip(),
        "source": "layout",
    }


def _extract_gb9706_202_report_rows_from_text(page: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    current_lines: list[str] = []

    def flush_current() -> None:
        if not current_lines:
            return
        raw_text = " ".join(current_lines)
        match = re.match(r"^(?:续\s*)?(\d{1,3})(?:\s+|$)(.*)$", raw_text)
        if not match:
            return
        sequence = _positive_int(match.group(1))
        if sequence is None:
            return
        body = match.group(2)
        clauses = extract_gb9706_202_clause_numbers(body)
        if not clauses:
            return
        judgement = _last_judgement_token(body)
        rows.append(
            {
                "sequence": sequence,
                "page": page.get("page"),
                "standard_clause": "、".join(clauses),
                "standard_clauses": clauses,
                "standard_requirement": body,
                "inspection_result": "",
                "single_conclusion": judgement,
                "remark": "",
                "report_judgement": normalize_report_judgement(judgement, body, ""),
                "raw_text": raw_text,
                "source": "text",
            }
        )

    for line in _compact_lines(str(page.get("text", ""))):
        if _looks_like_report_header_line(line):
            continue
        match = re.match(r"^(?:续\s*)?(\d{1,3})(?:\s+|$)", line)
        if match:
            flush_current()
            current_lines = [line]
            continue
        if current_lines:
            current_lines.append(line)

    flush_current()
    return rows


def _extract_gb9706_202_record_entries_from_layout(page: dict[str, Any]) -> list[dict[str, Any]]:
    words = _layout_words(page)
    if not words:
        return []
    columns = _gb9706_202_record_layout_columns(words, page.get("width"))
    if columns is None:
        return []

    entries: list[dict[str, Any]] = []
    for row in _gb9706_202_record_row_spans(words, columns, page):
        sequence = _positive_int(row.get("row_no"))
        if sequence is None:
            continue
        item_text = _join_words(_words_in_column_span(words, columns["item"], row["top"], row["bottom"]))
        clause_text = _join_words(_words_in_column_span(words, columns["clause"], row["top"], row["bottom"]))
        requirement_text = _join_words(
            _words_in_column_span(words, columns["requirement"], row["top"], row["bottom"])
        )
        measured_text = _join_words(_words_in_column_span(words, columns["measured"], row["top"], row["bottom"]))
        remark_text = _join_words(_words_in_column_span(words, columns["remark"], row["top"], row["bottom"]))
        clauses = extract_gb9706_202_clause_numbers(clause_text) or extract_gb9706_202_clause_numbers(
            requirement_text
        )
        if not clauses and not (item_text or requirement_text or measured_text or remark_text):
            continue
        judgement, judgement_source = _gb9706_202_record_judgement(page, columns, row, measured_text, remark_text)
        entries.append(
            {
                "page": page.get("page"),
                "pages": [_positive_int(page.get("page")) or page.get("page")],
                "record_sequence": sequence,
                "clauses": clauses,
                "inspection_item": item_text,
                "requirement_text": requirement_text,
                "measured_data": measured_text,
                "remark": remark_text,
                "observation_text": measured_text,
                "judgement": judgement,
                "symbol_judgement": judgement_source,
                "source": "layout",
            }
        )
    return entries


def _gb9706_202_record_row_spans(
    words: list[dict[str, Any]],
    columns: dict[str, Any],
    page: dict[str, Any],
) -> list[dict[str, Any]]:
    _left, right = columns["sequence"]
    sequence_right = min(float(right), 55.0)
    sequence_words = []
    for word in words:
        if word["y0"] <= columns["header_bottom"] or word["y0"] >= 780:
            continue
        if not (word["x0"] <= sequence_right and _word_center_x(word) <= sequence_right):
            continue
        if not re.fullmatch(r"\d{1,2}", word["text"]):
            continue
        sequence = int(word["text"])
        if 1 <= sequence <= 99:
            sequence_words.append(word)

    horizontal_lines = _horizontal_table_lines(page, min_width=100, y_min=max(0, columns["header_bottom"] - 25))

    def row_top_for(word: dict[str, Any]) -> float:
        candidates = [line for line in horizontal_lines if columns["header_bottom"] <= line <= word["y0"] + 1]
        if candidates:
            return max(candidates) - 0.5
        return columns["header_bottom"] + 1 if word is sequence_words[0] else word["y0"] - 2

    page_height = page.get("height")
    fallback_bottom = float(page_height) if isinstance(page_height, (int, float)) else max(word["y1"] for word in words) + 20
    fallback_bottom = min(fallback_bottom, 780.0)
    rows = []
    for index, word in enumerate(sequence_words):
        next_top = row_top_for(sequence_words[index + 1]) if index + 1 < len(sequence_words) else fallback_bottom
        rows.append({"row_no": word["text"], "top": row_top_for(word), "bottom": next_top})
    return rows


def _extract_gb9706_202_record_entries_from_text(page: dict[str, Any]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for line in _compact_lines(str(page.get("text", ""))):
        match = re.match(r"^(?:续\s*)?(\d{1,2})\s+(.+)$", line)
        if not match:
            continue
        clauses = extract_gb9706_202_clause_numbers(match.group(2))
        if not clauses:
            continue
        judgement = normalize_judgement(match.group(2)) or MISSING_JUDGEMENT
        entries.append(
            {
                "page": page.get("page"),
                "pages": [_positive_int(page.get("page")) or page.get("page")],
                "record_sequence": int(match.group(1)),
                "clauses": clauses,
                "inspection_item": "",
                "requirement_text": match.group(2),
                "measured_data": "",
                "remark": "",
                "observation_text": "",
                "judgement": judgement,
                "symbol_judgement": "text" if judgement != MISSING_JUDGEMENT else "missing",
                "source": "text",
            }
        )
    return entries


def _gb9706_202_record_layout_columns(
    words: list[dict[str, Any]],
    page_width: Any,
) -> dict[str, Any] | None:
    sequence = _find_header_group(words, "序号")
    item = _find_header_group(words, "检验项目")
    clause = _find_header_group(words, "条款号")
    requirement = _find_header_group(words, "标准要求")
    measured = _find_header_group(words, "实测数据")
    remark = _find_header_group(words, "备注")
    headers = [sequence, item, clause, requirement, measured, remark]
    if not all(headers):
        if not isinstance(page_width, (int, float)) or page_width <= 0:
            return None
        return {
            "header_bottom": 185.0,
            "sequence": (0.0, 55.0),
            "item": (55.0, 108.0),
            "clause": (108.0, 153.0),
            "requirement": (153.0, 350.0),
            "measured": (350.0, 500.0),
            "remark": (500.0, float(page_width)),
        }

    centers = [_box_center_x(header) for header in headers if header is not None]
    if centers != sorted(centers):
        return None

    right_edge = _page_right_edge(page_width, words, centers[-1])
    boundaries = [0.0]
    boundaries.extend((centers[index] + centers[index + 1]) / 2 for index in range(len(centers) - 1))
    boundaries.append(right_edge)
    return {
        "header_bottom": max(float(header["y1"]) for header in headers if header is not None),
        "sequence": (boundaries[0], boundaries[1]),
        "item": (boundaries[1], boundaries[2]),
        "clause": (boundaries[2], boundaries[3]),
        "requirement": (boundaries[3], boundaries[4]),
        "measured": (boundaries[4], boundaries[5]),
        "remark": (boundaries[5], boundaries[6]),
    }


def _gb9706_202_record_judgement(
    page: dict[str, Any],
    columns: dict[str, Any],
    row: dict[str, Any],
    measured_text: str,
    remark_text: str,
) -> tuple[str, str]:
    combined = _normalize_text(f"{measured_text} {remark_text}")
    if any(token in combined for token in ["×", "X", "不符合", "不合格"]):
        return "不符合", "text_nonconforming"
    if any(token in combined for token in ["△", "∆", "Δ", "不适用", "不涉及"]):
        return "不适用", "text_not_applicable"
    if any(token in combined for token in ["√", "✓", "✔", "符合要求", "符合"]):
        return "符合", "text_conforming"

    drawing_judgement = _gb9706_202_record_drawing_judgement(page, columns, row)
    if drawing_judgement:
        return drawing_judgement
    if measured_text.strip() and not _is_blank_marker(measured_text):
        return "符合", "typed_measured_data"
    return MISSING_JUDGEMENT, "missing_or_uncertain"


def _gb9706_202_record_drawing_judgement(
    page: dict[str, Any],
    columns: dict[str, Any],
    row: dict[str, Any],
) -> tuple[str, str] | None:
    measured_left, _ = columns["measured"]
    _, remark_right = columns["remark"]
    marks = []
    for drawing in _drawings(page):
        rect = drawing.get("rect")
        if not isinstance(rect, dict) or not _drawing_has_dark_fill(drawing):
            continue
        center_x = _rect_center_x(rect)
        center_y = _rect_center_y(rect)
        if not (measured_left <= center_x <= remark_right and row["top"] <= center_y < row["bottom"]):
            continue
        width = rect["x1"] - rect["x0"]
        height = rect["y1"] - rect["y0"]
        if width < 4 or height < 4:
            continue
        area = _rect_area(rect)
        open_distance = _drawing_path_open_distance(drawing)
        marks.append(
            {
                "width": width,
                "height": height,
                "aspect": width / height if height else 0,
                "area": area,
                "kind": _gb9706_202_drawing_mark_kind(width, height, area, open_distance),
            }
        )

    if not marks:
        return None
    if any(mark["kind"] == "check" for mark in marks):
        return "符合", "drawing_check_mark"
    if any(mark["kind"] == "delta" for mark in marks):
        return "不适用", "drawing_delta_mark"
    return None


def _gb9706_202_drawing_mark_kind(
    width: float,
    height: float,
    area: float,
    open_distance: float | None = None,
) -> str:
    aspect = width / height if height else 0
    if aspect < 0.45:
        return ""
    if (
        open_distance is not None
        and open_distance >= max(width, height) * 0.75
        and width >= 50
        and height >= 45
        and aspect <= 1.8
    ):
        return "check"
    if width >= 70 and height >= 55 and aspect <= 2.1:
        return "check"
    if area >= 2850 and width >= 52 and height >= 50 and aspect <= 1.6:
        return "check"
    if 12 <= width <= 65 and 10 <= height <= 55 and 0.75 <= aspect <= 2.3:
        return "delta"
    return ""


def _is_blank_marker(text: str) -> bool:
    compact = _normalize_text(text)
    if not compact:
        return True
    return all(char in {"/", "／", "-", "—", "–", "－"} for char in compact)


def _merge_gb9706_202_record_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_sequence: dict[int, dict[str, Any]] = {}
    judgement_parts: dict[int, list[dict[str, str]]] = {}
    for entry in entries:
        sequence = _positive_int(entry.get("record_sequence"))
        if sequence is None:
            continue
        judgement_parts.setdefault(sequence, []).append(
            {
                "judgement": str(entry.get("judgement") or ""),
                "source": str(entry.get("symbol_judgement") or ""),
            }
        )
        if sequence not in by_sequence:
            copied = dict(entry)
            copied["record_sequence"] = sequence
            copied["pages"] = _dedupe_pages(copied.get("pages", [copied.get("page")]))
            by_sequence[sequence] = copied
            continue

        existing = by_sequence[sequence]
        existing["pages"] = _dedupe_pages([*existing.get("pages", []), entry.get("page")])
        existing["page"] = existing["pages"][0] if existing["pages"] else existing.get("page")
        existing["clauses"] = _dedupe_list([*existing.get("clauses", []), *entry.get("clauses", [])])
        for key in ["inspection_item", "requirement_text", "measured_data", "remark", "observation_text"]:
            existing[key] = " ".join(part for part in [existing.get(key, ""), entry.get(key, "")] if part).strip()

    merged = []
    for sequence in sorted(by_sequence):
        entry = by_sequence[sequence]
        part_judgements = [part["judgement"] for part in judgement_parts.get(sequence, [])]
        entry["judgement"] = aggregate_record_judgement([{"judgement": value} for value in part_judgements])
        sources = [part["source"] for part in judgement_parts.get(sequence, []) if part["source"]]
        entry["symbol_judgement"] = "、".join(_dedupe_list(sources))
        merged.append(entry)
    return merged


def _dedupe_gb9706_202_report_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_sequence: dict[int, dict[str, Any]] = {}
    for row in rows:
        sequence = _positive_int(row.get("sequence"))
        if sequence is None:
            continue
        if sequence not in by_sequence:
            copied = dict(row)
            copied["sequence"] = sequence
            copied["pages"] = [_positive_int(row.get("page")) or row.get("page")]
            by_sequence[sequence] = copied
            continue
        existing = by_sequence[sequence]
        existing["pages"] = _dedupe_pages([*existing.get("pages", []), row.get("page")])
        existing["page"] = existing["pages"][0] if existing["pages"] else existing.get("page")
        existing["standard_clauses"] = _dedupe_list([*existing.get("standard_clauses", []), *row.get("standard_clauses", [])])
        existing["standard_clause"] = "、".join(existing["standard_clauses"])
        for key in ["standard_requirement", "inspection_result", "single_conclusion", "remark", "raw_text"]:
            existing[key] = " ".join(part for part in [existing.get(key, ""), row.get(key, "")] if part).strip()
        existing["report_judgement"] = existing.get("report_judgement") or row.get("report_judgement", "")
    return [by_sequence[key] for key in sorted(by_sequence)]


def _gb9706_202_sequence_mapping_start(
    report_rows: list[dict[str, Any]],
    reference_ranges: list[dict[str, int]],
) -> int | None:
    sequences = [_positive_int(row.get("sequence")) for row in report_rows]
    sequences = [sequence for sequence in sequences if sequence is not None]
    if not sequences:
        return None
    first_sequence = min(sequences)
    if reference_ranges:
        containing = [
            item["start"]
            for item in reference_ranges
            if item.get("start") and item["start"] <= first_sequence <= item["end"]
        ]
        if containing:
            return min(containing)
    return first_sequence


def _gb9706_202_fallback_record_entry(
    report_row: dict[str, Any],
    record_entries: list[dict[str, Any]],
    sequence_mapping_start: int | None,
) -> dict[str, Any] | None:
    report_sequence = _positive_int(report_row.get("sequence"))
    if report_sequence is None or sequence_mapping_start is None:
        return None
    record_sequence = report_sequence - sequence_mapping_start + 1
    for entry in record_entries:
        if _positive_int(entry.get("record_sequence")) == record_sequence:
            return entry
    return None


def _gb9706_202_parent_clause_sequence_match(entry: dict[str, Any], report_clauses: list[str]) -> bool:
    record_clauses = [
        normalize_gb9706_202_clause_number(str(clause))
        for clause in entry.get("clauses", [])
        if normalize_gb9706_202_clause_number(str(clause))
    ]
    for report_clause in report_clauses:
        parent_clause = normalize_gb9706_202_clause_number(str(report_clause))
        if not _gb9706_202_is_branch_parent_clause(parent_clause):
            continue
        if any(clause == parent_clause or clause.startswith(f"{parent_clause}.") for clause in record_clauses):
            return True
    return False


def _gb9706_202_is_branch_parent_clause(clause: str) -> bool:
    parts = clause.split(".")
    return len(parts) == 3 and parts[0] == "201" and all(part.isdigit() for part in parts)


def _record_entry_matches_gb9706_202_report_clauses(entry: dict[str, Any], report_clauses: list[str]) -> bool:
    if not report_clauses:
        return False
    for record_clause in entry.get("clauses", []):
        for report_clause in report_clauses:
            if _gb9706_202_clause_matches(str(record_clause), str(report_clause)):
                return True
    return False


def _gb9706_202_clause_matches(record_clause: str, report_clause: str) -> bool:
    record_clause = normalize_gb9706_202_clause_number(record_clause)
    report_clause = normalize_gb9706_202_clause_number(report_clause)
    if not record_clause or not report_clause:
        return False
    return record_clause == report_clause or record_clause.startswith(f"{report_clause}.") or report_clause.startswith(f"{record_clause}.")


def _sequence_in_ranges(sequence: int | None, ranges: list[dict[str, int]]) -> bool:
    if sequence is None:
        return False
    return any(item["start"] <= sequence <= item["end"] for item in ranges)


def _filter_reference_ranges_for_report_rows(
    ranges: list[dict[str, int]],
    report_rows: list[dict[str, Any]],
) -> list[dict[str, int]]:
    sequences = [_positive_int(row.get("sequence")) for row in report_rows]
    sequences = [sequence for sequence in sequences if sequence is not None]
    if not ranges or not sequences:
        return ranges
    first_sequence = min(sequences)
    last_sequence = max(sequences)
    filtered = [
        item
        for item in ranges
        if item.get("start", 0) <= first_sequence <= item.get("end", 0)
        or item.get("start", 0) <= last_sequence <= item.get("end", 0)
    ]
    return filtered or ranges


def _dedupe_ranges(ranges: list[dict[str, int]]) -> list[dict[str, int]]:
    deduped = []
    seen = set()
    for item in ranges:
        key = (item.get("start"), item.get("end"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _extract_record_entries_from_layout(page: dict[str, Any]) -> list[dict[str, Any]]:
    words = _layout_words(page)
    if not words:
        return []

    columns = _record_layout_columns(words, page.get("width"))
    if columns is None:
        return []

    labels = _record_compliance_label_positions(words, columns)
    rows = _record_checkbox_row_spans(page, words, columns)
    entries: list[dict[str, Any]] = []
    current_clauses: list[str] = []
    for row in rows:
        sequence_text = _join_words(_words_in_column_span(words, columns["sequence"], row["top"], row["bottom"]))
        requirement_words = _words_in_column_span(words, columns["requirement"], row["top"], row["bottom"])
        requirement_text = _join_words(requirement_words)
        judgement = _selected_record_judgement(page, words, row, columns, labels)
        clauses = _record_clauses_for_row(words, columns, row, sequence_text)
        if not requirement_text and sequence_text and clauses:
            requirement_text = sequence_text
        if not requirement_text:
            continue
        if not clauses and not current_clauses:
            clauses = extract_clause_numbers(requirement_text)
        if clauses:
            current_clauses = clauses
        else:
            clauses = list(current_clauses)
        if not judgement:
            continue
        entries.append(
            {
                "page": page.get("page"),
                "record_sequence": sequence_text or row["row_no"],
                "clauses": clauses,
                "requirement_text": requirement_text,
                "observation_text": _join_words(
                    _words_in_column_span(words, columns["observation"], row["top"], row["bottom"])
                ),
                "judgement": judgement,
                "source": "layout",
            }
        )
    return entries


def _extract_record_entries_from_text(page: dict[str, Any]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for line in _compact_lines(str(page.get("text", ""))):
        normalized = _normalize_text(line)
        if any(marker in normalized for marker in ["要求描述", "建议观察记录", "符合性"]):
            continue
        match = re.match(r"^(\d{1,3})\s+(.+)$", line)
        if not match:
            continue

        body = match.group(2)
        clauses = extract_clause_numbers(body)
        if not clauses:
            continue
        entries.append(
            {
                "page": page.get("page"),
                "record_sequence": match.group(1),
                "clauses": clauses,
                "requirement_text": body,
                "observation_text": "",
                "judgement": normalize_judgement(body) or MISSING_JUDGEMENT,
                "source": "text",
            }
        )
    return entries


def _extract_report_rows_from_layout(page: dict[str, Any]) -> list[dict[str, Any]]:
    words = _layout_words(page)
    if not words:
        return []

    columns = _report_layout_columns(words, page.get("width"))
    if columns is None:
        return []

    rows = _layout_row_spans(words, columns["sequence"], columns["header_bottom"], page.get("height"), 1, 118)
    report_rows: list[dict[str, Any]] = []
    for row in rows:
        clause_text = _join_words(_words_in_column_span(words, columns["clause"], row["top"], row["bottom"]))
        requirement_text = _join_words(
            _words_in_column_span(words, columns["requirement"], row["top"], row["bottom"])
        )
        result_text = _join_words(_words_in_column_span(words, columns["result"], row["top"], row["bottom"]))
        conclusion_text = _join_words(
            _words_in_column_span(words, columns["conclusion"], row["top"], row["bottom"])
        )
        remark_text = _join_words(_words_in_column_span(words, columns["remark"], row["top"], row["bottom"]))
        clauses = _primary_scope_clauses(
            extract_clause_numbers(clause_text) or _extract_top_level_clause_numbers(clause_text)
        )
        if not clauses:
            clauses = extract_clause_numbers(requirement_text)
        if not clauses:
            continue
        report_rows.append(
            {
                "sequence": int(row["row_no"]),
                "page": page.get("page"),
                "standard_clause": "、".join(clauses),
                "standard_clauses": clauses,
                "standard_requirement": requirement_text,
                "inspection_result": result_text,
                "single_conclusion": conclusion_text,
                "remark": remark_text,
                "report_judgement": normalize_report_judgement(conclusion_text, result_text, remark_text),
                "raw_text": " ".join(
                    [
                        row["row_no"],
                        clause_text,
                        requirement_text,
                        result_text,
                        conclusion_text,
                        remark_text,
                    ]
                ).strip(),
                "source": "layout",
            }
        )
    return report_rows


def _extract_report_rows_from_text(page: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    current_lines: list[str] = []

    def flush_current() -> None:
        if not current_lines:
            return
        row = _parse_report_text_row(page, current_lines)
        if row is not None:
            rows.append(row)

    for line in _compact_lines(str(page.get("text", ""))):
        if _looks_like_report_header_line(line):
            continue
        match = re.match(r"^(?:续\s*)?(\d{1,3})(?:\s+|$)", line)
        if match and 1 <= int(match.group(1)) <= 118:
            flush_current()
            current_lines = [line]
            continue
        if current_lines:
            current_lines.append(line)

    flush_current()
    return rows


def _parse_report_text_row(page: dict[str, Any], lines: list[str]) -> dict[str, Any] | None:
    raw_text = " ".join(lines)
    match = re.match(r"^(?:续\s*)?(\d{1,3})(?:\s+|$)(.*)$", raw_text)
    if not match:
        return None
    sequence = int(match.group(1))
    if not (1 <= sequence <= 118):
        return None

    body = match.group(2)
    clauses = extract_clause_numbers(body)
    if not clauses:
        return None
    judgement = _last_judgement_token(body)
    return {
        "sequence": sequence,
        "page": page.get("page"),
        "standard_clause": "、".join(clauses),
        "standard_clauses": clauses,
        "standard_requirement": body,
        "inspection_result": "",
        "single_conclusion": judgement,
        "remark": "",
        "report_judgement": normalize_report_judgement(judgement, body, ""),
        "raw_text": raw_text,
        "source": "text",
    }


def _record_layout_columns(words: list[dict[str, Any]], page_width: Any) -> dict[str, Any] | None:
    sequence = _find_header_group(words, "序号")
    requirement = _find_header_group(words, "要求描述")
    observation = _find_header_group(words, "建议观察记录")
    compliance = _find_header_group(words, "符合性")
    if not all([sequence, requirement, observation, compliance]):
        return None

    centers = {
        "sequence": _box_center_x(sequence),
        "requirement": _box_center_x(requirement),
        "observation": _box_center_x(observation),
        "compliance": _box_center_x(compliance),
    }
    if not (centers["sequence"] < centers["requirement"] < centers["observation"] < centers["compliance"]):
        return None

    seq_req_mid = (centers["sequence"] + centers["requirement"]) / 2
    req_obs_mid = (centers["requirement"] + centers["observation"]) / 2
    obs_comp_mid = (centers["observation"] + centers["compliance"]) / 2
    right_edge = _page_right_edge(page_width, words, centers["compliance"])
    header_bottom = max(
        sequence["y1"],
        requirement["y1"],
        observation["y1"],
        compliance["y1"],
    )
    return {
        "header_bottom": header_bottom,
        "sequence": (0.0, seq_req_mid),
        "requirement": (seq_req_mid, req_obs_mid),
        "observation": (req_obs_mid, obs_comp_mid),
        "compliance": (obs_comp_mid, right_edge),
    }


def _report_layout_columns(words: list[dict[str, Any]], page_width: Any) -> dict[str, Any] | None:
    headers = {
        "sequence": _find_header_group(words, "序号"),
        "clause": _find_header_group(words, "标准条款") or _find_header_group(words, "检验项目"),
        "requirement": _find_header_group(words, "标准要求"),
        "result": _find_header_group(words, "检验结果"),
        "conclusion": _find_header_group(words, "单项结论"),
        "remark": _find_header_group(words, "备注"),
    }
    if any(value is None for value in headers.values()):
        return None

    ordered_keys = ["sequence", "clause", "requirement", "result", "conclusion", "remark"]
    centers = [_box_center_x(headers[key]) for key in ordered_keys]  # type: ignore[arg-type]
    if centers != sorted(centers):
        return None

    right_edge = _page_right_edge(page_width, words, centers[-1])
    boundaries = [0.0]
    boundaries.extend((centers[index] + centers[index + 1]) / 2 for index in range(len(centers) - 1))
    boundaries.append(right_edge)
    columns = {
        key: (boundaries[index], boundaries[index + 1])
        for index, key in enumerate(ordered_keys)
    }
    columns["header_bottom"] = max(headers[key]["y1"] for key in ordered_keys)  # type: ignore[index]
    return columns


def _record_compliance_label_positions(
    words: list[dict[str, Any]], columns: dict[str, Any]
) -> dict[str, float]:
    left, right = columns["compliance"]
    labels: dict[str, float] = {}
    for word in words:
        center_x = _word_center_x(word)
        if not (left <= center_x <= right and word["y0"] <= columns["header_bottom"] + 70):
            continue
        text = _normalize_text(word["text"])
        if text in {"符合", "不符合", "不适用"} and text not in labels:
            labels[text] = center_x

    fallback_centers = {
        "符合": left + (right - left) / 6,
        "不符合": left + (right - left) / 2,
        "不适用": left + (right - left) * 5 / 6,
    }
    return {label: labels.get(label, fallback_centers[label]) for label in ["符合", "不符合", "不适用"]}


def _selected_record_judgement(
    page: dict[str, Any],
    words: list[dict[str, Any]],
    row: dict[str, Any],
    columns: dict[str, Any],
    labels: dict[str, float],
) -> str:
    compliance_words = _words_in_column_span(words, columns["compliance"], row["top"], row["bottom"])
    text_selected = _selected_label_from_text(_join_words(compliance_words))
    if text_selected:
        return text_selected

    drawings = _drawings(page)
    boxes = _checkbox_boxes_for_row(words, drawings, columns["compliance"], row["top"], row["bottom"])
    selected: list[tuple[str, int]] = []
    for box in boxes:
        score = _checkbox_selection_score(box, drawings, compliance_words)
        if score <= 0:
            continue
        selected.append((_nearest_label(_rect_center_x(box["rect"]), labels), score))

    selected = sorted(selected, key=lambda item: item[1], reverse=True)
    selected_labels = [label for label, score in selected if score == selected[0][1]] if selected else []
    unique_labels = list(dict.fromkeys(selected_labels))
    if len(unique_labels) == 1:
        return unique_labels[0]
    if "不适用" in unique_labels:
        return "不适用"
    mark_label = _selected_label_from_mark_drawings(drawings, columns["compliance"], row["top"], row["bottom"], labels)
    if mark_label:
        return mark_label
    return ""


def _record_clauses_for_row(
    words: list[dict[str, Any]],
    columns: dict[str, Any],
    row: dict[str, Any],
    sequence_text: str,
) -> list[str]:
    sequence_clauses = extract_clause_numbers(sequence_text)
    if sequence_clauses and _starts_with_clause(sequence_text) and not _looks_like_clause_reference_line(sequence_text):
        return sequence_clauses

    left, right = columns["sequence"]
    heading_right = left + (right - left) * 0.8
    candidates = []
    candidate_words = [
        word
        for word in words
        if columns["header_bottom"] < word["y0"] <= row["bottom"]
        and left <= _word_center_x(word) < right
        and word["x0"] < heading_right
    ]
    for line_words in _word_lines(candidate_words):
        line_text = _join_words(line_words)
        if _looks_like_clause_reference_line(line_text):
            continue
        line_clauses = extract_clause_numbers(line_text)
        if line_clauses:
            candidates.append((min(word["y0"] for word in line_words), line_clauses))
    for _, candidate_clauses in reversed(candidates):
        if candidate_clauses:
            return candidate_clauses

    clauses = extract_clause_numbers(sequence_text) or _clean_top_level_record_clause(sequence_text)
    if clauses:
        return clauses
    return []


def _starts_with_clause(text: str) -> bool:
    return bool(re.match(r"^\s*(?:续\s*)?\d{1,2}(?:\s*[.．。]\s*\d{1,4})+", str(text or "")))


def _clean_top_level_record_clause(text: str) -> list[str]:
    normalized = _normalize_text(str(text or ""))
    if re.fullmatch(r"(?:续)?(?:[4-9]|1[0-7])", normalized):
        return _extract_top_level_clause_numbers(normalized)
    return []


def _looks_like_clause_reference_line(text: str) -> bool:
    normalized = _normalize_text(str(text or ""))
    return normalized.startswith("见") or normalized.endswith("见") or "参见" in normalized


def _selected_label_from_text(text: str) -> str:
    compact = _normalize_text(text)
    for label in ["不适用", "不符合", "符合"]:
        for mark in CHECK_MARK_TOKENS:
            if f"{mark}{label}" in compact or f"{label}{mark}" in compact:
                return label
    return ""


def _checkbox_boxes_for_row(
    words: list[dict[str, Any]],
    drawings: list[dict[str, Any]],
    x_range: tuple[float, float],
    top: float,
    bottom: float,
) -> list[dict[str, Any]]:
    left, right = x_range
    boxes = []
    for word in words:
        if word["text"] not in CHECKBOX_TOKENS:
            continue
        center_x = _word_center_x(word)
        center_y = _word_center_y(word)
        if left <= center_x <= right and top <= center_y < bottom:
            boxes.append({"rect": _word_rect(word), "ops": ["text-checkbox"]})
    if boxes:
        return boxes

    for drawing in drawings:
        rect = drawing.get("rect")
        if not isinstance(rect, dict):
            continue
        center_x = _rect_center_x(rect)
        center_y = _rect_center_y(rect)
        if not (left <= center_x <= right and top <= center_y < bottom):
            continue
        if _is_checkbox_box_drawing(drawing):
            boxes.append(drawing)
    return boxes


def _record_checkbox_row_spans(
    page: dict[str, Any],
    words: list[dict[str, Any]],
    columns: dict[str, Any],
) -> list[dict[str, Any]]:
    left, right = columns["compliance"]
    checkbox_words = [
        word
        for word in words
        if word["text"] in CHECKBOX_TOKENS
        and word["y0"] > columns["header_bottom"]
        and left <= _word_center_x(word) <= right
    ]
    checkbox_items = checkbox_words or [
        {"x0": box["rect"]["x0"], "y0": box["rect"]["y0"], "x1": box["rect"]["x1"], "y1": box["rect"]["y1"], "text": "□"}
        for box in _checkbox_boxes_for_row(words, _drawings(page), columns["compliance"], columns["header_bottom"], page.get("height") or 9999)
    ]

    groups: list[list[dict[str, Any]]] = []
    for item in sorted(checkbox_items, key=lambda value: (_word_center_y(value), value["x0"])):
        center_y = _word_center_y(item)
        if not groups or abs(_word_center_y(groups[-1][0]) - center_y) > 6:
            groups.append([item])
            continue
        groups[-1].append(item)

    horizontal_lines = _horizontal_table_lines(page, min_width=120, y_min=columns["header_bottom"])
    fallback_bottom = float(page.get("height")) if isinstance(page.get("height"), (int, float)) else max(
        word["y1"] for word in words
    )
    rows = []
    for index, group in enumerate(groups, start=1):
        if len(group) < 2:
            continue
        center_y = sum(_word_center_y(word) for word in group) / len(group)
        top = max((line for line in horizontal_lines if line < center_y), default=min(word["y0"] for word in group) - 4)
        bottom = min((line for line in horizontal_lines if line > center_y), default=min(fallback_bottom, max(word["y1"] for word in group) + 18))
        if bottom <= top:
            top = min(word["y0"] for word in group) - 4
            bottom = max(word["y1"] for word in group) + 18
        rows.append({"row_no": str(index), "top": top, "bottom": bottom})
    return rows


def _checkbox_selection_score(
    box: dict[str, Any], drawings: list[dict[str, Any]], words: list[dict[str, Any]]
) -> int:
    box_rect = box["rect"]
    score = 0
    for word in words:
        if word["text"] in CHECK_MARK_TOKENS and _point_in_rect(_word_center_x(word), _word_center_y(word), box_rect, 2):
            score += 3

    for drawing in drawings:
        rect = drawing.get("rect")
        if not isinstance(rect, dict) or _same_rect(rect, box_rect):
            continue
        if not _rect_overlaps(rect, box_rect, padding=2):
            continue
        if abs(_rect_center_y(rect) - _rect_center_y(box_rect)) > max(
            (box_rect["y1"] - box_rect["y0"]) * 1.2,
            8,
        ):
            continue
        if _is_checkbox_box_drawing(drawing) and _rect_area(rect) >= _rect_area(box_rect) * 0.6:
            continue
        if _drawing_has_dark_fill(drawing):
            score += 3
        elif _drawing_ops_for(drawing):
            score += 2
        else:
            score += 1
    return score


def _selected_label_from_mark_drawings(
    drawings: list[dict[str, Any]],
    x_range: tuple[float, float],
    top: float,
    bottom: float,
    labels: dict[str, float],
) -> str:
    left, right = x_range
    scores: dict[str, float] = {}
    for drawing in drawings:
        rect = drawing.get("rect")
        if not isinstance(rect, dict):
            continue
        if _is_checkbox_box_drawing(drawing):
            continue
        if not _is_selection_mark_drawing(drawing):
            continue
        center_x = _rect_center_x(rect)
        if not (left <= center_x <= right):
            continue
        if rect["y1"] < top - 12 or rect["y0"] > bottom + 24:
            continue
        label = _label_for_selection_mark_rect(rect, labels)
        scores[label] = scores.get(label, 0) + max(_rect_area(rect), 1)
    if not scores:
        return ""
    ordered = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    if len(ordered) > 1 and ordered[0][1] == ordered[1][1]:
        return ""
    return ordered[0][0]


def _label_for_selection_mark_rect(rect: dict[str, float], labels: dict[str, float]) -> str:
    covered_labels = [
        label
        for label, center_x in labels.items()
        if rect["x0"] - 2 <= center_x <= rect["x1"] + 2
    ]
    if "不适用" in covered_labels and len(covered_labels) >= 2:
        return "不适用"
    return _nearest_label(_rect_center_x(rect), labels)


def _is_selection_mark_drawing(drawing: dict[str, Any]) -> bool:
    rect = drawing.get("rect")
    if not isinstance(rect, dict):
        return False
    width = rect["x1"] - rect["x0"]
    height = rect["y1"] - rect["y0"]
    if width < 5 or height < 5:
        return False
    return _drawing_has_dark_fill(drawing) or len(_drawing_ops_for(drawing)) >= 4


def _is_checkbox_box_drawing(drawing: dict[str, Any]) -> bool:
    rect = drawing.get("rect")
    if not isinstance(rect, dict):
        return False
    if _drawing_has_dark_fill(drawing):
        return False
    width = rect["x1"] - rect["x0"]
    height = rect["y1"] - rect["y0"]
    if width <= 0 or height <= 0:
        return False
    aspect = width / height
    ops = set(_drawing_ops_for(drawing))
    return 4 <= width <= 30 and 4 <= height <= 30 and 0.65 <= aspect <= 1.55 and "re" in ops


def _drawing_has_dark_fill(drawing: dict[str, Any]) -> bool:
    fill = drawing.get("fill")
    if not isinstance(fill, list) or not fill:
        return False
    return max(fill) < 0.85


def _drawing_ops_for(drawing: dict[str, Any]) -> list[str]:
    ops = drawing.get("ops")
    if isinstance(ops, list):
        return [str(op) for op in ops]
    items = drawing.get("items")
    if not isinstance(items, list):
        return []
    result = []
    for item in items:
        if isinstance(item, dict) and item.get("op"):
            result.append(str(item["op"]))
        elif isinstance(item, (list, tuple)) and item:
            result.append(str(item[0]))
    return result


def _drawing_path_open_distance(drawing: dict[str, Any]) -> float | None:
    start = _coerce_point(drawing.get("path_start"))
    end = _coerce_point(drawing.get("path_end"))
    if start is None or end is None:
        return None
    return ((start["x"] - end["x"]) ** 2 + (start["y"] - end["y"]) ** 2) ** 0.5


def _coerce_point(value: Any) -> dict[str, float] | None:
    if isinstance(value, dict):
        try:
            return {"x": float(value["x"]), "y": float(value["y"])}
        except (KeyError, TypeError, ValueError):
            return None
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        try:
            return {"x": float(value[0]), "y": float(value[1])}
        except (TypeError, ValueError):
            return None
    return None


def _drawings(page: dict[str, Any]) -> list[dict[str, Any]]:
    drawings = []
    for drawing in page.get("drawings", []):
        if not isinstance(drawing, dict):
            continue
        rect = _coerce_rect(drawing.get("rect"))
        if rect is None:
            continue
        copied = dict(drawing)
        copied["rect"] = rect
        drawings.append(copied)
    return drawings


def _horizontal_table_lines(page: dict[str, Any], min_width: float, y_min: float = 0) -> list[float]:
    lines: list[float] = []
    for drawing in _drawings(page):
        rect = drawing["rect"]
        width = rect["x1"] - rect["x0"]
        height = rect["y1"] - rect["y0"]
        if width >= min_width and height <= 1.5 and rect["y0"] >= y_min:
            y = round((rect["y0"] + rect["y1"]) / 2, 1)
            if y not in lines:
                lines.append(y)
    return sorted(lines)


def _layout_row_spans(
    words: list[dict[str, Any]],
    sequence_range: tuple[float, float],
    header_bottom: float,
    page_height: Any,
    min_sequence: int,
    max_sequence: int,
) -> list[dict[str, Any]]:
    left, right = sequence_range
    sequence_words = []
    for word in words:
        if word["y0"] <= header_bottom:
            continue
        if not (left <= _word_center_x(word) < right):
            continue
        if not re.fullmatch(r"\d{1,3}", word["text"]):
            continue
        sequence = int(word["text"])
        if min_sequence <= sequence <= max_sequence:
            sequence_words.append(word)

    fallback_bottom = float(page_height) if isinstance(page_height, (int, float)) else max(word["y1"] for word in words) + 20
    rows = []
    for index, word in enumerate(sequence_words):
        next_top = sequence_words[index + 1]["y0"] if index + 1 < len(sequence_words) else fallback_bottom
        rows.append({"row_no": word["text"], "top": word["y0"] - 2, "bottom": next_top - 1})
    return rows


def _report_page_has_sequence_after_gb9706(page: dict[str, Any]) -> bool:
    words = _layout_words(page)
    if words:
        columns = _report_layout_columns(words, page.get("width"))
        if columns is not None:
            left, right = columns["sequence"]
            for word in words:
                if word["y0"] <= columns["header_bottom"]:
                    continue
                if not (left <= _word_center_x(word) < right):
                    continue
                if re.fullmatch(r"\d{1,3}", word["text"]) and int(word["text"]) > 118:
                    return True
            return False

    for line in _compact_lines(str(page.get("text", ""))):
        match = re.match(r"^(?:续\s*)?(\d{1,3})(?:\s|$)", line)
        if match and int(match.group(1)) > 118:
            return True
    return False


def _find_header_group(words: list[dict[str, Any]], label: str) -> dict[str, Any] | None:
    target = _header_key(label)
    for word in words:
        if _header_key(word["text"]) == target:
            return _word_group_box([word])

    for line_words in _word_lines(words):
        for start in range(len(line_words)):
            selected = []
            text = ""
            for word in line_words[start : start + 6]:
                selected.append(word)
                text += _header_key(word["text"])
                if text == target:
                    return _word_group_box(selected)
                if len(text) > len(target) + 2:
                    break

    for column_words in _nearby_vertical_word_groups(words):
        for start in range(len(column_words)):
            selected = []
            text = ""
            for word in column_words[start : start + 6]:
                selected.append(word)
                text += _header_key(word["text"])
                if text == target:
                    return _word_group_box(selected)
                if len(text) > len(target) + 2:
                    break

    for word in words:
        if target in _header_key(word["text"]):
            return _word_group_box([word])
    return None


def _nearby_vertical_word_groups(words: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    groups: list[list[dict[str, Any]]] = []
    header_words = [word for word in words if word["y0"] < 240]
    for word in sorted(header_words, key=lambda item: (_word_center_x(item), item["y0"])):
        for group in groups:
            if abs(_word_center_x(group[0]) - _word_center_x(word)) <= 8:
                group.append(word)
                group.sort(key=lambda item: item["y0"])
                break
        else:
            groups.append([word])
    return groups


def _word_lines(words: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    lines: list[list[dict[str, Any]]] = []
    for word in sorted(words, key=lambda item: (_word_center_y(item), item["x0"])):
        for line in lines:
            if abs(_word_center_y(line[0]) - _word_center_y(word)) <= 4:
                line.append(word)
                line.sort(key=lambda item: item["x0"])
                break
        else:
            lines.append([word])
    return lines


def _word_group_box(words: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "text": "".join(word["text"] for word in words),
        "x0": min(word["x0"] for word in words),
        "y0": min(word["y0"] for word in words),
        "x1": max(word["x1"] for word in words),
        "y1": max(word["y1"] for word in words),
    }


def _word_rect(word: dict[str, Any]) -> dict[str, float]:
    return {
        "x0": float(word["x0"]),
        "y0": float(word["y0"]),
        "x1": float(word["x1"]),
        "y1": float(word["y1"]),
    }


def _words_in_column_span(
    words: list[dict[str, Any]], x_range: tuple[float, float], top: float, bottom: float
) -> list[dict[str, Any]]:
    left, right = x_range
    selected = []
    for word in words:
        center_x = _word_center_x(word)
        center_y = _word_center_y(word)
        if left <= center_x < right and top <= center_y < bottom:
            selected.append(word)
    return selected


def _layout_words(page: dict[str, Any]) -> list[dict[str, Any]]:
    words = []
    for word in page.get("layout_words", []):
        if not isinstance(word, dict):
            continue
        text = str(word.get("text", "")).strip()
        if not text:
            continue
        try:
            words.append(
                {
                    "text": text,
                    "x0": float(word["x0"]),
                    "y0": float(word["y0"]),
                    "x1": float(word["x1"]),
                    "y1": float(word["y1"]),
                }
            )
        except (KeyError, TypeError, ValueError):
            continue
    return sorted(words, key=lambda item: (item["y0"], item["x0"]))


def _record_entry_matches_report_clauses(entry: dict[str, Any], report_clauses: list[str]) -> bool:
    if not report_clauses:
        return False
    for record_clause in entry.get("clauses", []):
        if any(_clause_matches_prefix(str(record_clause), report_clause) for report_clause in report_clauses):
            return True
    return False


def _clause_matches_prefix(record_clause: str, report_clause: str) -> bool:
    return record_clause == report_clause or record_clause.startswith(f"{report_clause}.")


def _comparison_issues(
    report_clauses: list[str],
    matched_record_entries: list[dict[str, Any]],
    record_judgement: str,
    report_judgement: str,
) -> list[str]:
    issues = []
    if not report_clauses:
        issues.append("report_clause_missing")
    if not matched_record_entries:
        issues.append("record_evidence_missing")
    if record_judgement == MISSING_JUDGEMENT:
        issues.append("record_judgement_missing")
    if report_judgement == MISSING_JUDGEMENT:
        issues.append("report_judgement_missing")
    if not issues and record_judgement != report_judgement:
        issues.append("mismatch")
    return issues


def _missing_mapping_reason(issues: list[str]) -> str:
    reason_map = {
        "report_clause_missing": "报告行未能抽取到标准条款号。",
        "record_evidence_missing": "未找到与报告标准条款前缀匹配的原始记录条款。",
        "record_judgement_missing": "原始记录匹配条款未能识别有效勾选判定。",
        "report_judgement_missing": "报告行未能识别有效单项结论/检验结果判定。",
    }
    return " ".join(reason_map.get(issue, issue) for issue in issues)


def _record_entry_summaries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "page": entry.get("page"),
            "pages": entry.get("pages", []),
            "record_sequence": entry.get("record_sequence"),
            "clauses": entry.get("clauses", []),
            "judgement": entry.get("judgement", ""),
            "inspection_item": entry.get("inspection_item", ""),
            "requirement_text": _excerpt(str(entry.get("requirement_text", "")), 500),
            "observation_text": _excerpt(str(entry.get("observation_text", "")), 300),
            "measured_data": _excerpt(str(entry.get("measured_data", "")), 300),
            "remark": _excerpt(str(entry.get("remark", "")), 200),
            "symbol_judgement": entry.get("symbol_judgement", ""),
        }
        for entry in entries
    ]


def _dedupe_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped = []
    seen = set()
    for entry in entries:
        key = (
            entry.get("page"),
            entry.get("record_sequence"),
            tuple(entry.get("clauses", [])),
            entry.get("judgement"),
            entry.get("requirement_text"),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(entry)
    return deduped


def _dedupe_report_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_sequence: dict[int, dict[str, Any]] = {}
    for row in rows:
        sequence = _positive_int(row.get("sequence"))
        if sequence is None:
            continue
        if sequence not in by_sequence:
            copied = dict(row)
            copied["sequence"] = sequence
            by_sequence[sequence] = copied
            continue

        existing = by_sequence[sequence]
        merged_clauses = _dedupe_list(
            [*existing.get("standard_clauses", []), *row.get("standard_clauses", [])]
        )
        existing["standard_clauses"] = _primary_scope_clauses(merged_clauses) or merged_clauses
        existing["standard_clause"] = "、".join(existing["standard_clauses"])
        for key in ["standard_requirement", "inspection_result", "single_conclusion", "remark", "raw_text"]:
            existing[key] = " ".join(part for part in [existing.get(key, ""), row.get(key, "")] if part).strip()
        existing["report_judgement"] = existing.get("report_judgement") or row.get("report_judgement", "")
    return [by_sequence[key] for key in sorted(by_sequence)]


def _judgement_counts(values: Any) -> dict[str, int]:
    counts = {"符合": 0, "不符合": 0, "不适用": 0, "缺失": 0}
    for value in values:
        judgement = str(value or "") if value in VALID_JUDGEMENTS else MISSING_JUDGEMENT
        counts[judgement] += 1
    return counts


def _last_judgement_token(text: str) -> str:
    tokens = re.split(r"\s+", str(text or "").strip())
    for token in reversed(tokens):
        judgement = normalize_judgement(token)
        if judgement:
            return judgement
    return normalize_judgement(text)


def _looks_like_report_header_line(line: str) -> bool:
    normalized = _normalize_text(line)
    return "序号" in normalized and "标准要求" in normalized


def _join_words(words: list[dict[str, Any]]) -> str:
    return " ".join(word["text"] for word in sorted(words, key=lambda item: (item["y0"], item["x0"]))).strip()


def _nearest_label(x: float, labels: dict[str, float]) -> str:
    return min(labels, key=lambda label: abs(labels[label] - x))


def _word_center_x(word: dict[str, Any]) -> float:
    return (word["x0"] + word["x1"]) / 2


def _word_center_y(word: dict[str, Any]) -> float:
    return (word["y0"] + word["y1"]) / 2


def _box_center_x(box: dict[str, Any]) -> float:
    return (float(box["x0"]) + float(box["x1"])) / 2


def _rect_center_x(rect: dict[str, float]) -> float:
    return (rect["x0"] + rect["x1"]) / 2


def _rect_center_y(rect: dict[str, float]) -> float:
    return (rect["y0"] + rect["y1"]) / 2


def _rect_area(rect: dict[str, float]) -> float:
    return max(rect["x1"] - rect["x0"], 0) * max(rect["y1"] - rect["y0"], 0)


def _point_in_rect(x: float, y: float, rect: dict[str, float], padding: float = 0) -> bool:
    return rect["x0"] - padding <= x <= rect["x1"] + padding and rect["y0"] - padding <= y <= rect["y1"] + padding


def _rect_overlaps(a: dict[str, float], b: dict[str, float], padding: float = 0) -> bool:
    return not (
        a["x1"] < b["x0"] - padding
        or a["x0"] > b["x1"] + padding
        or a["y1"] < b["y0"] - padding
        or a["y0"] > b["y1"] + padding
    )


def _same_rect(a: dict[str, float], b: dict[str, float]) -> bool:
    return all(abs(a[key] - b[key]) <= 0.5 for key in ["x0", "y0", "x1", "y1"])


def _coerce_rect(value: Any) -> dict[str, float] | None:
    if isinstance(value, dict):
        try:
            x0 = float(value["x0"])
            y0 = float(value["y0"])
            x1 = float(value["x1"])
            y1 = float(value["y1"])
        except (KeyError, TypeError, ValueError):
            return None
    elif isinstance(value, (list, tuple)) and len(value) >= 4:
        try:
            x0 = float(value[0])
            y0 = float(value[1])
            x1 = float(value[2])
            y1 = float(value[3])
        except (TypeError, ValueError):
            return None
    else:
        try:
            x0 = float(value.x0)
            y0 = float(value.y0)
            x1 = float(value.x1)
            y1 = float(value.y1)
        except AttributeError:
            return None
    return {
        "x0": min(x0, x1),
        "y0": min(y0, y1),
        "x1": max(x0, x1),
        "y1": max(y0, y1),
    }


def _page_right_edge(page_width: Any, words: list[dict[str, Any]], minimum_center: float) -> float:
    if isinstance(page_width, (int, float)) and page_width > minimum_center:
        return float(page_width)
    return max(max(word["x1"] for word in words) + 20, minimum_center + 80)


def _positive_int(value: Any) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _dedupe_pages(values: Any) -> list[int]:
    pages: list[int] = []
    for value in values:
        page = _positive_int(value)
        if page is not None and page not in pages:
            pages.append(page)
    return pages


def _remove_repeated_clause_prefix(text: str) -> str:
    parts = text.split(".")
    for prefix_len in range(2, len(parts) // 2 + 1):
        if parts[:prefix_len] == parts[prefix_len : prefix_len * 2]:
            return ".".join(parts[prefix_len:])
    return text


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", "", text)


def _header_key(text: str) -> str:
    return re.sub(r"[\s/／、:：.。．,，\-—–_]+", "", str(text or ""))


def _is_not_applicable_marker(text: str) -> bool:
    compact = re.sub(r"\s+", "", str(text or ""))
    if not compact:
        return False
    return all(char in {"/", "／", "-", "—", "–", "－"} for char in compact)


def _compact_lines(text: str) -> list[str]:
    return [re.sub(r"\s+", " ", line).strip() for line in text.splitlines() if line.strip()]


def _dedupe_list(values: list[str]) -> list[str]:
    result = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result


def _excerpt(text: str, limit: int) -> str:
    return re.sub(r"\s+", " ", text).strip()[:limit]
