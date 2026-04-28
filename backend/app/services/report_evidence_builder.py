import copy
import re
from typing import Any


APPROVED_CHECK_IDS = [
    "C00",
    "C01",
    "C02",
    "C03",
    "C04",
    "C06",
    "C07",
    "C08",
    "C12",
    "C13",
    "C14",
    "C15",
    "C16",
]


CHECK_NAMES = {
    "C00": "文档结构完整性",
    "C01": "报告编号与样品编号一致性",
    "C02": "首页基础字段一致性",
    "C03": "首页扩展字段一致性",
    "C04": "时间逻辑一致性",
    "C06": "样品描述字段一致性",
    "C07": "照片覆盖性",
    "C08": "样品描述与照片标签一致性",
    "C12": "检验结果与单项结论逻辑",
    "C13": "单项结论与总结论逻辑",
    "C14": "非空字段核对",
    "C15": "序号连续性与续表正确性",
    "C16": "页码连续性",
}


IMAGE_EVIDENCE_CHECK_IDS = {"C03", "C06", "C08"}


REQUIRED_DETAILS = {
    "C00": ["detected_sections", "missing_sections", "section_order_ok"],
    "C01": ["report_number", "sample_number", "tail_match"],
    "C02": ["field_comparisons"],
    "C03": ["field_comparisons", "see_sample_desc_consistent"],
    "C04": ["dates", "timeline_checks"],
    "C06": ["rows"],
    "C07": ["components"],
    "C08": ["sample_items", "label_items", "label_comparisons"],
    "C12": ["sequence_results"],
    "C13": ["overall_conclusion_text", "nonconforming_sequences", "overall_consistent"],
    "C14": ["rows", "empty_field_rows"],
    "C15": ["sequence_list", "missing_numbers", "duplicate_numbers", "continuation_marker_findings"],
    "C16": ["page_infos", "missing_pages", "duplicate_pages", "total_consistent", "final_page_match"],
}


CHECK_RULES = {
    "C04": [
        "只核对到样日期、检验日期等样品接收与检验流程时间逻辑。",
        "不要核对签发日期，也不要因为签发日期与检验日期之间的关系给出问题。",
    ],
    "C12": [
        "核对检验结果与单项结论的语义一致性，业务判断仍由 Codex 根据上下文完成。",
        "在“无菌”或“应无菌”等无菌检查项目语境下，检验结果写“无菌生长”应理解为未见菌生长/无菌结果，可作为单项结论“符合”的符合证据；不要仅因字面误读判 warning。",
        "不要将该规则泛化到“有菌生长”、检出微生物、阳性等明显阳性结果；这些仍应结合上下文按不符合或疑点处理。",
    ],
    "C14": [
        "C14 只检查检验结果表中的“检验结果、单项结论、备注”三类结果值列是否非空；不检查检验项目名称、技术要求、首页或签字栏。",
        "不检查签发日期、批准、审核、检验日期、检验人员姓名、首页字段；这些均为 out of scope，不能作为 finding，也不能据此判 error/warning。",
        "必须优先审阅 evidence.candidate_empty_field_rows；这些只是候选证据，不是最终结论。若候选确认为检验结果表行缺少单项结论或备注，应按 C14 范围给出 finding。",
        "如果 evidence.candidate_empty_field_rows 的 reason 标明由版式词坐标确认某列未见内容，应优先按该候选判断相应列为空。",
        "只判断上述范围内需要填写的字段是否非空，不判断字段内容是否正确。",
        "检验结果表中的“备注”列填“/”属于正常空白标记，不应作为问题。",
        "备注列只要存在任何数字、字符、汉字或“/”，都应视为非空；只有完全空白才算空字段。",
    ],
    "C15": [
        "必须优先审阅 evidence.continuation_marker_candidates。",
        "如果某序号是首次出现，序号栏不应写“续”；如果同一序号已在前文出现，后续页或后续片段再次出现时应写“续+序号”。",
        "若 evidence.continuation_marker_candidates 已列出 missing_continuation_marker 或 unexpected_continuation_marker，应据此给出 finding。",
    ],
    "C08": [
        "从样品描述中的“被检样品包括”表提取样品名称、型号、批号/序列号。",
        "从照片页中的标签样张文字和已附加的照片页图像识别标签上的样品名称、型号、批号/序列号。",
        "证据包中的 sample_items、label_items、candidate_match_hints 只是候选证据，不是最终匹配结论。",
        "必须在 details.label_comparisons 中逐项列出样品描述值、标签值、页码、是否一致和判断说明。",
        "逐项核对样品描述与对应标签样张是否一致；名称允许合理换行或空格差异，但型号、批号/序列号必须一致。",
        "如果照片页只有外观照片而没有标签样张，不要直接判为错误；应列为证据不足并说明缺少哪一项标签证据。",
        "只核对被检样品本身，不核对“型号规格或其他说明”中的配合使用设备。",
    ],
}


class ReportEvidenceBuilder:
    def build_all(self, extracted_report: dict[str, Any]) -> list[dict[str, Any]]:
        return [self.build_one(check_id, extracted_report) for check_id in APPROVED_CHECK_IDS]

    def build_one(self, check_id: str, extracted_report: dict[str, Any]) -> dict[str, Any]:
        raw_pages = copy.deepcopy(extracted_report.get("pages", []))
        pages = [_public_page_snapshot(page) for page in raw_pages]
        sample_description_text = self._first_text_containing(pages, "样品描述")
        photo_pages = self._photo_pages(pages)
        label_photo_pages = self._label_photo_pages(pages)
        evidence = {
            "file_name": extracted_report.get("file_name", ""),
            "pages": pages,
            "cover_text": self._page_text(pages, 1),
            "report_home_text": self._first_text_containing(pages, "检验报告首页"),
            "sample_description_text": sample_description_text,
            "inspection_table_text": self._first_inspection_table_text(pages),
            "photo_text": self._first_photo_page_text(pages),
            "photo_pages": photo_pages,
            "label_photo_pages": label_photo_pages,
        }
        image_paths = _image_paths(label_photo_pages) or _image_paths(photo_pages)

        if check_id == "C08":
            sample_items = _extract_sample_items(sample_description_text)
            label_items = _extract_label_items(pages, label_photo_pages)
            evidence["sample_items"] = sample_items
            evidence["label_items"] = label_items
            evidence["candidate_match_hints"] = _build_candidate_match_hints(sample_items, label_items)

        if check_id == "C14":
            evidence["candidate_empty_field_rows"] = _extract_c14_candidate_empty_field_rows(raw_pages)

        if check_id == "C15":
            sequence_markers = _extract_c15_sequence_markers(raw_pages)
            evidence["sequence_markers"] = sequence_markers
            evidence["continuation_marker_candidates"] = _extract_c15_continuation_marker_candidates(
                sequence_markers
            )

        if check_id in IMAGE_EVIDENCE_CHECK_IDS:
            evidence["attached_image_count"] = len(image_paths)

        package = {
            "check_id": check_id,
            "check_name": CHECK_NAMES[check_id],
            "required_details": list(REQUIRED_DETAILS[check_id]),
            "check_rules": list(CHECK_RULES.get(check_id, [])),
            "evidence": evidence,
        }
        if check_id in IMAGE_EVIDENCE_CHECK_IDS and image_paths:
            package["image_paths"] = image_paths
        return package

    def _page_text(self, pages: list[dict[str, Any]], page_number: int) -> str:
        for page in pages:
            if page.get("page") == page_number:
                return str(page.get("text", ""))
        return ""

    def _first_text_containing(self, pages: list[dict[str, Any]], marker: str) -> str:
        normalized_marker = _normalize_text(marker)
        for page in pages:
            text = str(page.get("text", ""))
            if normalized_marker in _normalize_text(text):
                return text
        return ""

    def _first_text_containing_any(self, pages: list[dict[str, Any]], markers: list[str]) -> str:
        normalized_markers = [_normalize_text(marker) for marker in markers]
        for page in pages:
            text = str(page.get("text", ""))
            normalized_text = _normalize_text(text)
            if any(marker in normalized_text for marker in normalized_markers):
                return text
        return ""

    def _first_photo_page_text(self, pages: list[dict[str, Any]]) -> str:
        for page in pages:
            if _is_photo_page(page):
                return str(page.get("text", ""))
        return ""

    def _first_inspection_table_text(self, pages: list[dict[str, Any]]) -> str:
        for page in pages:
            text = str(page.get("text", ""))
            normalized_text = _normalize_text(text)
            if "序号" in normalized_text and "检验项目" in normalized_text and "单项结论" in normalized_text:
                return text
        return self._first_text_containing(pages, "检验项目")

    def _photo_pages(self, pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [_page_excerpt(page) for page in pages if _is_photo_page(page)]

    def _label_photo_pages(self, pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [_page_excerpt(page) for page in pages if _is_photo_page(page) and "标签" in str(page.get("text", ""))]


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", "", text)


def _public_page_snapshot(page: dict[str, Any]) -> dict[str, Any]:
    snapshot = copy.deepcopy(page)
    snapshot.pop("layout_words", None)
    snapshot.pop("drawings", None)
    return snapshot


def _is_photo_page(page: dict[str, Any]) -> bool:
    text = str(page.get("text", ""))
    normalized = _normalize_text(text)
    return "检验报告照片页" in normalized or "照片和说明" in normalized


def _page_excerpt(page: dict[str, Any]) -> dict[str, Any]:
    text = re.sub(r"\s+", " ", str(page.get("text", ""))).strip()
    return {
        "page": page.get("page"),
        "text": text[:1200],
        "image_path": page.get("image_path"),
        "image_crop_paths": list(page.get("image_crop_paths", [])),
    }


def _image_paths(pages: list[dict[str, Any]]) -> list[str]:
    image_paths: list[str] = []
    for page in pages:
        if page.get("image_path"):
            image_paths.append(str(page["image_path"]))
        image_paths.extend(str(path) for path in page.get("image_crop_paths", []) if path)
    return image_paths


def _extract_sample_items(sample_description_text: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    header = _find_sample_table_header(sample_description_text)
    split_cell_items = _extract_split_cell_sample_items(sample_description_text, header)
    if split_cell_items:
        return split_cell_items

    for line in _compact_lines(sample_description_text):
        match = re.match(r"^(\d+)\s+(.+)$", line)
        if not match:
            continue

        fields = _split_sample_row(match.group(2), header)
        if not fields:
            continue

        row_number = match.group(1)
        item = {
            "row_number": row_number,
            "component_name": fields.get("component_name", ""),
            "model": fields.get("model", ""),
            "batch_or_serial": fields.get("batch_or_serial", ""),
            "production_date": fields.get("production_date", ""),
            "raw_text": line,
            "source_fields": header,
        }
        items.append(item)
    return items


def _find_sample_table_header(text: str) -> dict[str, str]:
    lines = _compact_lines(text)
    for index, line in enumerate(lines):
        current = _normalize_text(line)
        if not (current == "序号" or current.startswith("序号")):
            continue

        normalized = _normalize_text(" ".join(lines[index : index + 8]))
        name_field = "部件名称" if "部件名称" in normalized else "样品名称" if "样品名称" in normalized else "名称"
        model_field = (
            "型号规格"
            if "型号规格" in normalized
            else "型号/规格"
            if "型号/规格" in normalized
            else "组件号"
            if "组件号" in normalized
            else "型号"
        )
        batch_field = (
            "批号/序列号"
            if "批号/序列号" in normalized
            else "序列号/批号"
            if "序列号/批号" in normalized
            else "产品编号/批号"
            if "产品编号/批号" in normalized
            else "批号或序列号"
        )
        return {
            "component_name": name_field,
            "model": model_field,
            "batch_or_serial": batch_field,
            "production_date": "生产日期",
        }
    return {
        "component_name": "部件名称/样品名称",
        "model": "型号规格/组件号",
        "batch_or_serial": "批号/序列号",
        "production_date": "生产日期",
    }


def _split_sample_row(row_body: str, header: dict[str, str]) -> dict[str, str] | None:
    return _split_sample_tokens(row_body.split(), header)


def _extract_split_cell_sample_items(sample_description_text: str, header: dict[str, str]) -> list[dict[str, Any]]:
    lines = _compact_lines(sample_description_text)
    data_start = _find_split_cell_table_data_start(lines)
    if data_start is None:
        return []

    items: list[dict[str, Any]] = []
    row_number = ""
    tokens: list[str] = []

    def append_current() -> None:
        if not row_number or not tokens:
            return
        fields = _split_sample_tokens(tokens, header)
        if fields is None:
            return
        items.append(
            {
                "row_number": row_number,
                "component_name": fields.get("component_name", ""),
                "model": fields.get("model", ""),
                "batch_or_serial": fields.get("batch_or_serial", ""),
                "production_date": fields.get("production_date", ""),
                "raw_text": f"{row_number} {' '.join(tokens)}",
                "source_fields": header,
            }
        )

    for line in lines[data_start:]:
        normalized = _normalize_text(line)
        if _is_sample_table_stop_line(normalized):
            append_current()
            break

        if _is_sample_row_number(line):
            append_current()
            row_number = line
            tokens = []
            continue

        if row_number:
            tokens.append(line)

    else:
        append_current()

    return items


def _find_split_cell_table_data_start(lines: list[str]) -> int | None:
    for index, line in enumerate(lines):
        normalized = _normalize_text(line)
        if normalized != "序号":
            continue

        header_window = _normalize_text(" ".join(lines[index : index + 8]))
        if "生产日期" not in header_window or not ("批号" in header_window or "序列号" in header_window):
            continue

        for data_index in range(index + 1, len(lines)):
            if _is_sample_row_number(lines[data_index]):
                return data_index
    return None


def _is_sample_row_number(text: str) -> bool:
    return bool(re.fullmatch(r"\d{1,3}", text))


def _is_sample_table_stop_line(normalized_line: str) -> bool:
    return normalized_line.startswith("以上详见") or normalized_line.startswith("型号规格或其他说明")


def _split_sample_tokens(tokens: list[str], header: dict[str, str]) -> dict[str, str] | None:
    tokens = list(tokens)
    if len(tokens) < 3:
        return None

    production_date = ""
    if tokens and _looks_like_date(tokens[-1]):
        production_date = tokens.pop()

    if len(tokens) < 3:
        return None

    batch_or_serial = tokens.pop()
    model = tokens.pop()
    component_name = "".join(tokens).strip()
    if not component_name:
        return None

    return {
        "component_name": component_name,
        "model": model,
        "batch_or_serial": batch_or_serial,
        "production_date": production_date,
        "component_source_field": header.get("component_name", ""),
        "model_source_field": header.get("model", ""),
        "batch_source_field": header.get("batch_or_serial", ""),
    }


def _extract_label_items(all_pages: list[dict[str, Any]], label_photo_pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    label_page_numbers = {page.get("page") for page in label_photo_pages}
    items = []
    for page in all_pages:
        if page.get("page") not in label_page_numbers:
            continue

        text = str(page.get("text", ""))
        items.append(
            {
                "page": page.get("page"),
                "caption": _extract_label_caption(text),
                "raw_text": _excerpt_text(text, 1200),
                "fields": _extract_label_fields(text),
                "has_attached_image": bool(page.get("image_path")),
            }
        )
    return items


def _extract_label_caption(text: str) -> str:
    captions = [line for line in _compact_lines(text) if "标签" in line and ("№" in line or "No" in line)]
    if captions:
        return captions[0]
    for line in _compact_lines(text):
        if "标签" in line:
            return line
    return ""


def _extract_label_fields(text: str) -> dict[str, str]:
    field_names = [
        "产品名称",
        "样品名称",
        "部件名称",
        "型号规格",
        "规格型号",
        "型号/规格",
        "型号",
        "产品编号/批号",
        "批号/序列号",
        "序列号/批号",
        "批号",
        "序列号",
        "生产日期",
        "失效日期",
    ]
    field_pattern = "|".join(re.escape(name) for name in field_names)
    pattern = re.compile(
        rf"({field_pattern})\s*[:：]\s*(.*?)(?=(?:\s*(?:{field_pattern})\s*[:：])|$)",
        flags=re.S,
    )
    fields: dict[str, str] = {}
    for match in pattern.finditer(text):
        label = match.group(1)
        value = _excerpt_text(match.group(2), 240)
        if value:
            fields[label] = value
    return fields


def _build_candidate_match_hints(
    sample_items: list[dict[str, Any]], label_items: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    hints = []
    for item in sample_items:
        tokens = [
            str(item.get("component_name", "")),
            str(item.get("model", "")),
            str(item.get("batch_or_serial", "")),
        ]
        normalized_tokens = [_normalize_text(token) for token in tokens if token]
        candidate_pages = []
        for label_item in label_items:
            haystack = _normalize_text(
                " ".join(
                    [
                        str(label_item.get("caption", "")),
                        str(label_item.get("raw_text", "")),
                        " ".join(str(value) for value in dict(label_item.get("fields", {})).values()),
                    ]
                )
            )
            if any(token and token in haystack for token in normalized_tokens):
                page = label_item.get("page")
                if isinstance(page, int):
                    candidate_pages.append(page)

        hints.append(
            {
                "sample_item_index": item.get("row_number"),
                "sample_component_name": item.get("component_name", ""),
                "sample_model": item.get("model", ""),
                "sample_batch_or_serial": item.get("batch_or_serial", ""),
                "label_candidate_pages": sorted(set(candidate_pages)),
                "reason": "候选页文字包含样品描述中的名称、型号或批号/序列号；最终一致性由 Codex 判断。",
            }
        )
    return hints


def _extract_c14_candidate_empty_field_rows(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for page in pages:
        text = str(page.get("text", ""))
        if not _is_c14_inspection_result_table_text(text):
            continue

        candidates.extend(_extract_c14_layout_empty_field_rows(page))
        lines = _compact_lines(text)
        for result_index, line in enumerate(lines):
            if not _looks_like_c14_result_value(line):
                continue
            if _has_c14_conclusion_or_remark_evidence([line]):
                continue

            following_lines = _c14_lines_before_next_row_boundary(lines, result_index + 1)
            if _has_c14_conclusion_or_remark_evidence(following_lines):
                continue

            raw_start = _find_c14_row_context_start(lines, result_index)
            boundary_index = result_index + 1 + len(following_lines)
            nearby_end = min(len(lines), boundary_index + 1)
            candidates.append(
                {
                    "page": page.get("page"),
                    "raw_text": _excerpt_text(" ".join(lines[raw_start : result_index + 1]), 500),
                    "nearby_text": _excerpt_text(" ".join(lines[raw_start:nearby_end]), 700),
                    "suspected_fields": ["单项结论", "备注"],
                    "reason": (
                        "检验结果值后在下一序号/子条款/此处空白前未见“符合”“不符合”或“/”；"
                        "仅作为 C14 空字段候选，最终由 Codex 结合表格上下文判定。"
                    ),
                }
            )
    return _dedupe_c14_candidates(candidates)


def _is_c14_inspection_result_table_text(text: str) -> bool:
    normalized_text = _normalize_text(text)
    return all(marker in normalized_text for marker in ["序号", "检验项目", "检验结果", "单项结论"])


def _extract_c14_layout_empty_field_rows(page: dict[str, Any]) -> list[dict[str, Any]]:
    words = _layout_words(page)
    if not words:
        return []

    columns = _c14_layout_columns(words)
    if columns is None:
        return []

    page_number = page.get("page")
    candidates: list[dict[str, Any]] = []
    row_spans = _c14_layout_row_spans(words, columns["header_bottom"], page.get("height"))
    for row in row_spans:
        result_words = _words_in_column_span(words, columns["result"], row["top"], row["bottom"])
        if not result_words:
            continue

        conclusion_words = _words_in_column_span(words, columns["conclusion"], row["top"], row["bottom"])
        remark_words = _words_in_column_span(words, columns["remark"], row["top"], row["bottom"])
        missing_fields = []
        if not conclusion_words:
            missing_fields.append("单项结论")
        if not remark_words:
            missing_fields.append("备注")
        if not missing_fields:
            continue

        result_text = " ".join(word["text"] for word in result_words)
        conclusion_text = " ".join(word["text"] for word in conclusion_words)
        remark_text = " ".join(word["text"] for word in remark_words)
        reason_parts = [
            f"版式词坐标显示第{row['row_no']}行检验结果列有值“{result_text}”。",
        ]
        if "单项结论" in missing_fields:
            reason_parts.append("单项结论列未见任何内容。")
        if "备注" in missing_fields:
            reason_parts.append("备注列未见任何内容。")
        candidates.append(
            {
                "page": page_number,
                "row_no": row["row_no"],
                "raw_text": _excerpt_text(str(page.get("text", "")), 500),
                "nearby_text": (
                    f"序号 {row['row_no']}；检验结果列：{result_text or '空'}；"
                    f"单项结论列：{conclusion_text or '空'}；备注列：{remark_text or '空'}"
                ),
                "suspected_fields": missing_fields,
                "reason": " ".join(reason_parts),
            }
        )

    return candidates


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


def _c14_layout_columns(words: list[dict[str, Any]]) -> dict[str, Any] | None:
    result = _find_word_containing(words, "检验结果")
    remark = _find_word_containing(words, "备注")
    conclusion_words = [word for word in words if word["text"] in {"单项", "结论"}]
    if result is None or remark is None or not conclusion_words:
        return None

    result_center = _word_center_x(result)
    conclusion_center = sum(_word_center_x(word) for word in conclusion_words) / len(conclusion_words)
    remark_center = _word_center_x(remark)
    result_conclusion_mid = (result_center + conclusion_center) / 2
    conclusion_remark_mid = (conclusion_center + remark_center) / 2
    result_width = max(conclusion_center - result_center, 20)
    remark_width = max(remark_center - conclusion_center, 20)
    header_bottom = max(
        result["y1"],
        remark["y1"],
        *(word["y1"] for word in conclusion_words),
    )
    return {
        "header_bottom": header_bottom,
        "result": (result_center - result_width, result_conclusion_mid),
        "conclusion": (result_conclusion_mid, conclusion_remark_mid),
        "remark": (conclusion_remark_mid, remark_center + remark_width),
    }


def _find_word_containing(words: list[dict[str, Any]], text: str) -> dict[str, Any] | None:
    for word in words:
        if text in word["text"]:
            return word
    return None


def _word_center_x(word: dict[str, Any]) -> float:
    return (word["x0"] + word["x1"]) / 2


def _word_center_y(word: dict[str, Any]) -> float:
    return (word["y0"] + word["y1"]) / 2


def _c14_layout_row_spans(
    words: list[dict[str, Any]], header_bottom: float, page_height: Any
) -> list[dict[str, Any]]:
    row_words = [
        word
        for word in words
        if word["y0"] > header_bottom and word["x0"] < 75 and re.fullmatch(r"\d{1,4}", word["text"])
    ]
    rows = []
    fallback_bottom = float(page_height) if isinstance(page_height, (int, float)) else max(word["y1"] for word in words) + 20
    for index, word in enumerate(row_words):
        next_top = row_words[index + 1]["y0"] if index + 1 < len(row_words) else fallback_bottom
        rows.append(
            {
                "row_no": word["text"],
                "top": word["y0"] - 2,
                "bottom": next_top - 1,
            }
        )
    return rows


def _words_in_column_span(
    words: list[dict[str, Any]], x_range: tuple[float, float], top: float, bottom: float
) -> list[dict[str, Any]]:
    left, right = x_range
    selected = []
    for word in words:
        center_x = _word_center_x(word)
        center_y = _word_center_y(word)
        if left <= center_x < right and top <= center_y < bottom and not _is_c14_header_word(word["text"]):
            selected.append(word)
    return selected


def _is_c14_header_word(text: str) -> bool:
    return text in {"检验结果", "单项", "结论", "备注"}


def _looks_like_c14_result_value(line: str) -> bool:
    normalized_line = _normalize_text(line)
    return "无菌生长" in normalized_line


def _c14_lines_before_next_row_boundary(lines: list[str], start_index: int) -> list[str]:
    following_lines: list[str] = []
    for line in lines[start_index:]:
        if _is_c14_row_boundary(line):
            break
        following_lines.append(line)
    return following_lines


def _is_c14_row_boundary(line: str) -> bool:
    normalized_line = _normalize_text(line)
    if not normalized_line:
        return False
    return (
        normalized_line.startswith("此处空白")
        or bool(re.match(r"^\d{1,4}(?:\D|$)", line))
        or bool(re.match(r"^\d+(?:\.\d+){1,}\D", line))
    )


def _has_c14_conclusion_or_remark_evidence(lines: list[str]) -> bool:
    for line in lines:
        normalized_line = _normalize_text(line)
        if "符合" in normalized_line or "/" in normalized_line or "／" in normalized_line:
            return True
    return False


def _find_c14_row_context_start(lines: list[str], result_index: int) -> int:
    window_start = max(0, result_index - 6)
    for index in range(result_index - 1, window_start - 1, -1):
        if _is_c14_row_boundary(lines[index]):
            if index > 0 and re.fullmatch(r"\d{1,4}", _normalize_text(lines[index - 1])):
                return index - 1
            return index
    return window_start


def _dedupe_c14_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped = []
    seen = set()
    for candidate in candidates:
        key = (
            candidate.get("page"),
            candidate.get("row_no"),
            tuple(candidate.get("suspected_fields", [])),
            candidate.get("nearby_text"),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)
    return deduped


def _extract_c15_sequence_markers(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for page in pages:
        text = str(page.get("text", ""))
        if not _is_c14_inspection_result_table_text(text):
            continue

        layout_entries = _extract_c15_layout_sequence_markers(page)
        if layout_entries:
            entries.extend(layout_entries)
            continue

        pending_marker: str | None = None
        for index, line in enumerate(_compact_lines(text)):
            compact = _normalize_text(line)
            inline_marker_match = re.match(r"^续\s*(\d{1,3})(?:\D|$)", line)
            if inline_marker_match:
                entries.append(
                    {
                        "page": page.get("page"),
                        "sequence": int(inline_marker_match.group(1)),
                        "has_continuation_marker": True,
                        "marker_text": line,
                        "row_text": line,
                        "line_index": index,
                    }
                )
                pending_marker = None
                continue

            if compact.startswith("续") and not compact.startswith("续表"):
                pending_marker = line
                continue

            row_match = re.match(r"^(\d{1,3})(?:\s|$)", line)
            if not row_match:
                continue

            entries.append(
                {
                    "page": page.get("page"),
                    "sequence": int(row_match.group(1)),
                    "has_continuation_marker": pending_marker is not None,
                    "marker_text": pending_marker,
                    "row_text": line,
                    "line_index": index,
                }
            )
            pending_marker = None

    return entries


def _extract_c15_layout_sequence_markers(page: dict[str, Any]) -> list[dict[str, Any]]:
    words = _layout_words(page)
    if not words:
        return []

    columns = _c14_layout_columns(words)
    if columns is None:
        return []

    entries: list[dict[str, Any]] = []
    first_column_words = [
        word
        for word in words
        if word["y0"] > columns["header_bottom"] and word["x0"] < 75
    ]
    pending_marker: dict[str, Any] | None = None
    for index, word in enumerate(first_column_words):
        text = word["text"]
        inline_marker = re.fullmatch(r"续\s*(\d{1,3})", text)
        if inline_marker:
            entries.append(
                {
                    "page": page.get("page"),
                    "sequence": int(inline_marker.group(1)),
                    "has_continuation_marker": True,
                    "marker_text": text,
                    "row_text": text,
                    "line_index": index,
                }
            )
            pending_marker = None
            continue

        if text == "续":
            pending_marker = word
            continue

        if not re.fullmatch(r"\d{1,3}", text):
            pending_marker = None
            continue

        entries.append(
            {
                "page": page.get("page"),
                "sequence": int(text),
                "has_continuation_marker": pending_marker is not None,
                "marker_text": pending_marker["text"] if pending_marker else None,
                "row_text": _c15_layout_row_text(words, word),
                "line_index": index,
            }
        )
        pending_marker = None
    return entries


def _c15_layout_row_text(words: list[dict[str, Any]], sequence_word: dict[str, Any]) -> str:
    center_y = _word_center_y(sequence_word)
    line_words = [
        word["text"]
        for word in words
        if abs(_word_center_y(word) - center_y) <= 3 and word["x0"] >= sequence_word["x0"]
    ]
    return " ".join(line_words) or sequence_word["text"]


def _extract_c15_continuation_marker_candidates(sequence_markers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    seen_sequences: set[int] = set()
    for entry in sequence_markers:
        sequence = int(entry["sequence"])
        has_marker = bool(entry.get("has_continuation_marker"))
        expected_marker = sequence in seen_sequences
        if expected_marker and not has_marker:
            candidates.append(
                {
                    "issue": "missing_continuation_marker",
                    "page": entry.get("page"),
                    "sequence": sequence,
                    "expected": f"续{sequence}",
                    "actual": str(entry.get("row_text", "")),
                    "reason": f"序号 {sequence} 此前已经出现，本次再次出现时序号栏未带“续”。",
                }
            )
        if not expected_marker and has_marker:
            candidates.append(
                {
                    "issue": "unexpected_continuation_marker",
                    "page": entry.get("page"),
                    "sequence": sequence,
                    "expected": str(sequence),
                    "actual": f"{entry.get('marker_text') or ''} {entry.get('row_text') or ''}".strip(),
                    "reason": f"序号 {sequence} 是首次出现，但序号栏带有“续”。",
                }
            )
        seen_sequences.add(sequence)
    return candidates


def _compact_lines(text: str) -> list[str]:
    return [re.sub(r"\s+", " ", line).strip() for line in text.splitlines() if line.strip()]


def _looks_like_date(text: str) -> bool:
    return bool(re.fullmatch(r"\d{4}[-/.年]?\d{1,2}[-/.月]?\d{0,2}日?", text))


def _excerpt_text(text: str, max_chars: int) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    return compact[:max_chars]
