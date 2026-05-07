from app.services.record_report_evidence_builder import (
    aggregate_record_judgement,
    build_gb9706_202_record_report_comparisons,
    build_record_report_comparisons,
    extract_gb9706_202_record_entries,
    extract_gb9706_202_report_reference_ranges,
    extract_gb9706_202_report_rows,
    extract_record_entries,
    extract_report_rows,
    normalize_gb9706_202_clause_number,
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


def test_normalize_gb9706_202_clause_number_handles_spaced_and_top_level_values():
    assert normalize_gb9706_202_clause_number("201.4.2 .3.101") == "201.4.2.3.101"
    assert normalize_gb9706_202_clause_number("201.4.1 1") == "201.4.11"
    assert normalize_gb9706_202_clause_number("208") == "208"
    assert normalize_gb9706_202_clause_number("GB 9706.202") == ""
    assert normalize_gb9706_202_clause_number("2.1") == ""


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


def test_extract_gb9706_202_record_entries_reads_table2_fields_and_judgement():
    page = {
        "page": 3,
        "width": 620,
        "height": 260,
        "text": "检测原始记录（表2） 标准号 GB 9706.202-2021 序号 检验项目 条款号 标准要求 实测数据 备注",
        "layout_words": [
            _word("序号", 10, 40, 35, 50),
            _word("检验项目", 70, 40, 120, 50),
            _word("条款号", 150, 40, 190, 50),
            _word("标准要求", 230, 40, 280, 50),
            _word("实测数据", 410, 40, 460, 50),
            _word("备注", 540, 40, 570, 50),
            _word("1", 15, 82, 25, 92),
            _word("风险管理", 70, 82, 120, 92),
            _word("201.4.2", 150, 82, 188, 92),
            _word(".3.101", 190, 82, 210, 92),
            _word("应纳入风险管理", 230, 82, 320, 92),
            _word("△", 385, 82, 395, 92),
            _word("2", 15, 126, 25, 136),
            _word("工作数据", 70, 126, 120, 136),
            _word("208", 150, 126, 170, 136),
            _word("报警要求", 230, 126, 280, 136),
            _word("符合要求", 380, 126, 430, 136),
            _word("/", 540, 126, 545, 136),
        ],
        "drawings": [],
    }

    entries = extract_gb9706_202_record_entries([page])

    assert [entry["record_sequence"] for entry in entries] == [1, 2]
    assert entries[0]["clauses"] == ["201.4.2.3.101"]
    assert entries[0]["inspection_item"] == "风险管理"
    assert entries[0]["measured_data"] == "△"
    assert entries[0]["judgement"] == "不适用"
    assert entries[1]["clauses"] == ["208"]
    assert entries[1]["judgement"] == "符合"


def test_extract_gb9706_202_record_entries_treats_large_triangle_as_not_applicable():
    page = {
        "page": 11,
        "width": 620,
        "height": 220,
        "text": "检测原始记录（表2） 标准号 GB 9706.202-2021 序号 检验项目 条款号 标准要求 实测数据 备注",
        "layout_words": [
            _word("序号", 10, 40, 35, 50),
            _word("检验项目", 70, 40, 120, 50),
            _word("条款号", 150, 40, 190, 50),
            _word("标准要求", 230, 40, 280, 50),
            _word("实测数据", 410, 40, 460, 50),
            _word("备注", 540, 40, 570, 50),
            _word("16", 15, 82, 25, 92),
            _word("患者导联", 70, 82, 120, 92),
            _word("201.8.5", 150, 82, 188, 92),
            _word("不适用于手术连接器", 230, 82, 330, 92),
            _word("/", 540, 82, 545, 92),
        ],
        "drawings": [_filled_mark(382, 82, 435, 123)],
    }

    entries = extract_gb9706_202_record_entries([page])

    assert len(entries) == 1
    assert entries[0]["judgement"] == "不适用"
    assert entries[0]["symbol_judgement"] == "drawing_delta_mark"


def test_extract_gb9706_202_record_entries_ignores_vertical_annotation_and_treats_large_triangle_as_delta():
    page = {
        "page": 9,
        "width": 620,
        "height": 300,
        "text": "检测原始记录（表2） 标准号 GB 9706.202-2021 序号 检验项目 条款号 标准要求 实测数据 备注",
        "layout_words": [
            _word("序号", 10, 40, 35, 50),
            _word("检验项目", 70, 40, 120, 50),
            _word("条款号", 150, 40, 190, 50),
            _word("标准要求", 230, 40, 280, 50),
            _word("实测数据", 410, 40, 460, 50),
            _word("备注", 540, 40, 570, 50),
            _word("14", 15, 82, 28, 92),
            _word("电压电流限制", 70, 82, 140, 92),
            _word("201.8.4", 150, 82, 188, 92),
            _word("中性电极监测电路", 230, 82, 330, 92),
            _word("/", 540, 82, 545, 92),
        ],
        "drawings": [
            _filled_mark(382, 82, 440, 131),
            _filled_mark(444, 82, 465, 239),
        ],
    }

    entries = extract_gb9706_202_record_entries([page])

    assert len(entries) == 1
    assert entries[0]["record_sequence"] == 14
    assert entries[0]["judgement"] == "不适用"
    assert entries[0]["symbol_judgement"] == "drawing_delta_mark"


def test_extract_gb9706_202_record_entries_treats_compact_check_as_compliant():
    page = {
        "page": 6,
        "width": 620,
        "height": 240,
        "text": "检测原始记录（表2） 标准号 GB 9706.202-2021 序号 检验项目 条款号 标准要求 实测数据 备注",
        "layout_words": [
            _word("序号", 10, 40, 35, 50),
            _word("检验项目", 70, 40, 120, 50),
            _word("条款号", 150, 40, 190, 50),
            _word("标准要求", 230, 40, 280, 50),
            _word("实测数据", 410, 40, 460, 50),
            _word("备注", 540, 40, 570, 50),
            _word("11", 15, 82, 28, 92),
            _word("附件", 70, 82, 110, 92),
            _word("201.7.9", 150, 82, 188, 92),
            _word("应包含资料", 230, 82, 300, 92),
            _word("/", 540, 82, 545, 92),
        ],
        "drawings": [_filled_mark(382, 82, 438, 134)],
    }

    entries = extract_gb9706_202_record_entries([page])

    assert len(entries) == 1
    assert entries[0]["judgement"] == "符合"
    assert entries[0]["symbol_judgement"] == "drawing_check_mark"


def test_extract_gb9706_202_record_entries_uses_open_path_for_check_like_mark():
    check_mark = _filled_mark(382, 82, 440, 131)
    check_mark["path_start"] = {"x": 383, "y": 126}
    check_mark["path_end"] = {"x": 439, "y": 83}
    page = {
        "page": 18,
        "width": 620,
        "height": 240,
        "text": "检测原始记录（表2） 标准号 GB 9706.202-2021 序号 检验项目 条款号 标准要求 实测数据 备注",
        "layout_words": [
            _word("序号", 10, 40, 35, 50),
            _word("检验项目", 70, 40, 120, 50),
            _word("条款号", 150, 40, 190, 50),
            _word("标准要求", 230, 40, 280, 50),
            _word("实测数据", 410, 40, 460, 50),
            _word("备注", 540, 40, 570, 50),
            _word("31", 15, 82, 28, 92),
            _word("供电电源", 70, 82, 120, 92),
            _word("201.11.8", 150, 82, 198, 92),
            _word("模式不应改变", 230, 82, 310, 92),
            _word("/", 540, 82, 545, 92),
        ],
        "drawings": [check_mark],
    }

    entries = extract_gb9706_202_record_entries([page])

    assert len(entries) == 1
    assert entries[0]["judgement"] == "符合"
    assert entries[0]["symbol_judgement"] == "drawing_check_mark"


def test_extract_gb9706_202_record_entries_includes_first_continuation_row_mark_above_sequence_number():
    page = {
        "page": 20,
        "width": 620,
        "height": 240,
        "text": "检测原始记录（表2） 标准号 GB 9706.202-2021 序号 检验项目 条款号 标准要求 实测数据 备注",
        "layout_words": [
            _word("序号", 10, 40, 35, 50),
            _word("检验项目", 70, 40, 120, 50),
            _word("条款号", 150, 40, 190, 50),
            _word("标准要求", 230, 40, 280, 50),
            _word("实测数据", 410, 40, 460, 50),
            _word("备注", 540, 40, 570, 50),
            _word("续", 15, 86, 25, 96),
            _word("33", 15, 104, 27, 114),
            _word("ME设备", 70, 88, 110, 98),
            _word("e)", 230, 88, 245, 98),
            _word("201.12.2", 250, 88, 300, 98),
            _word("不能错误连接", 230, 108, 300, 118),
        ],
        "drawings": [_filled_mark(378, 62, 458, 152)],
    }

    entries = extract_gb9706_202_record_entries([page])

    assert len(entries) == 1
    assert entries[0]["record_sequence"] == 33
    assert entries[0]["judgement"] == "符合"
    assert entries[0]["symbol_judgement"] == "drawing_check_mark"


def test_extract_gb9706_202_record_entries_uses_table_line_above_sequence_for_row_top():
    page = {
        "page": 1,
        "width": 620,
        "height": 240,
        "text": "检测原始记录（表2） 标准号 GB 9706.202-2021 序号 检验项目 条款号 标准要求 实测数据 备注",
        "layout_words": [
            _word("序号", 10, 40, 35, 50),
            _word("检验项目", 70, 40, 120, 50),
            _word("条款号", 150, 40, 190, 50),
            _word("标准要求", 230, 40, 280, 50),
            _word("实测数据", 410, 40, 460, 50),
            _word("备注", 540, 40, 570, 50),
            _word("5", 15, 146, 25, 156),
            _word("其他电源", 70, 146, 120, 156),
            _word("201.7.2", 150, 146, 188, 156),
            _word("7.2.8.2", 230, 146, 270, 156),
        ],
        "drawings": [
            _box(0, 136, 620, 137),
            _filled_mark(380, 94, 465, 180),
        ],
    }

    entries = extract_gb9706_202_record_entries([page])

    assert len(entries) == 1
    assert entries[0]["record_sequence"] == 5
    assert entries[0]["judgement"] == "符合"
    assert entries[0]["symbol_judgement"] == "drawing_check_mark"


def test_extract_gb9706_202_report_rows_uses_reference_range_and_excludes_product_requirement_rows():
    page = {
        "page": 42,
        "width": 640,
        "height": 220,
        "text": (
            "GB 9706.1-2020 见序号1～118。"
            "GB 9706.202-2021 见序号119～120。"
            "序号 标准条款 标准要求 检验结果 单项结论 备注"
        ),
        "layout_words": [
            _word("序号", 10, 10, 35, 20),
            _word("标准条款", 75, 10, 125, 20),
            _word("标准要求", 200, 10, 250, 20),
            _word("检验结果", 370, 10, 420, 20),
            _word("单项结论", 465, 10, 515, 20),
            _word("备注", 550, 10, 580, 20),
            _word("119", 12, 60, 30, 70),
            _word("201.4.2", 80, 60, 118, 70),
            _word(".3.101", 120, 60, 148, 70),
            _word("风险管理要求", 200, 60, 280, 70),
            _word("/", 380, 60, 385, 70),
            _word("不适用", 475, 60, 515, 70),
            _word("120", 12, 100, 30, 110),
            _word("208", 80, 100, 100, 110),
            _word("报警要求", 200, 100, 250, 110),
            _word("符合要求", 380, 100, 430, 110),
            _word("符合", 475, 100, 505, 110),
            _word("157", 12, 140, 30, 150),
            _word("2.1", 80, 140, 100, 150),
            _word("GB9706.202-2021 产品技术要求", 200, 140, 340, 150),
            _word("符合要求", 380, 140, 430, 150),
            _word("符合", 475, 140, 505, 150),
        ],
    }

    ranges = extract_gb9706_202_report_reference_ranges([page])
    rows = extract_gb9706_202_report_rows([page])

    assert ranges == [{"start": 119, "end": 120, "page": 42}]
    assert [row["sequence"] for row in rows] == [119, 120]
    assert rows[0]["standard_clauses"] == ["201.4.2.3.101"]
    assert rows[0]["report_judgement"] == "不适用"
    assert rows[1]["standard_clauses"] == ["208"]
    assert rows[1]["report_judgement"] == "符合"


def test_build_gb9706_202_comparisons_uses_clause_then_sequence_fallback():
    record_entries = [
        {
            "page": 3,
            "record_sequence": 1,
            "clauses": ["201.4.2.3.101"],
            "judgement": "不适用",
            "requirement_text": "201.4.2.3.101 A",
        },
        {
            "page": 3,
            "record_sequence": 2,
            "clauses": ["201.12.1"],
            "judgement": "符合",
            "requirement_text": "208 B",
        },
    ]
    report_rows = [
        {
            "sequence": 119,
            "page": 42,
            "standard_clause": "201.4.2.3.101",
            "standard_clauses": ["201.4.2.3.101"],
            "standard_requirement": "风险管理要求",
            "inspection_result": "",
            "single_conclusion": "不适用",
            "report_judgement": "不适用",
        },
        {
            "sequence": 120,
            "page": 42,
            "standard_clause": "208",
            "standard_clauses": ["208"],
            "standard_requirement": "报警要求",
            "inspection_result": "符合要求",
            "single_conclusion": "符合",
            "report_judgement": "符合",
        },
    ]

    bundle = build_gb9706_202_record_report_comparisons(
        record_entries,
        report_rows,
        [{"start": 119, "end": 120, "page": 42}],
    )

    assert bundle["summary_counts"]["report_row_count"] == 2
    assert bundle["summary_counts"]["record_entry_count"] == 2
    assert bundle["summary_counts"]["matched_count"] == 2
    assert bundle["summary_counts"]["missing_mapping_count"] == 0
    assert bundle["comparisons"][0]["mapping_method"] == "clause"
    assert bundle["comparisons"][1]["mapping_method"] == "sequence_fallback"


def test_build_gb9706_202_comparisons_uses_parent_clause_sequence_for_branch_group():
    record_entries = [
        {
            "page": 2,
            "record_sequence": 2,
            "clauses": ["201.8.4.10120"],
            "judgement": "符合",
            "requirement_text": "OCR 误连产生的相似条款",
        },
        {
            "page": 9,
            "record_sequence": 14,
            "clauses": ["201.8.4", "201.8.4.101", "201.8.6.1", "201.8.7.3", "201.7.9.2.2.101"],
            "judgement": "不适用",
            "requirement_text": "201.8.4 下的分支条款组合",
        },
    ]
    report_rows = [
        {
            "sequence": 132,
            "page": 92,
            "standard_clause": "201.8.4、201.8.4.101、201.8.6.1、201.8.4.1022",
            "standard_clauses": ["201.8.4", "201.8.4.101", "201.8.6.1", "201.8.4.1022"],
            "standard_requirement": "中性电极监测电路及其分支要求",
            "inspection_result": "——",
            "single_conclusion": "/",
            "report_judgement": "不适用",
        }
    ]

    bundle = build_gb9706_202_record_report_comparisons(
        record_entries,
        report_rows,
        [{"start": 119, "end": 156, "page": 5}],
    )

    comparison = bundle["comparisons"][0]
    assert comparison["matched"] is True
    assert comparison["record_aggregate_judgement"] == "不适用"
    assert comparison["record_entries"][0]["record_sequence"] == 14
    assert comparison["mapping_method"] == "parent_clause_sequence"
