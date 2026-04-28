from app.services.record_report_evidence_builder import (
    aggregate_record_judgement,
    build_record_report_comparisons,
    extract_record_entries,
    extract_report_rows,
    normalize_clause_number,
)


def _word(text: str, x0: float, y0: float, x1: float, y1: float) -> dict:
    return {"text": text, "x0": x0, "y0": y0, "x1": x1, "y1": y1}


def _box(x0: float, y0: float, x1: float, y1: float) -> dict:
    return {"rect": {"x0": x0, "y0": y0, "x1": x1, "y1": y1}, "ops": ["re"]}


def _mark(x0: float, y0: float, x1: float, y1: float) -> dict:
    return {"rect": {"x0": x0, "y0": y0, "x1": x1, "y1": y1}, "ops": ["l", "l"]}


def _filled_mark(x0: float, y0: float, x1: float, y1: float) -> dict:
    return {
        "rect": {"x0": x0, "y0": y0, "x1": x1, "y1": y1},
        "ops": ["l", "c", "c", "c", "l", "c"],
        "fill": [0.0, 0.0, 0.0],
    }


def test_normalize_clause_number_removes_spaces_around_dots():
    assert normalize_clause_number("15.3. 1") == "15.3.1"
    assert normalize_clause_number(" 7．2．3 ") == "7.2.3"
    assert normalize_clause_number("GB 9706.1") == ""
    assert normalize_clause_number("0.4") == ""
    assert normalize_clause_number("42.4") == ""
    assert normalize_clause_number("15.3.15.3.4.1") == "15.3.4.1"


def test_extract_record_entries_detects_selected_checkbox_from_drawings():
    page = {
        "page": 6,
        "width": 620,
        "height": 160,
        "text": "序号 要求描述 建议观察记录 符合性 符合 不符合 不适用",
        "layout_words": [
            _word("序号", 10, 10, 30, 20),
            _word("要求描述", 80, 10, 160, 20),
            _word("建议观察记录", 250, 10, 350, 20),
            _word("符合性", 500, 10, 540, 20),
            _word("符合", 440, 30, 470, 40),
            _word("不符合", 490, 30, 530, 40),
            _word("不适用", 550, 30, 595, 40),
            _word("1", 15, 62, 25, 72),
            _word("15.3.", 85, 62, 115, 72),
            _word("1", 120, 62, 128, 72),
            _word("应进行机械强度检查", 135, 62, 205, 72),
            _word("观察记录", 260, 62, 330, 72),
        ],
        "drawings": [
            _box(445, 62, 455, 72),
            _box(495, 62, 505, 72),
            _box(555, 62, 565, 72),
            _mark(497, 64, 503, 69),
        ],
    }

    entries = extract_record_entries([page])

    assert len(entries) == 1
    assert entries[0]["clauses"] == ["15.3.1"]
    assert entries[0]["judgement"] == "不符合"
    assert entries[0]["source"] == "layout"


def test_extract_record_entries_uses_clause_heading_over_see_reference():
    page = {
        "page": 11,
        "width": 620,
        "height": 180,
        "text": "序号 要求描述 建议观察记录 符合性 符合 不符合 不适用",
        "layout_words": [
            _word("序号", 10, 10, 30, 20),
            _word("要求描述", 80, 10, 160, 20),
            _word("建议观察记录", 250, 10, 350, 20),
            _word("符合性", 500, 10, 540, 20),
            _word("符合", 440, 30, 470, 40),
            _word("不符合", 490, 30, 530, 40),
            _word("不适用", 550, 30, 595, 40),
            _word("7.1.1", 42, 92, 68, 102),
            _word("12.2。", 58, 114, 68, 124),
            _word("见", 58, 126, 66, 136),
        ],
        "drawings": [
            _box(445, 114, 455, 124),
            _box(495, 114, 505, 124),
            _box(555, 114, 565, 124),
            _mark(447, 116, 453, 121),
        ],
    }

    entries = extract_record_entries([page])

    assert len(entries) == 1
    assert entries[0]["clauses"] == ["7.1.1"]
    assert entries[0]["judgement"] == "符合"


def test_extract_record_entries_treats_wide_selection_mark_as_not_applicable():
    page = {
        "page": 77,
        "width": 620,
        "height": 180,
        "text": "序号 要求描述 建议观察记录 符合性 符合 不符合 不适用",
        "layout_words": [
            _word("序号", 10, 10, 30, 20),
            _word("要求描述", 80, 10, 160, 20),
            _word("建议观察记录", 250, 10, 350, 20),
            _word("符合性", 500, 10, 540, 20),
            _word("符合", 440, 30, 470, 40),
            _word("不符合", 490, 30, 530, 40),
            _word("不适用", 550, 30, 595, 40),
            _word("11.7", 56, 78, 88, 88),
            _word("生物相容性", 145, 84, 205, 94),
            _word("□", 445, 84, 455, 94),
            _word("□", 495, 84, 505, 94),
            _word("□", 555, 84, 565, 94),
        ],
        "drawings": [
            _mark(420, 78, 585, 108),
        ],
    }

    entries = extract_record_entries([page])

    assert len(entries) == 1
    assert entries[0]["clauses"] == ["11.7"]
    assert entries[0]["judgement"] == "不适用"


def test_extract_record_entries_does_not_treat_filled_slash_mark_as_checkbox_box():
    page = {
        "page": 74,
        "width": 620,
        "height": 180,
        "text": "序号 要求描述 建议观察记录 符合性 符合 不符合 不适用",
        "layout_words": [
            _word("序号", 10, 10, 30, 20),
            _word("要求描述", 80, 10, 160, 20),
            _word("建议观察记录", 250, 10, 350, 20),
            _word("符合性", 500, 10, 540, 20),
            _word("符合", 440, 30, 470, 40),
            _word("不符合", 490, 30, 530, 40),
            _word("不适用", 550, 30, 595, 40),
            _word("11.5", 56, 84, 88, 94),
            _word("制造商风险管理", 145, 84, 220, 94),
            _word("□", 445, 84, 455, 94),
            _word("□", 495, 84, 505, 94),
            _word("□", 555, 84, 565, 94),
            _word("11.6", 56, 118, 88, 128),
            _word("下一行", 145, 118, 220, 128),
            _word("□", 445, 118, 455, 128),
            _word("□", 495, 118, 505, 128),
            _word("□", 555, 118, 565, 128),
        ],
        "drawings": [
            _filled_mark(552, 78, 580, 108),
            _filled_mark(420, 112, 470, 146),
        ],
    }

    entries = extract_record_entries([page])

    assert entries[0]["clauses"] == ["11.5"]
    assert entries[0]["judgement"] == "不适用"


def test_extract_report_rows_normalizes_spaced_standard_clause():
    page = {
        "page": 12,
        "width": 640,
        "height": 160,
        "text": "序号 标准条款 标准要求 检验结果 单项结论 备注",
        "layout_words": [
            _word("序号", 10, 10, 35, 20),
            _word("标准条款", 75, 10, 125, 20),
            _word("标准要求", 200, 10, 250, 20),
            _word("检验结果", 370, 10, 420, 20),
            _word("单项结论", 465, 10, 515, 20),
            _word("备注", 550, 10, 580, 20),
            _word("10", 12, 60, 30, 70),
            _word("15.3.", 80, 60, 112, 70),
            _word("1", 118, 60, 126, 70),
            _word("机械强度要求", 200, 60, 280, 70),
            _word("已检", 380, 60, 410, 70),
            _word("符合", 475, 60, 505, 70),
            _word("/", 560, 60, 565, 70),
        ],
    }

    rows = extract_report_rows([page])

    assert len(rows) == 1
    assert rows[0]["sequence"] == 10
    assert rows[0]["standard_clauses"] == ["15.3.1"]
    assert rows[0]["report_judgement"] == "符合"


def test_extract_report_rows_repairs_repeated_clause_prefix_from_layout_text():
    page = {
        "page": 64,
        "width": 640,
        "height": 180,
        "text": "序号 标准条款 标准要求 检验结果 单项结论 备注",
        "layout_words": [
            _word("序号", 10, 10, 35, 20),
            _word("标准条款", 115, 10, 170, 20),
            _word("标准要求", 245, 10, 295, 20),
            _word("检验结果", 390, 10, 440, 20),
            _word("单项结论", 475, 10, 525, 20),
            _word("备注", 560, 10, 590, 20),
            _word("103", 12, 60, 30, 70),
            _word("15.3.", 130, 60, 158, 70),
            _word("15.3.4.1", 180, 60, 224, 70),
            _word("15.3.4.2", 180, 84, 224, 94),
            _word("坠落试验要求", 230, 60, 310, 70),
            _word("符合要求", 400, 60, 445, 70),
            _word("符合", 485, 60, 510, 70),
            _word("/", 565, 60, 570, 70),
        ],
    }

    rows = extract_report_rows([page])

    assert len(rows) == 1
    assert rows[0]["sequence"] == 103
    assert rows[0]["standard_clauses"] == ["15.3.4.1", "15.3.4.2"]
    assert rows[0]["report_judgement"] == "符合"


def test_extract_report_rows_accepts_top_level_clause():
    page = {
        "page": 79,
        "width": 640,
        "height": 160,
        "text": "序号 标准条款 标准要求 检验结果 单项结论 备注",
        "layout_words": [
            _word("序号", 10, 10, 35, 20),
            _word("标准条款", 75, 10, 125, 20),
            _word("标准要求", 200, 10, 250, 20),
            _word("检验结果", 370, 10, 420, 20),
            _word("单项结论", 465, 10, 515, 20),
            _word("备注", 550, 10, 580, 20),
            _word("118", 12, 60, 30, 70),
            _word("17", 82, 60, 95, 70),
            _word("电磁兼容风险管理", 200, 60, 310, 70),
            _word("/", 380, 60, 385, 70),
            _word("/", 475, 60, 480, 70),
        ],
    }

    rows = extract_report_rows([page])

    assert len(rows) == 1
    assert rows[0]["sequence"] == 118
    assert rows[0]["standard_clauses"] == ["17"]
    assert rows[0]["report_judgement"] == "不适用"


def test_aggregate_record_judgement_priority_order():
    assert aggregate_record_judgement([{"judgement": "符合"}, {"judgement": "不适用"}]) == "符合"
    assert aggregate_record_judgement([{"judgement": "不适用"}, {"judgement": "不适用"}]) == "不适用"
    assert aggregate_record_judgement([{"judgement": "符合"}, {"judgement": "不符合"}]) == "不符合"
    assert aggregate_record_judgement([]) == "缺失"


def test_build_comparisons_maps_record_clauses_by_report_prefix_and_flags_mismatch():
    record_entries = [
        {"page": 6, "record_sequence": "1", "clauses": ["15.3.1"], "judgement": "符合", "requirement_text": "15.3.1 A"},
        {"page": 6, "record_sequence": "2", "clauses": ["15.3.2"], "judgement": "不符合", "requirement_text": "15.3.2 B"},
    ]
    report_rows = [
        {
            "sequence": 10,
            "page": 12,
            "standard_clause": "15.3",
            "standard_clauses": ["15.3"],
            "standard_requirement": "机械强度",
            "inspection_result": "",
            "single_conclusion": "符合",
            "report_judgement": "符合",
        }
    ]

    bundle = build_record_report_comparisons(record_entries, report_rows)

    assert bundle["summary_counts"]["mismatch_count"] == 1
    comparison = bundle["comparisons"][0]
    assert comparison["record_entry_count"] == 2
    assert comparison["record_aggregate_judgement"] == "不符合"
    assert comparison["report_judgement"] == "符合"
    assert comparison["issue"] == "mismatch"


def test_build_comparisons_marks_empty_extractions_as_missing_mapping():
    bundle = build_record_report_comparisons([], [])

    assert bundle["summary_counts"]["missing_mapping_count"] == 2
    assert {item["type"] for item in bundle["missing_mappings"]} == {
        "report_table_missing",
        "record_table_missing",
    }
