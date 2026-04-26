import json
from pathlib import Path

import pytest

from app.services.report_evidence_builder import APPROVED_CHECK_IDS, ReportEvidenceBuilder


def load_fixture() -> dict:
    return json.loads(Path("tests/fixtures/minimal_report_pages.json").read_text(encoding="utf-8"))


def test_builder_creates_exactly_approved_check_packages():
    evidence = ReportEvidenceBuilder().build_all(load_fixture())

    assert [item["check_id"] for item in evidence] == APPROVED_CHECK_IDS
    assert "C05" not in [item["check_id"] for item in evidence]
    assert "C17" not in [item["check_id"] for item in evidence]
    assert "C18" not in [item["check_id"] for item in evidence]


def test_c02_package_contains_concrete_cover_and_home_fields():
    evidence = ReportEvidenceBuilder().build_all(load_fixture())
    c02 = next(item for item in evidence if item["check_id"] == "C02")

    assert c02["check_name"] == "首页基础字段一致性"
    assert "cover_text" in c02["evidence"]
    assert "report_home_text" in c02["evidence"]
    assert c02["required_details"] == ["field_comparisons"]


def test_builder_finds_spaced_section_titles_without_false_photo_match():
    report = {
        "file_name": "spaced.pdf",
        "pages": [
            {"page": 1, "text": "检  验  报  告\n报告编号：国医检（设）字 QW2026 第 1432 号"},
            {"page": 2, "text": "注 意 事 项"},
            {"page": 3, "text": "检 验 报 告 首 页\n样品名称 一次性使用球囊形脉冲电场消融导管"},
            {"page": 4, "text": "样品描述\n以上详见照片"},
            {"page": 5, "text": "序 号\n检验\n项目\n检验结果\n单项\n结论\n1\n尺寸\n符合要求\n符合"},
            {"page": 6, "text": "检 验 报 告 照 片 页\n照片和说明\n№1 检品外观"},
        ],
    }

    evidence = ReportEvidenceBuilder().build_one("C02", report)["evidence"]

    assert "检 验 报 告 首 页" in evidence["report_home_text"]
    assert "序 号" in evidence["inspection_table_text"]
    assert "检 验 报 告 照 片 页" in evidence["photo_text"]
    assert "样品描述" not in evidence["photo_text"]


def test_photo_text_uses_actual_photo_page_not_sample_description_reference():
    report = {
        "file_name": "photo-reference.pdf",
        "pages": [
            {"page": 4, "text": "样品描述\n被检样品为一次性使用消化道脉冲电场消融导管，详见报告照片页"},
            {"page": 9, "text": "检 验 报 告 照 片 页\n照片和说明\n№1 检品外观\n№2 检品标签样张"},
        ],
    }

    evidence = ReportEvidenceBuilder().build_one("C08", report)["evidence"]

    assert "检 验 报 告 照 片 页" in evidence["photo_text"]
    assert "样品描述" not in evidence["photo_text"]
    assert [page["page"] for page in evidence["photo_pages"]] == [9]


def test_c04_and_c14_packages_include_current_business_rules():
    evidence = ReportEvidenceBuilder().build_all(load_fixture())
    c04 = next(item for item in evidence if item["check_id"] == "C04")
    c14 = next(item for item in evidence if item["check_id"] == "C14")

    assert any("不要核对签发日期" in rule for rule in c04["check_rules"])
    assert any("不检查签发日期、批准、审核、检验" in rule for rule in c14["check_rules"])
    assert any("备注" in rule and "“/”" in rule for rule in c14["check_rules"])


def test_c08_package_includes_label_pages_and_image_paths():
    report = {
        "file_name": "labels.pdf",
        "pages": [
            {
                "page": 4,
                "text": "样品描述\n被检样品包括：\n1 导管 EPV8DZOC 批号：76180003",
            },
            {
                "page": 10,
                "text": "检 验 报 告 照 片 页\n照片和说明\n№7 导管标签样张",
                "image_path": "/tmp/page-010.png",
            },
        ],
    }

    c08 = ReportEvidenceBuilder().build_one("C08", report)

    assert c08["check_name"] == "样品描述与照片标签一致性"
    assert c08["required_details"] == ["sample_items", "label_items", "label_comparisons"]
    assert c08["image_paths"] == ["/tmp/page-010.png"]
    assert c08["evidence"]["label_photo_pages"][0]["page"] == 10
    assert any("型号、批号/序列号必须一致" in rule for rule in c08["check_rules"])


def test_c08_package_includes_label_page_crop_images_for_codex():
    report = {
        "file_name": "labels-with-crops.pdf",
        "pages": [
            {"page": 4, "text": "样品描述\n1 导管 EPV8DZOC 76180003"},
            {
                "page": 10,
                "text": "检 验 报 告 照 片 页\n照片和说明\n№7 导管标签样张",
                "image_path": "/tmp/page-010.png",
                "image_crop_paths": ["/tmp/page-010-crop-001.png", "/tmp/page-010-crop-002.png"],
            },
        ],
    }

    c08 = ReportEvidenceBuilder().build_one("C08", report)

    assert c08["image_paths"] == [
        "/tmp/page-010.png",
        "/tmp/page-010-crop-001.png",
        "/tmp/page-010-crop-002.png",
    ]
    assert c08["evidence"]["label_photo_pages"][0]["image_crop_paths"] == [
        "/tmp/page-010-crop-001.png",
        "/tmp/page-010-crop-002.png",
    ]
    assert c08["evidence"]["attached_image_count"] == 3


@pytest.mark.parametrize("check_id", ["C03", "C06"])
def test_c03_and_c06_packages_include_label_page_crop_images_for_codex(check_id):
    report = {
        "file_name": "labels-for-field-checks.pdf",
        "pages": [
            {"page": 4, "text": "样品描述\n1 导管 EPV8DZOC 76180003"},
            {
                "page": 10,
                "text": "检 验 报 告 照 片 页\n照片和说明\n№7 导管标签样张",
                "image_path": "/tmp/page-010.png",
                "image_crop_paths": ["/tmp/page-010-crop-001.png", "/tmp/page-010-crop-002.png"],
            },
        ],
    }

    package = ReportEvidenceBuilder().build_one(check_id, report)

    assert package["image_paths"] == [
        "/tmp/page-010.png",
        "/tmp/page-010-crop-001.png",
        "/tmp/page-010-crop-002.png",
    ]
    assert package["evidence"]["attached_image_count"] == 3
    assert package["evidence"]["label_photo_pages"][0]["image_crop_paths"] == [
        "/tmp/page-010-crop-001.png",
        "/tmp/page-010-crop-002.png",
    ]


def test_c08_package_prepares_structured_candidates_for_codex():
    report = {
        "file_name": "structured-labels.pdf",
        "pages": [
            {
                "page": 4,
                "text": (
                    "样品描述\n"
                    "被检样品信息如下：\n"
                    "序号 部件名称 型号规格 批号/序列号 生产日期\n"
                    "1 导管 EPV8DZOC 76180003 2025-04-01"
                ),
            },
            {
                "page": 10,
                "text": (
                    "检 验 报 告 照 片 页\n"
                    "照片和说明\n"
                    "№7 导管标签样张\n"
                    "产品名称：导管\n"
                    "型号规格：EPV8DZOC\n"
                    "批号/序列号：76180003"
                ),
                "image_path": "/tmp/page-010.png",
            },
        ],
    }

    c08 = ReportEvidenceBuilder().build_one("C08", report)
    evidence = c08["evidence"]

    assert evidence["attached_image_count"] == 1
    assert evidence["sample_items"][0]["component_name"] == "导管"
    assert evidence["sample_items"][0]["model"] == "EPV8DZOC"
    assert evidence["sample_items"][0]["batch_or_serial"] == "76180003"
    assert evidence["label_items"][0]["page"] == 10
    assert evidence["label_items"][0]["fields"]["产品名称"] == "导管"
    assert evidence["label_items"][0]["fields"]["型号规格"] == "EPV8DZOC"
    assert evidence["label_items"][0]["fields"]["批号/序列号"] == "76180003"
    assert evidence["candidate_match_hints"][0]["sample_component_name"] == "导管"
    assert evidence["candidate_match_hints"][0]["label_candidate_pages"] == [10]


def test_c08_sample_candidates_support_pdf_table_cells_split_across_lines():
    report = {
        "file_name": "split-table.pdf",
        "pages": [
            {
                "page": 4,
                "text": (
                    "样品描述\n"
                    "被检样品信息如下：\n"
                    "序号\n"
                    "部件名称\n"
                    "型号规格\n"
                    "批号/序列号\n"
                    "生产日期\n"
                    "1\n"
                    "一次性使用磁电\n"
                    "定位心脏脉冲电\n"
                    "场消融导管\n"
                    "NavAEPP1206\n"
                    "2BL009\n"
                    "2025-12-03\n"
                    "2\n"
                    "尾线\n"
                    "A1201\n"
                    "2BL010\n"
                    "2025-12-03\n"
                    "以上详见报告照片页"
                ),
            },
            {
                "page": 9,
                "text": "检 验 报 告 照 片 页\n照片和说明\n№2 一次性使用磁电定位心脏脉冲电场消融导管 中文标签",
            },
        ],
    }

    evidence = ReportEvidenceBuilder().build_one("C08", report)["evidence"]

    assert len(evidence["sample_items"]) == 2
    assert evidence["sample_items"][0]["component_name"] == "一次性使用磁电定位心脏脉冲电场消融导管"
    assert evidence["sample_items"][0]["model"] == "NavAEPP1206"
    assert evidence["sample_items"][0]["batch_or_serial"] == "2BL009"
    assert evidence["sample_items"][0]["production_date"] == "2025-12-03"
    assert "NavAEPP1206" in evidence["sample_items"][0]["raw_text"]
    assert "2025-12-03" in evidence["sample_items"][0]["raw_text"]
    assert evidence["sample_items"][0]["source_fields"]["component_name"] == "部件名称"
    assert evidence["sample_items"][0]["source_fields"]["model"] == "型号规格"
    assert evidence["sample_items"][0]["source_fields"]["batch_or_serial"] == "批号/序列号"
    assert evidence["sample_items"][1]["component_name"] == "尾线"
    assert evidence["sample_items"][1]["model"] == "A1201"


def test_c08_sample_header_detection_uses_sequence_header_line_not_preceding_window():
    report = {
        "file_name": "header-window.pdf",
        "pages": [
            {
                "page": 4,
                "text": (
                    "样品描述\n"
                    "上\n"
                    "海\n"
                    "市\n"
                    "医\n"
                    "疗\n"
                    "器\n"
                    "械\n"
                    "序号\n"
                    "部件名称\n"
                    "组件号\n"
                    "批号/序列号\n"
                    "生产日期\n"
                    "1\n"
                    "心脏脉冲电场消融仪（主机）\n"
                    "ASM-00094\n"
                    "2521001CPO\n"
                    "2025/05/21\n"
                    "以上详见照片"
                ),
            },
            {"page": 9, "text": "检 验 报 告 照 片 页\n照片和说明\n№2 心脏脉冲电场消融仪 中文标签样张"},
        ],
    }

    evidence = ReportEvidenceBuilder().build_one("C08", report)["evidence"]

    assert evidence["sample_items"][0]["source_fields"]["component_name"] == "部件名称"
    assert evidence["sample_items"][0]["source_fields"]["model"] == "组件号"
    assert evidence["sample_items"][0]["source_fields"]["batch_or_serial"] == "批号/序列号"


def test_c08_sample_candidates_keep_compact_numeric_production_dates():
    report = {
        "file_name": "compact-date.pdf",
        "pages": [
            {
                "page": 4,
                "text": (
                    "样品描述\n"
                    "序号\n"
                    "部件名称\n"
                    "型号规格\n"
                    "序列号/批号\n"
                    "生产日期\n"
                    "1\n"
                    "消化道脉冲电场\n"
                    "消融仪\n"
                    "RMD01\n"
                    "RMD251206002\n"
                    "20251230\n"
                    "2\n"
                    "等电位线\n"
                    "HWD06-C3-5M\n"
                    "RMD251206002\n"
                    "20251230\n"
                    "以上详见照片"
                ),
            },
            {"page": 9, "text": "检 验 报 告 照 片 页\n照片和说明\n№5 消化道脉冲电场消融仪 主机中文标签"},
        ],
    }

    evidence = ReportEvidenceBuilder().build_one("C08", report)["evidence"]

    assert len(evidence["sample_items"]) == 2
    assert evidence["sample_items"][0]["production_date"] == "20251230"
    assert evidence["sample_items"][1]["production_date"] == "20251230"


def test_c12_rules_treat_sterile_growth_as_sterile_context_evidence():
    c12 = ReportEvidenceBuilder().build_one("C12", load_fixture())

    assert any("无菌生长" in rule and "无菌" in rule and "符合证据" in rule for rule in c12["check_rules"])
    assert any("有菌生长" in rule and "阳性" in rule for rule in c12["check_rules"])


def test_c14_rules_scope_only_inspection_result_table_value_columns():
    c14 = ReportEvidenceBuilder().build_one("C14", load_fixture())

    assert any("只检查检验结果表" in rule for rule in c14["check_rules"])
    assert any("检验结果、单项结论、备注" in rule for rule in c14["check_rules"])
    assert any("首页字段" in rule and "不能作为 finding" in rule for rule in c14["check_rules"])
    assert any("签发日期" in rule and "out of scope" in rule for rule in c14["check_rules"])
    assert any("candidate_empty_field_rows" in rule and "优先审阅" in rule for rule in c14["check_rules"])


def test_c14_candidate_empty_field_rows_include_sterile_result_before_next_sequence():
    report = {
        "file_name": "c14-empty-fields.pdf",
        "pages": [
            {
                "page": 98,
                "text": (
                    "序号\n"
                    "检验项目\n"
                    "技术要求\n"
                    "检验结果\n"
                    "单项结论\n"
                    "备注\n"
                    "163\n"
                    "2.7.7 无菌\n"
                    "导管连接线应无菌。\n"
                    "无菌生长\n"
                    "164 定位精度"
                ),
            }
        ],
    }

    evidence = ReportEvidenceBuilder().build_one("C14", report)["evidence"]

    assert evidence["candidate_empty_field_rows"]
    candidate = evidence["candidate_empty_field_rows"][0]
    assert candidate["page"] == 98
    assert "2.7.7 无菌" in candidate["raw_text"]
    assert "无菌生长" in candidate["nearby_text"]
    assert "164 定位精度" in candidate["nearby_text"]
    assert "单项结论" in candidate["suspected_fields"]


def test_c14_layout_candidates_detect_empty_remark_cell_in_result_row():
    report = {
        "file_name": "c14-empty-remark.pdf",
        "pages": [
            {
                "page": 95,
                "text": (
                    "序号 检验项目 标准条款 标准要求 检验结果 单项结论 备注\n"
                    "157 电气安全 2.15 2.15.1 通用安全 见序号1～118\n"
                    "2.15.2 专用安全 见序号119～156 符合\n"
                    "2.15.3 电磁兼容性 /\n"
                    "此处空白"
                ),
                "layout_words": [
                    {"text": "检验结果", "x0": 405.5, "y0": 183.7, "x1": 447.5, "y1": 194.2},
                    {"text": "单项", "x0": 463.7, "y0": 176.7, "x1": 484.8, "y1": 187.3},
                    {"text": "结论", "x0": 463.7, "y0": 190.4, "x1": 484.8, "y1": 200.9},
                    {"text": "备注", "x0": 511.3, "y0": 183.7, "x1": 532.4, "y1": 194.2},
                    {"text": "157", "x0": 50.9, "y0": 204.5, "x1": 66.7, "y1": 215.1},
                    {"text": "见序号", "x0": 401.5, "y0": 218.2, "x1": 433.1, "y1": 228.8},
                    {"text": "1～", "x0": 435.7, "y0": 218.2, "x1": 451.5, "y1": 228.8},
                    {"text": "118", "x0": 418.6, "y0": 231.7, "x1": 434.4, "y1": 242.2},
                    {"text": "见序号", "x0": 410.7, "y0": 273.2, "x1": 442.3, "y1": 283.7},
                    {"text": "119～156", "x0": 405.5, "y0": 286.6, "x1": 447.5, "y1": 297.2},
                    {"text": "符合", "x0": 463.7, "y0": 293.6, "x1": 484.8, "y1": 304.1},
                    {"text": "/", "x0": 423.9, "y0": 348.5, "x1": 429.1, "y1": 359.1},
                ],
            }
        ],
    }

    evidence = ReportEvidenceBuilder().build_one("C14", report)["evidence"]

    assert evidence["candidate_empty_field_rows"]
    candidate = evidence["candidate_empty_field_rows"][0]
    assert candidate["page"] == 95
    assert candidate["row_no"] == "157"
    assert candidate["suspected_fields"] == ["备注"]
    assert "备注列未见任何内容" in candidate["reason"]


def test_c15_sequence_marker_candidates_detect_missing_and_unexpected_continuation_markers():
    report = {
        "file_name": "c15-continuation-markers.pdf",
        "pages": [
            {
                "page": 89,
                "text": (
                    "序号 检验项目 标准条款 标准要求 检验结果 单项结论 备注\n"
                    "151 ME 设备 201.12.2 可用性\n"
                ),
            },
            {
                "page": 90,
                "text": (
                    "序号 检验项目 标准条款 标准要求 检验结果 单项结论 备注\n"
                    "续 ME 设备 201.12.2 b) 如果在一个手术手柄上\n"
                    "151 的可用性\n"
                    "续 危险输出 201.12.4 增补条款\n"
                    "152 的防护 201.12.4.101 大电流模式的使用\n"
                ),
            },
            {
                "page": 92,
                "text": (
                    "序号 检验项目 标准条款 标准要求 检验结果 单项结论 备注\n"
                    "152 危险输出 201.12.4 201.12.4.4.102 同时激活期间的输出功率\n"
                    "153 ME 设备 201.13 过载\n"
                ),
            },
        ],
    }

    evidence = ReportEvidenceBuilder().build_one("C15", report)["evidence"]

    findings = evidence["continuation_marker_candidates"]
    assert [finding["issue"] for finding in findings] == [
        "unexpected_continuation_marker",
        "missing_continuation_marker",
    ]
    assert findings[0]["sequence"] == 152
    assert findings[0]["page"] == 90
    assert findings[1]["sequence"] == 152
    assert findings[1]["page"] == 92


def test_c15_layout_sequence_markers_ignore_standard_requirement_numbers():
    report = {
        "file_name": "c15-layout-ignores-body-numbers.pdf",
        "pages": [
            {
                "page": 10,
                "text": (
                    "序号 检验项目 标准条款 标准要求 检验结果 单项结论 备注\n"
                    "151 ME 设备 201.12.2 可用性\n"
                    "12 中列出的各项数值\n"
                ),
                "layout_words": [
                    {"text": "检验结果", "x0": 405.5, "y0": 183.7, "x1": 447.5, "y1": 194.2},
                    {"text": "单项", "x0": 463.7, "y0": 176.7, "x1": 484.8, "y1": 187.3},
                    {"text": "结论", "x0": 463.7, "y0": 190.4, "x1": 484.8, "y1": 200.9},
                    {"text": "备注", "x0": 511.3, "y0": 183.7, "x1": 532.4, "y1": 194.2},
                    {"text": "151", "x0": 50.9, "y0": 204.5, "x1": 66.7, "y1": 215.1},
                    {"text": "12", "x0": 181.7, "y0": 245.3, "x1": 192.2, "y1": 255.9},
                ],
            },
            {
                "page": 11,
                "text": (
                    "序号 检验项目 标准条款 标准要求 检验结果 单项结论 备注\n"
                    "152 危险输出 201.12.4 防护\n"
                    "12 中列出的各项数值\n"
                ),
                "layout_words": [
                    {"text": "检验结果", "x0": 405.5, "y0": 183.7, "x1": 447.5, "y1": 194.2},
                    {"text": "单项", "x0": 463.7, "y0": 176.7, "x1": 484.8, "y1": 187.3},
                    {"text": "结论", "x0": 463.7, "y0": 190.4, "x1": 484.8, "y1": 200.9},
                    {"text": "备注", "x0": 511.3, "y0": 183.7, "x1": 532.4, "y1": 194.2},
                    {"text": "152", "x0": 50.9, "y0": 204.5, "x1": 66.7, "y1": 215.1},
                    {"text": "12", "x0": 181.7, "y0": 245.3, "x1": 192.2, "y1": 255.9},
                ],
            },
        ],
    }

    evidence = ReportEvidenceBuilder().build_one("C15", report)["evidence"]

    assert [entry["sequence"] for entry in evidence["sequence_markers"]] == [151, 152]
    assert evidence["continuation_marker_candidates"] == []


@pytest.mark.parametrize(
    "check_id,check_name,required_details",
    [
        ("C00", "文档结构完整性", ["detected_sections", "missing_sections", "section_order_ok"]),
        ("C01", "报告编号与样品编号一致性", ["report_number", "sample_number", "tail_match"]),
        ("C02", "首页基础字段一致性", ["field_comparisons"]),
        ("C03", "首页扩展字段一致性", ["field_comparisons", "see_sample_desc_consistent"]),
        ("C04", "时间逻辑一致性", ["dates", "timeline_checks"]),
        ("C06", "样品描述字段一致性", ["rows"]),
        ("C07", "照片覆盖性", ["components"]),
        ("C08", "样品描述与照片标签一致性", ["sample_items", "label_items", "label_comparisons"]),
        ("C12", "检验结果与单项结论逻辑", ["sequence_results"]),
        ("C13", "单项结论与总结论逻辑", ["overall_conclusion_text", "nonconforming_sequences", "overall_consistent"]),
        ("C14", "非空字段核对", ["rows", "empty_field_rows"]),
        (
            "C15",
            "序号连续性与续表正确性",
            ["sequence_list", "missing_numbers", "duplicate_numbers", "continuation_marker_findings"],
        ),
        ("C16", "页码连续性", ["page_infos", "missing_pages", "duplicate_pages", "total_consistent", "final_page_match"]),
    ],
)
def test_every_approved_check_has_expected_metadata(check_id, check_name, required_details):
    evidence = ReportEvidenceBuilder().build_all(load_fixture())
    item = next(package for package in evidence if package["check_id"] == check_id)

    assert item["check_name"] == check_name
    assert item["required_details"] == required_details
    assert {
        "file_name",
        "pages",
        "cover_text",
        "report_home_text",
        "sample_description_text",
        "inspection_table_text",
        "photo_text",
    }.issubset(item["evidence"].keys())


def test_packages_are_isolated_snapshots():
    fixture = load_fixture()
    evidence = ReportEvidenceBuilder().build_all(fixture)
    c02 = next(package for package in evidence if package["check_id"] == "C02")
    c03 = next(package for package in evidence if package["check_id"] == "C03")

    c02["evidence"]["pages"][0]["text"] = "mutated page text"
    c02["required_details"].append("mutated_detail")

    assert c03["evidence"]["pages"][0]["text"] != "mutated page text"
    assert "mutated_detail" not in c03["required_details"]
    assert fixture["pages"][0]["text"] != "mutated page text"
    assert "mutated_detail" not in next(package for package in evidence if package["check_id"] == "C00")["required_details"]
