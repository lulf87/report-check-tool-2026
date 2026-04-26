from app.services.ptr_report_evidence_builder import PtrReportEvidenceBuilder


def _ptr_document() -> dict:
    return {
        "file_name": "PTR.pdf",
        "pages": [
            {"page": 1, "text": "1 概述\n本文件规定产品要求。"},
            {
                "page": 2,
                "text": (
                    "2 性能指标\n"
                    "2.1 外观\n产品表面应光滑。\n"
                    "2.2 尺寸\n导管外径应≤2.0 mm。\n"
                    "2.2.1 有效长度\n有效长度应≥900 mm。\n"
                    "2.3 生物相容性\n应符合相关要求。"
                ),
            },
            {
                "page": 3,
                "text": (
                    "2.5 电气性能\n输出电压应≤1000 V。\n"
                    "2.5.1 脉冲宽度\n脉冲宽度应≥1 ms。\n"
                    "2.6 安全要求\n泄漏电流应≤10 mA。"
                ),
            },
            {"page": 4, "text": "", "image_path": "/tmp/ptr-page-004.png"},
            {"page": 5, "text": "3 试验方法\n按规定方法试验。"},
        ],
    }


def _report_document(scope_text: str | None = "检验项目：2.2、2.5、2.6（除生物相容性、电磁兼容性）") -> dict:
    home_text = "检 验 报 告 首 页\n样品名称：导管\n"
    if scope_text is not None:
        home_text += scope_text

    return {
        "file_name": "report.pdf",
        "pages": [
            {"page": 1, "text": home_text},
            {
                "page": 4,
                "text": (
                    "序号 检验项目 标准要求 检验结果 单项结论\n"
                    "1 2.2 尺寸 导管外径应<2.0 mm 符合 符合\n"
                    "2 2.2.1 有效长度 有效长度应≥900 mm 符合 符合"
                ),
            },
            {
                "page": 5,
                "text": (
                    "序号 检验项目 标准要求 检验结果 单项结论\n"
                    "3 2.5 电气性能 输出电压应≤1000 V 符合 符合\n"
                    "4 2.6 安全要求 泄漏电流应≤10 mA 符合 符合"
                ),
            },
            {"page": 6, "text": "检验报告照片页\n照片和说明"},
        ],
    }


def test_parses_1539_style_home_scope_and_exclusions():
    packages = PtrReportEvidenceBuilder().build_all(_ptr_document(), _report_document())

    package = next(item for item in packages if item["check_id"] == "PTR-2.2")

    assert package["evidence"]["report_scope_text"] == "检验项目：2.2、2.5、2.6（除生物相容性、电磁兼容性）"
    assert package["evidence"]["included_clause_prefixes"] == ["2.2", "2.5", "2.6"]
    assert package["evidence"]["exclusion_texts"] == ["除生物相容性、电磁兼容性"]


def test_parses_spaced_multiline_home_scope_from_pdf_text_extraction():
    report = _report_document(scope_text=None)
    report["pages"][0]["text"] = (
        "检 验 报 告 首 页\n"
        "样品名称：导管\n"
        "检 验 项 目\n"
        "2.2、2.5、2.6（除生物相容性、电磁兼容性）\n"
        "检验依据：PTR"
    )

    packages = PtrReportEvidenceBuilder().build_all(_ptr_document(), report)

    assert [item["check_id"] for item in packages] == ["PTR-2.2", "PTR-2.5", "PTR-2.6"]
    assert packages[0]["evidence"]["report_scope_text"] == "检 验 项 目 2.2、2.5、2.6（除生物相容性、电磁兼容性）"


def test_parses_top_level_range_scope_into_all_declared_prefixes():
    report = _report_document(scope_text="检验项目：2.1～2.4（除电磁兼容性）")

    packages = PtrReportEvidenceBuilder().build_all(_ptr_document(), report)

    assert [item["check_id"] for item in packages] == ["PTR-2.1", "PTR-2.2", "PTR-2.3", "PTR-2.4"]
    assert packages[0]["evidence"]["included_clause_prefixes"] == ["2.1", "2.2", "2.3", "2.4"]
    package_2_2 = next(item for item in packages if item["check_id"] == "PTR-2.2")
    assert [clause["prefix"] for clause in package_2_2["evidence"]["ptr_clauses"]] == ["2.2", "2.2.1"]


def test_detailed_child_range_scope_filters_clauses_inside_top_level_package():
    ptr = _ptr_document()
    ptr["pages"][1]["text"] = (
        "2. 性能指标\n"
        "2.1 基本电性能\n表1 参数表。\n"
        "2.1.1 起搏模式\n模式应符合表1。\n"
        "2.1.2 脉冲幅度\n幅度应≤7.5V。\n"
        "2.1.3 脉冲宽度\n宽度应≥0.1ms。\n"
        "2.1.4 基础频率\n频率应符合表1。\n"
        "2.1.5 磁铁频率\n磁铁频率应符合表1。\n"
        "2.2 功能指标\n功能应正常。"
    )
    report = _report_document(scope_text="检验项目：2.1.2～2.1.4、2.1.5")

    packages = PtrReportEvidenceBuilder().build_all(ptr, report)
    package = next(item for item in packages if item["check_id"] == "PTR-2.1")

    assert [clause["prefix"] for clause in package["evidence"]["ptr_clauses"]] == [
        "2.1",
        "2.1.2",
        "2.1.3",
        "2.1.4",
        "2.1.5",
    ]
    assert "2.1.1" not in [clause["prefix"] for clause in package["evidence"]["ptr_clauses"]]


def test_child_range_candidate_pages_do_not_match_parent_prefix_only_noise():
    ptr = _ptr_document()
    ptr["pages"][1]["text"] = (
        "2. 性能指标\n"
        "2.1 基本电性能\n表1 参数表。\n"
        "2.1.1 起搏模式\n模式应符合表1。\n"
        "2.1.2 脉冲幅度\n幅度应≤7.5V。\n"
        "2.1.3 脉冲宽度\n宽度应≥0.1ms。\n"
        "2.1.4 基础频率\n频率应符合表1。\n"
        "2.1.5 磁铁频率\n磁铁频率应符合表1。\n"
        "2.2 功能指标\n功能应正常。"
    )
    report = _report_document(scope_text="检验项目：2.1.2～2.1.4、2.1.5")
    report["pages"][1] = {
        "page": 7,
        "text": (
            "序号 检验项目 标准要求 检验结果 单项结论\n"
            "1 随机文件 GB 16174.2-2024 中 2.1 条要求 符合 符合"
        ),
    }
    report["pages"][2] = {
        "page": 8,
        "text": (
            "序号 检验项目 标准要求 检验结果 单项结论\n"
            "38 脉冲幅度 2.1.2 幅度应≤7.5V 符合 符合\n"
            "39 脉冲宽度 2.1.3 宽度应≥0.1ms 符合 符合"
        ),
    }

    package = next(item for item in PtrReportEvidenceBuilder().build_all(ptr, report) if item["check_id"] == "PTR-2.1")

    assert [page["page"] for page in package["evidence"]["report_candidate_pages"]] == [8]


def test_scope_coverage_summarizes_declared_actual_and_missing_leaf_clauses():
    ptr = _ptr_document()
    ptr["pages"][1]["text"] = (
        "2. 性能指标\n"
        "2.1 基本电性能\n表1 参数表。\n"
        "2.1.2 脉冲幅度\n幅度应≤7.5V。\n"
        "2.1.3 脉冲宽度\n宽度应≥0.1ms。\n"
        "2.1.4 基础频率\n频率应符合表1。\n"
        "2.2 功能指标\n功能应正常。"
    )
    report = _report_document(scope_text="检验项目：2.1.2～2.1.4")
    report["pages"][1] = {
        "page": 8,
        "text": (
            "序号 检验项目 标准要求 检验结果 单项结论\n"
            "38 脉冲幅度 2.1.2 幅度应≤7.5V 符合 符合\n"
            "40 基础频率 2.1.4 频率应符合表1 符合 符合"
        ),
    }
    report["pages"][2] = {"page": 9, "text": "此处空白"}

    packages = PtrReportEvidenceBuilder().build_all(ptr, report)

    coverage = packages[0]["evidence"]["scope_coverage"]
    assert coverage["declared_clause_prefixes"] == ["2.1.2", "2.1.3", "2.1.4"]
    assert coverage["actual_report_clause_prefixes"] == ["2.1.2", "2.1.4"]
    assert coverage["missing_declared_clause_prefixes"] == ["2.1.3"]


def test_leaf_clause_reviews_include_expanded_report_entry_until_next_clause():
    ptr = _ptr_document()
    ptr["pages"][1]["text"] = (
        "2. 性能指标\n"
        "2.1 基本电性能\n表1 参数表。\n"
        "参数 型号 常规数值 标准设置 允许误差\n"
        "脉冲幅度(V) 全部型号 0.2 ... 7.5 3.0 ±50mV\n"
        "脉冲宽度(ms) 全部型号 0.1 ... 1.5 0.4 ±20μs\n"
        "2.1.2 脉冲幅度\n脉冲幅度应符合表1中的数值。\n"
        "2.1.3 脉冲宽度\n脉冲宽度应符合表1中的数值。\n"
        "2.2 功能指标\n功能应正常。"
    )
    report = _report_document(scope_text="检验项目：2.1.2～2.1.3")
    report["pages"][1] = {
        "page": 8,
        "text": (
            "序号 检验项目 标准要求 检验结果 单项结论\n"
            "38 脉冲幅度 2.1.2 脉冲幅度应符合表1中的数值。\n"
            "脉冲幅度(V)（心房） 常规数值：0.2 ... 7.5\n"
        ),
    }
    report["pages"][2] = {
        "page": 9,
        "text": (
            "序号 检验项目 标准要求 检验结果 单项结论\n"
            "@240Ω 0.2V：±50mV 0.4V～7.5V：+20%/-25%\n"
            "39 脉冲宽度 2.1.3 脉冲宽度应符合表1中的数值。 符合 符合"
        ),
    }

    package = next(item for item in PtrReportEvidenceBuilder().build_all(ptr, report) if item["check_id"] == "PTR-2.1")
    review = next(item for item in package["evidence"]["leaf_clause_reviews"] if item["prefix"] == "2.1.2")

    assert review["report_presence"] == "present"
    assert review["report_entry_pages"] == [8, 9]
    assert "2.1.2 脉冲幅度" in review["ptr_display_text"]
    assert "表 1 对应内容" in review["ptr_display_text"]
    assert "脉冲幅度(V)" in review["ptr_display_text"]
    assert "0.2 ... 7.5" in review["ptr_display_text"]
    assert "脉冲宽度" not in review["ptr_display_text"]
    assert "0.4V～7.5V" in review["report_standard_requirement_text"]
    assert "2.1.3" not in review["report_standard_requirement_text"]


def test_leaf_clause_reviews_match_table_rows_with_acronym_and_particle_variants():
    ptr = _ptr_document()
    ptr["pages"][1]["text"] = (
        "2. 性能指标\n"
        "2.1 基本电性能\n表1 参数表。\n"
        "房室间期(ms) 感知后的房室间期(ms) Edora 8 DR-T 低，中，高，固定，自定义 低 / "
        "20 ... (5) ... 350 180-170-160-150-140 ±20 "
        "PVARP(ms) Edora 8 SR-T 不适用 Edora 8 DR-T 175 ... (25) ... 600 225 ±20 "
        "注释：符号“/”代表不适用。\n"
        "2.1.12 心室后心房不应期（PVARP）\n心室后心房不应期应符合表1中的数值。\n"
        "2.1.15 感知后房室间期\n感知后房室间期应符合表1中的数值。\n"
        "2.2 功能指标\n功能应正常。"
    )
    report = _report_document(scope_text="检验项目：2.1.12、2.1.15")

    package = next(item for item in PtrReportEvidenceBuilder().build_all(ptr, report) if item["check_id"] == "PTR-2.1")
    pvarp = next(item for item in package["evidence"]["leaf_clause_reviews"] if item["prefix"] == "2.1.12")
    sensed_av = next(item for item in package["evidence"]["leaf_clause_reviews"] if item["prefix"] == "2.1.15")

    assert "PVARP(ms)" in pvarp["ptr_display_text"]
    assert "175 ... (25) ... 600" in pvarp["ptr_display_text"]
    assert "注释" not in pvarp["ptr_display_text"]
    assert "感知后的房室间期(ms)" in sensed_av["ptr_display_text"]
    assert "20 ... (5) ... 350" in sensed_av["ptr_display_text"]
    assert "PVARP(ms)" not in sensed_av["ptr_display_text"]


def test_top_level_exact_scope_still_matches_parent_prefix_report_page():
    report = _report_document(scope_text="检验项目：2.2")
    report["pages"][1] = {
        "page": 4,
        "text": "序号 检验项目 标准要求 检验结果 单项结论\n1 尺寸 2.2 导管外径应≤2.0 mm 符合 符合",
    }

    package = next(
        item for item in PtrReportEvidenceBuilder().build_all(_ptr_document(), report) if item["check_id"] == "PTR-2.2"
    )

    assert [page["page"] for page in package["evidence"]["report_candidate_pages"]] == [4]


def test_clause_reference_matching_does_not_match_larger_standard_clause_numbers():
    report = _report_document(scope_text="检验项目：2.2")
    report["pages"][1] = {
        "page": 4,
        "text": "序号 检验项目 标准要求 检验结果 单项结论\n1 随机文件 12.2 应包含产品信息 符合 符合",
    }
    report["pages"][2] = {
        "page": 5,
        "text": "序号 检验项目 标准要求 检验结果 单项结论\n2 尺寸 2.2 导管外径应≤2.0 mm 符合 符合",
    }

    package = next(
        item for item in PtrReportEvidenceBuilder().build_all(_ptr_document(), report) if item["check_id"] == "PTR-2.2"
    )

    assert [page["page"] for page in package["evidence"]["report_candidate_pages"]] == [5]


def test_exclusion_text_matches_common_shorter_clause_title_variant():
    ptr = _ptr_document()
    ptr["pages"][2]["text"] = (
        "2.5 安全要求\n"
        "2.5.1 通用安全要求\n应符合 GB 9706.1。\n"
        "2.5.2 专用安全要求\n应符合 GB 9706.202。\n"
        "2.5.3 电磁兼容\n应符合 YY 9706.102。\n"
        "3 检验方法\n按规定方法试验。"
    )
    report = _report_document(scope_text="检验项目：2.5（除电磁兼容性）")

    package = PtrReportEvidenceBuilder().build_all(ptr, report)[0]

    assert [clause["prefix"] for clause in package["evidence"]["ptr_clauses"]] == ["2.5", "2.5.1", "2.5.2"]


def test_only_builds_packages_for_report_declared_top_level_scope():
    packages = PtrReportEvidenceBuilder().build_all(_ptr_document(), _report_document())

    assert [item["check_id"] for item in packages] == ["PTR-2.2", "PTR-2.5", "PTR-2.6"]
    assert "PTR-2.1" not in [item["check_id"] for item in packages]


def test_2_2_package_includes_ptr_subclauses_and_report_candidate_pages():
    packages = PtrReportEvidenceBuilder().build_all(_ptr_document(), _report_document())
    package = next(item for item in packages if item["check_id"] == "PTR-2.2")

    assert package["check_name"] == "PTR 第 2 章性能指标 vs report 标准要求摘录一致性 - 2.2"
    assert package["required_details"][:4] == [
        "scope_coverage",
        "ptr_clause_prefix",
        "ptr_clauses",
        "leaf_clause_reviews",
    ]
    assert "leaf_clause_comparisons" in package["required_details"]
    assert "report_candidate_pages" in package["required_details"]
    assert "scope_decision" in package["required_details"]
    assert [clause["prefix"] for clause in package["evidence"]["ptr_clauses"]] == ["2.2", "2.2.1"]
    assert package["evidence"]["ptr_clauses"][0]["page"] == 2
    assert any("导管外径应<2.0 mm" in page["text_excerpt"] for page in package["evidence"]["report_candidate_pages"])
    assert package["evidence"]["scope_decision"] == "included_by_report_home_scope"


def test_check_rules_define_standard_requirements_only_and_comparator_strictness():
    packages = PtrReportEvidenceBuilder().build_all(_ptr_document(), _report_document())
    package = next(item for item in packages if item["check_id"] == "PTR-2.2")

    rules = "\n".join(package["check_rules"])
    assert "只核对 report 表格的“标准要求”" in rules
    assert "检验结果/单项结论不参与" in rules
    assert "≥/≤ 与 >/< 差异按不一致" in rules
    assert "report 可展开 PTR 引用表格" in rules
    assert "首页未声明不算缺失" in rules


def test_textless_ptr_pages_are_recorded_without_fabricated_clauses():
    packages = PtrReportEvidenceBuilder().build_all(_ptr_document(), _report_document())
    evidence = packages[0]["evidence"]

    assert evidence["ptr_textless_pages"] == [{"page": 4, "image_path": "/tmp/ptr-page-004.png"}]
    assert all(clause["text"].strip() for package in packages for clause in package["evidence"]["ptr_clauses"])


def test_textless_ptr_page_images_are_attached_for_codex_review():
    packages = PtrReportEvidenceBuilder().build_all(_ptr_document(), _report_document())

    assert "/tmp/ptr-page-004.png" in packages[0]["image_paths"]


def test_missing_report_home_scope_returns_scope_warning_package():
    packages = PtrReportEvidenceBuilder().build_all(_ptr_document(), _report_document(scope_text=None))

    assert len(packages) == 1
    assert packages[0]["check_id"] == "PTR-SCOPE"
    assert packages[0]["evidence"]["scope_decision"] == "insufficient_report_home_scope"
    assert packages[0]["evidence"]["report_scope_text"] == ""
