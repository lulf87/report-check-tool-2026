import re
from typing import Any


PTR_REPORT_CHECK_RULES = [
    "只核对 report 表格的“标准要求”，不核对检验结果/单项结论。",
    "检验结果/单项结论不参与本轮 PTR-report 一致性判断。",
    "≥/≤ 与 >/< 差异按不一致处理，不能视为等价表达。",
    "report 可展开 PTR 引用表格；只要标准要求完整覆盖对应 PTR 条款即可。",
    "report 首页未声明不算缺失；未声明的 PTR 第 2 章条款不应作为问题。",
    "必须按 evidence.leaf_clause_reviews 逐条核对最细条款，并在 details.leaf_clause_comparisons 中逐条说明是否一致。",
    "逐条核对时优先使用 leaf_clause_reviews 中的 ptr_display_text 与 report_display_text。",
]

PTR_REQUIRED_DETAILS = [
    "scope_coverage",
    "ptr_clause_prefix",
    "ptr_clauses",
    "leaf_clause_reviews",
    "leaf_clause_comparisons",
    "report_candidate_pages",
    "scope_decision",
]


class PtrReportEvidenceBuilder:
    def build_all(self, extracted_ptr: dict[str, Any], extracted_report: dict[str, Any]) -> list[dict[str, Any]]:
        report_pages = list(extracted_report.get("pages", []))
        ptr_pages = list(extracted_ptr.get("pages", []))
        report_scope_text = _extract_report_scope_text(report_pages)
        included_clause_selectors = _extract_clause_selectors(report_scope_text)
        included_clause_prefixes = _extract_included_clause_prefixes(included_clause_selectors)
        exclusion_texts = _extract_exclusion_texts(report_scope_text)
        ptr_textless_pages = _extract_textless_pages(ptr_pages)
        ptr_textless_image_paths = _textless_page_image_paths(ptr_textless_pages)
        ptr_clauses = _extract_ptr_chapter_2_clauses(ptr_pages)
        report_clause_entries = _extract_report_clause_entries(report_pages)
        homepage_scope = {
            "report_scope_text": report_scope_text,
            "included_clause_prefixes": included_clause_prefixes,
            "included_clause_selectors": included_clause_selectors,
            "exclusion_texts": exclusion_texts,
        }

        common_evidence = {
            "homepage_scope": homepage_scope,
            "report_scope_text": report_scope_text,
            "included_clause_prefixes": included_clause_prefixes,
            "included_clause_selectors": included_clause_selectors,
            "exclusion_texts": exclusion_texts,
            "ptr_textless_pages": ptr_textless_pages,
            "attached_image_count": len(ptr_textless_image_paths),
        }

        if not report_scope_text or not included_clause_prefixes:
            package = {
                "check_id": "PTR-SCOPE",
                "check_name": "PTR 第 2 章性能指标 vs report 标准要求摘录一致性 - 范围不足",
                "required_details": ["report_scope_text", "included_clause_prefixes", "scope_decision"],
                "check_rules": list(PTR_REPORT_CHECK_RULES),
                "homepage_scope": homepage_scope,
                "evidence": {
                    **common_evidence,
                    "ptr_clause_prefix": "",
                    "ptr_clauses": [],
                    "report_candidate_pages": [],
                    "scope_decision": "insufficient_report_home_scope",
                },
            }
            if ptr_textless_image_paths:
                package["image_paths"] = ptr_textless_image_paths
            return [package]

        selected_ptr_clauses = [
            clause
            for prefix in included_clause_prefixes
            for clause in ptr_clauses
            if _clause_matches_scope(str(clause["prefix"]), prefix, included_clause_selectors)
            and not _matches_any_exclusion(clause, exclusion_texts)
        ]
        selected_ptr_clauses = _dedupe_clauses(selected_ptr_clauses)
        scope_coverage = _build_scope_coverage(
            report_scope_text,
            included_clause_selectors,
            selected_ptr_clauses,
            report_clause_entries,
            exclusion_texts,
        )
        common_evidence["scope_coverage"] = scope_coverage

        packages: list[dict[str, Any]] = []
        for prefix in included_clause_prefixes:
            package_clauses = [
                clause
                for clause in ptr_clauses
                if _clause_matches_scope(str(clause["prefix"]), prefix, included_clause_selectors)
            ]
            package_clauses = [
                clause for clause in package_clauses if not _matches_any_exclusion(clause, exclusion_texts)
            ]
            package = {
                "check_id": f"PTR-{prefix}",
                "check_name": f"PTR 第 2 章性能指标 vs report 标准要求摘录一致性 - {prefix}",
                "required_details": list(PTR_REQUIRED_DETAILS),
                "check_rules": list(PTR_REPORT_CHECK_RULES),
                "homepage_scope": homepage_scope,
                "evidence": {
                    **common_evidence,
                    "ptr_clause_prefix": prefix,
                    "ptr_clauses": package_clauses,
                    "leaf_clause_reviews": _build_leaf_clause_reviews(package_clauses, report_clause_entries),
                    "report_candidate_pages": _extract_report_candidate_pages(
                        report_pages, prefix, package_clauses, included_clause_selectors
                    ),
                    "scope_decision": "included_by_report_home_scope",
                },
            }
            if ptr_textless_image_paths:
                package["image_paths"] = ptr_textless_image_paths
            packages.append(package)
        return packages


def _extract_report_scope_text(report_pages: list[dict[str, Any]]) -> str:
    home_text = ""
    for page in report_pages:
        text = str(page.get("text", ""))
        normalized = _normalize_text(text)
        if "检验报告首页" in normalized:
            home_text = text
            break
    if not home_text and report_pages:
        home_text = str(report_pages[0].get("text", ""))

    lines = _compact_lines(home_text)
    for index, line in enumerate(lines):
        if "检验项目" not in _normalize_text(line):
            continue
        scope_lines = [line]
        for following_line in lines[index + 1 :]:
            if _looks_like_next_home_field(following_line):
                break
            scope_lines.append(following_line)
        return " ".join(scope_lines)
    return ""


def _extract_clause_selectors(scope_text: str) -> list[dict[str, str]]:
    selectors: list[dict[str, str]] = []
    occupied_ranges: list[tuple[int, int]] = []
    range_pattern = re.compile(
        r"(2(?:\.\d+){1,4})\s*(?:~|～|至|到|—|–|-)\s*(2(?:\.\d+){1,4}|\d+(?:\.\d+)*)"
    )
    for match in range_pattern.finditer(scope_text):
        start = match.group(1)
        end = _normalize_range_end(start, match.group(2))
        if end is None:
            continue
        selectors.append({"kind": "range", "start": start, "end": end, "top_level": _top_level_prefix(start)})
        occupied_ranges.append(match.span())

    def is_inside_range(index: int) -> bool:
        return any(start <= index < end for start, end in occupied_ranges)

    for match in re.finditer(r"2(?:\.\d+){1,4}", scope_text):
        if is_inside_range(match.start()):
            continue
        clause = match.group(0)
        selectors.append({"kind": "exact", "start": clause, "end": clause, "top_level": _top_level_prefix(clause)})
    return selectors


def _extract_included_clause_prefixes(selectors: list[dict[str, str]]) -> list[str]:
    prefixes: list[str] = []
    for selector in selectors:
        for prefix in _selector_top_level_prefixes(selector):
            if prefix not in prefixes:
                prefixes.append(prefix)
    return prefixes


def _extract_exclusion_texts(scope_text: str) -> list[str]:
    exclusions: list[str] = []
    for content in re.findall(r"[（(]([^（）()]*?(?:除|不含|不包括|排除)[^（）()]*)[）)]", scope_text):
        text = content.strip()
        if text:
            exclusions.append(text)
    return exclusions


def _extract_textless_pages(ptr_pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    textless_pages: list[dict[str, Any]] = []
    for page in ptr_pages:
        if str(page.get("text", "")).strip():
            continue
        textless_page = {"page": page.get("page")}
        if page.get("image_path"):
            textless_page["image_path"] = page.get("image_path")
        image_crop_paths = list(page.get("image_crop_paths", []))
        if image_crop_paths:
            textless_page["image_crop_paths"] = image_crop_paths
        textless_pages.append(textless_page)
    return textless_pages


def _textless_page_image_paths(textless_pages: list[dict[str, Any]]) -> list[str]:
    image_paths: list[str] = []
    for page in textless_pages:
        if page.get("image_path"):
            image_paths.append(str(page["image_path"]))
        image_paths.extend(str(path) for path in page.get("image_crop_paths", []) if path)
    return image_paths


def _extract_ptr_chapter_2_clauses(ptr_pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    chapter_pages = _ptr_chapter_2_text_pages(ptr_pages)
    joined = "\n".join(
        f"\n__PAGE_{page.get('page')}__\n{page.get('text', '')}" for page in chapter_pages
    )
    heading_pattern = re.compile(r"(?m)^\s*(2(?:\.\d+){1,4})(?:\s+|[.。．、,，]\s*)([^\n]+)")
    matches = list(heading_pattern.finditer(joined))
    clauses: list[dict[str, Any]] = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(joined)
        body = _strip_page_markers(joined[start:end]).strip()
        page = _nearest_page_number(joined[: match.start()])
        title = match.group(2).strip()
        text_parts = [match.group(0).strip()]
        if body:
            text_parts.append(body)
        clauses.append(
            {
                "prefix": match.group(1),
                "title": title,
                "text": "\n".join(text_parts).strip(),
                "page": page,
            }
        )
    return clauses


def _ptr_chapter_2_text_pages(ptr_pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    in_chapter_2 = False
    for page in ptr_pages:
        text = str(page.get("text", ""))
        if not text.strip():
            continue
        if re.search(r"(?m)^\s*2\s*[.。．]?\s*性能指标\b", text):
            in_chapter_2 = True
        next_chapter_pattern = r"(?m)^\s*3\s*[.。．]?\s*(?:检验方法|试验方法|测试方法|术语|检测方法)\b.*$"
        if in_chapter_2 and re.search(next_chapter_pattern, text):
            before_next_chapter = re.split(next_chapter_pattern, text, maxsplit=1)[0]
            if before_next_chapter.strip():
                copied = dict(page)
                copied["text"] = before_next_chapter
                selected.append(copied)
            break
        if in_chapter_2:
            selected.append(page)
    return selected


def _extract_report_candidate_pages(
    report_pages: list[dict[str, Any]],
    prefix: str,
    ptr_clauses: list[dict[str, Any]],
    selectors: list[dict[str, str]],
) -> list[dict[str, Any]]:
    include_parent_prefix = _package_has_top_level_selector(prefix, selectors)
    clause_prefixes = {prefix} if include_parent_prefix else set()
    for clause in ptr_clauses:
        clause_prefix = str(clause.get("prefix", ""))
        if clause_prefix != prefix or include_parent_prefix:
            clause_prefixes.add(clause_prefix)

    candidate_pages: list[dict[str, Any]] = []
    for page in report_pages:
        text = str(page.get("text", ""))
        if not _looks_like_report_inspection_table(text):
            continue
        reference_text = _normalize_clause_reference_text(text)
        if any(
            _contains_clause_reference(
                reference_text,
                clause_prefix,
                allow_descendants=include_parent_prefix and _clause_depth(clause_prefix) == 2,
            )
            for clause_prefix in clause_prefixes
            if clause_prefix
        ):
            text_excerpt = _excerpt(text)
            candidate_pages.append({"page": page.get("page"), "text": text_excerpt, "text_excerpt": text_excerpt})
    return candidate_pages


def _extract_report_clause_entries(report_pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    table_pages = [page for page in report_pages if _looks_like_report_inspection_table(str(page.get("text", "")))]
    joined = "\n".join(f"\n__PAGE_{page.get('page')}__\n{page.get('text', '')}" for page in table_pages)
    matches = list(re.finditer(r"(?<![\d.])2(?:\.\d+){1,4}(?![\d.])", joined))
    entries: list[dict[str, Any]] = []
    for index, match in enumerate(matches):
        segment_start = match.start()
        segment_end = matches[index + 1].start() if index + 1 < len(matches) else len(joined)
        segment = joined[segment_start:segment_end]
        text = _strip_page_markers(segment).strip()
        if not text:
            continue
        entries.append(
            {
                "prefix": match.group(0),
                "pages": _page_numbers_for_segment(joined, segment_start, segment),
                "text": _excerpt(text, 3500),
                "text_excerpt": _excerpt(text, 1200),
            }
        )
    return entries


def _build_scope_coverage(
    report_scope_text: str,
    selectors: list[dict[str, str]],
    selected_ptr_clauses: list[dict[str, Any]],
    report_clause_entries: list[dict[str, Any]],
    exclusion_texts: list[str],
) -> dict[str, Any]:
    declared_clause_prefixes = _declared_clause_prefixes(selectors, selected_ptr_clauses)
    actual_report_clause_prefixes = _dedupe([str(entry.get("prefix", "")) for entry in report_clause_entries])
    missing_declared_clause_prefixes = [
        prefix for prefix in declared_clause_prefixes if not _declared_prefix_is_covered(prefix, actual_report_clause_prefixes)
    ]
    extra_report_clause_prefixes = [
        prefix for prefix in actual_report_clause_prefixes if not _actual_prefix_is_declared(prefix, declared_clause_prefixes)
    ]
    return {
        "report_scope_text": report_scope_text,
        "declared_selectors": selectors,
        "declared_clause_prefixes": declared_clause_prefixes,
        "actual_report_clause_prefixes": actual_report_clause_prefixes,
        "missing_declared_clause_prefixes": missing_declared_clause_prefixes,
        "extra_report_clause_prefixes": extra_report_clause_prefixes,
        "exclusion_texts": exclusion_texts,
        "declared_clause_count": len(declared_clause_prefixes),
        "actual_report_clause_count": len(actual_report_clause_prefixes),
    }


def _build_leaf_clause_reviews(
    ptr_clauses: list[dict[str, Any]],
    report_clause_entries: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    entries_by_prefix: dict[str, list[dict[str, Any]]] = {}
    for entry in report_clause_entries:
        entries_by_prefix.setdefault(str(entry.get("prefix", "")), []).append(entry)

    reviews = []
    for clause in _leaf_clauses(ptr_clauses):
        prefix = str(clause.get("prefix", ""))
        entries = entries_by_prefix.get(prefix, [])
        pages = _dedupe_pages(page for entry in entries for page in entry.get("pages", []) if page)
        ptr_reference_context_text = _parent_context_text(prefix, ptr_clauses)
        ptr_referenced_requirement_text = _referenced_context_excerpt(prefix, clause, ptr_clauses)
        report_standard_requirement_text = "\n".join(str(entry.get("text", "")) for entry in entries).strip()
        reviews.append(
            {
                "prefix": prefix,
                "parent_prefix": _top_level_prefix(prefix),
                "title": clause.get("title", ""),
                "ptr_page": clause.get("page"),
                "ptr_requirement_text": clause.get("text", ""),
                "ptr_reference_context_text": ptr_reference_context_text,
                "ptr_referenced_requirement_text": ptr_referenced_requirement_text,
                "ptr_display_text": _build_ptr_display_text(clause, ptr_referenced_requirement_text),
                "report_presence": "present" if entries else "missing",
                "report_entry_pages": pages,
                "report_standard_requirement_text": report_standard_requirement_text,
                "report_display_text": report_standard_requirement_text,
                "comparison_instruction": "核对 report 标准要求是否完整、一致覆盖 PTR 条款及其引用表格/上下文。",
            }
        )
    return reviews


def _declared_clause_prefixes(selectors: list[dict[str, str]], selected_ptr_clauses: list[dict[str, Any]]) -> list[str]:
    prefixes: list[str] = []
    for selector in selectors:
        start = selector["start"]
        end = selector["end"]
        if selector["kind"] == "exact" and _clause_depth(start) == 2:
            prefixes.append(start)
            continue
        if selector["kind"] == "range" and _clause_depth(start) == 2 and _clause_depth(end) == 2:
            prefixes.extend(_selector_top_level_prefixes(selector))
            continue
        for clause in selected_ptr_clauses:
            prefix = str(clause.get("prefix", ""))
            if _selector_matches_clause(selector, prefix) and _clause_depth(prefix) >= 3:
                prefixes.append(prefix)
    return _dedupe(prefixes)


def _declared_prefix_is_covered(declared_prefix: str, actual_prefixes: list[str]) -> bool:
    if _clause_depth(declared_prefix) == 2:
        return any(_is_clause_in_prefix(actual_prefix, declared_prefix) for actual_prefix in actual_prefixes)
    return declared_prefix in actual_prefixes


def _actual_prefix_is_declared(actual_prefix: str, declared_prefixes: list[str]) -> bool:
    return any(
        actual_prefix == declared_prefix
        or (_clause_depth(declared_prefix) == 2 and _is_clause_in_prefix(actual_prefix, declared_prefix))
        for declared_prefix in declared_prefixes
    )


def _leaf_clauses(clauses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    prefixes = [str(clause.get("prefix", "")) for clause in clauses]
    return [
        clause
        for clause in clauses
        if not any(other != str(clause.get("prefix", "")) and other.startswith(f"{clause.get('prefix')}.") for other in prefixes)
    ]


def _parent_context_text(prefix: str, clauses: list[dict[str, Any]]) -> str:
    parent_prefix = _top_level_prefix(prefix)
    if parent_prefix == prefix:
        return ""
    for clause in clauses:
        if str(clause.get("prefix", "")) == parent_prefix:
            return _excerpt(str(clause.get("text", "")), 5000)
    return ""


def _build_ptr_display_text(clause: dict[str, Any], referenced_text: str) -> str:
    parts = [_primary_clause_sentence(str(clause.get("text", "")))]
    if referenced_text:
        parts.append(f"表 1 对应内容：{referenced_text}")
    return "\n".join(part for part in parts if part).strip()


def _primary_clause_sentence(text: str) -> str:
    for line in _compact_lines(text):
        if line:
            return line
    return _excerpt(text, 500)


def _referenced_context_excerpt(prefix: str, clause: dict[str, Any], clauses: list[dict[str, Any]]) -> str:
    parent_text = _parent_context_text(prefix, clauses)
    if not parent_text:
        return ""
    token, start = _find_first_title_token(parent_text, str(clause.get("title", "")))
    if not token or start < 0:
        return ""
    sibling_tokens = [
        token
        for other in _leaf_clauses(clauses)
        for token in _title_match_tokens(str(other.get("title", "")))
        if str(other.get("prefix", "")) != prefix and _top_level_prefix(str(other.get("prefix", ""))) == _top_level_prefix(prefix)
    ]
    end_positions = [_find_token(parent_text[start + len(token) :], sibling) for sibling in sibling_tokens if sibling]
    end_positions = [start + len(token) + position for position in end_positions if position >= 0]
    stop_positions = [_find_token(parent_text[start + len(token) :], stop) for stop in ["注释", "符号“/”代表不适用"]]
    end_positions.extend(start + len(token) + position for position in stop_positions if position >= 0)
    end = min(end_positions) if end_positions else min(len(parent_text), start + 1600)
    return _strip_trailing_page_number(_excerpt(parent_text[start:end], 1600))


def _find_first_title_token(text: str, title: str) -> tuple[str, int]:
    for token in _title_match_tokens(title):
        position = _find_token(text, token)
        if position >= 0:
            return token, position
    return "", -1


def _title_match_tokens(title: str) -> list[str]:
    heading = re.split(r"[:：]", title, maxsplit=1)[0]
    parenthetical_tokens = re.findall(r"[（(]([^（）()]+)[）)]", heading)
    base = re.sub(r"[（(][^（）()]*[）)]", "", heading)
    base = re.sub(r"[①②③④⑤⑥⑦⑧⑨⑩]", "", base)
    base = _normalize_text(base)
    tokens: list[str] = []
    for token in parenthetical_tokens:
        normalized_token = _normalize_text(token)
        if _looks_like_acronym_token(normalized_token):
            tokens.append(normalized_token)
    if "/" in base:
        tokens.append(base.split("/")[0])
    tokens.append(base)
    if "感知后" in base and "感知后的" not in base:
        tokens.append(base.replace("感知后", "感知后的", 1))
    if "不应期" in base:
        tokens.extend(["心房不应期", "右室不应期", "不应期"])
    return _dedupe([token for token in tokens if token])


def _looks_like_acronym_token(token: str) -> bool:
    if token in {"V", "mV", "ms", "bpm", "ppm", "KΩ", "Ω"}:
        return False
    return len(re.findall(r"[A-Z]", token)) >= 2


def _strip_trailing_page_number(text: str) -> str:
    return re.sub(r"\s+[1-9]\s*$", "", text).strip()


def _find_token(text: str, token: str) -> int:
    if not token:
        return -1
    compact_text = _normalize_text(text)
    compact_index = compact_text.find(_normalize_text(token))
    if compact_index < 0:
        return -1
    compact_seen = 0
    for index, char in enumerate(text):
        if char.isspace():
            continue
        if compact_seen == compact_index:
            return index
        compact_seen += 1
    return -1


def _package_has_top_level_selector(prefix: str, selectors: list[dict[str, str]]) -> bool:
    for selector in selectors:
        if prefix not in _selector_top_level_prefixes(selector):
            continue
        start = selector["start"]
        end = selector["end"]
        if _clause_depth(start) == 2 and _clause_depth(end) == 2:
            return True
        if selector["kind"] == "exact" and start == prefix:
            return True
    return False


def _contains_clause_reference(normalized_text: str, clause_prefix: str, allow_descendants: bool = False) -> bool:
    suffix = r"(?:\.\d+)*" if allow_descendants else ""
    pattern = rf"(?<![\d.]){re.escape(clause_prefix)}{suffix}(?![\d.])"
    return re.search(pattern, normalized_text) is not None


def _looks_like_report_inspection_table(text: str) -> bool:
    normalized = _normalize_text(text)
    return "检验项目" in normalized and "标准要求" in normalized


def _looks_like_next_home_field(line: str) -> bool:
    normalized = _normalize_text(line)
    next_field_markers = [
        "检验依据",
        "样品名称",
        "型号规格",
        "委托单位",
        "生产单位",
        "受检单位",
        "报告编号",
    ]
    return any(normalized.startswith(marker) for marker in next_field_markers)


def _matches_any_exclusion(clause: dict[str, Any], exclusion_texts: list[str]) -> bool:
    if not exclusion_texts:
        return False
    clause_text = _normalize_text(f"{clause.get('title', '')}\n{clause.get('text', '')}")
    for exclusion_text in exclusion_texts:
        for token in _exclusion_tokens(exclusion_text):
            if token and token in clause_text:
                return True
    return False


def _clause_matches_scope(
    clause_prefix: str, package_prefix: str, selectors: list[dict[str, str]]
) -> bool:
    if clause_prefix == package_prefix:
        return any(package_prefix in _selector_top_level_prefixes(selector) for selector in selectors)
    for selector in selectors:
        if package_prefix not in _selector_top_level_prefixes(selector):
            continue
        if _top_level_prefix(clause_prefix) != package_prefix:
            continue
        if _selector_matches_clause(selector, clause_prefix):
            return True
    return False


def _selector_matches_clause(selector: dict[str, str], clause_prefix: str) -> bool:
    kind = selector["kind"]
    start = selector["start"]
    end = selector["end"]
    if kind == "exact":
        if _clause_depth(start) == 2:
            return _is_clause_in_prefix(clause_prefix, start)
        return clause_prefix == start

    if _clause_depth(start) == 2 and _clause_depth(end) == 2:
        clause_top = _top_level_prefix(clause_prefix)
        return _top_level_index(start) <= _top_level_index(clause_top) <= _top_level_index(end)

    if _top_level_prefix(clause_prefix) != _top_level_prefix(start):
        return False
    if _clause_depth(clause_prefix) < 3:
        return False
    child_index = _child_index(clause_prefix)
    return _child_index(start) <= child_index <= _child_index(end)


def _selector_top_level_prefixes(selector: dict[str, str]) -> list[str]:
    start = selector["start"]
    end = selector["end"]
    if selector["kind"] == "range" and _clause_depth(start) == 2 and _clause_depth(end) == 2:
        start_index = _top_level_index(start)
        end_index = _top_level_index(end)
        if start_index <= end_index:
            return [f"2.{number}" for number in range(start_index, end_index + 1)]
    return [_top_level_prefix(start)]


def _normalize_range_end(start: str, raw_end: str) -> str | None:
    if raw_end.startswith("2."):
        return raw_end
    start_parts = start.split(".")
    end_parts = raw_end.split(".")
    if len(end_parts) == 1 and len(start_parts) >= 2:
        return ".".join([*start_parts[:-1], raw_end])
    if len(end_parts) == 2 and start_parts[0] == "2":
        return f"2.{raw_end}"
    return None


def _clause_depth(prefix: str) -> int:
    return len(prefix.split("."))


def _top_level_index(prefix: str) -> int:
    return int(prefix.split(".")[1])


def _child_index(prefix: str) -> int:
    parts = prefix.split(".")
    return int(parts[2]) if len(parts) >= 3 else 0


def _exclusion_tokens(exclusion_text: str) -> list[str]:
    text = re.sub(r"^(除|不含|不包括|排除)", "", _normalize_text(exclusion_text))
    tokens: list[str] = []
    for token in re.split(r"[、,，;；/和及]+", text):
        if not token:
            continue
        tokens.append(token)
        if token.endswith("性") and len(token) > 2:
            tokens.append(token[:-1])
    return tokens


def _is_clause_in_prefix(clause_prefix: str, prefix: str) -> bool:
    return clause_prefix == prefix or clause_prefix.startswith(f"{prefix}.")


def _top_level_prefix(prefix: str) -> str:
    parts = prefix.split(".")
    return ".".join(parts[:2])


def _nearest_page_number(text_before_match: str) -> Any:
    page_markers = re.findall(r"__PAGE_(\d+)__", text_before_match)
    if not page_markers:
        return None
    return int(page_markers[-1])


def _page_numbers_for_segment(joined_text: str, segment_start: int, segment: str) -> list[int]:
    pages = []
    nearest_page = _nearest_page_number(joined_text[:segment_start])
    if nearest_page is not None:
        pages.append(nearest_page)
    pages.extend(int(page) for page in re.findall(r"__PAGE_(\d+)__", segment))
    return _dedupe_pages(pages)


def _strip_page_markers(text: str) -> str:
    return re.sub(r"\n?__PAGE_\d+__\n?", "\n", text)


def _compact_lines(text: str) -> list[str]:
    return [re.sub(r"\s+", " ", line).strip() for line in text.splitlines() if line.strip()]


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", "", text)


def _normalize_clause_reference_text(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def _dedupe(items: list[str]) -> list[str]:
    deduped: list[str] = []
    for item in items:
        if item and item not in deduped:
            deduped.append(item)
    return deduped


def _dedupe_pages(items: Any) -> list[int]:
    deduped: list[int] = []
    for item in items:
        try:
            page = int(item)
        except (TypeError, ValueError):
            continue
        if page not in deduped:
            deduped.append(page)
    return deduped


def _dedupe_clauses(clauses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for clause in clauses:
        prefix = str(clause.get("prefix", ""))
        if not prefix or prefix in seen:
            continue
        seen.add(prefix)
        deduped.append(clause)
    return deduped


def _excerpt(text: str, limit: int = 1200) -> str:
    return re.sub(r"\s+", " ", text).strip()[:limit]
