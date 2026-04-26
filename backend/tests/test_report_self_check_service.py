import json
from pathlib import Path
from typing import Any

from app.models.report_self_check import CheckResult, CheckStatus, Confidence
from app.services.report_self_check_service import ReportSelfCheckService


FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


class FakeJudgeClient:
    def __init__(self):
        self.packages: list[dict[str, Any]] = []

    def judge(self, package: dict[str, Any]) -> CheckResult:
        self.packages.append(package)
        return CheckResult(
            check_id=str(package["check_id"]),
            check_name=str(package["check_name"]),
            status=CheckStatus.PASS,
            confidence=Confidence.HIGH,
            summary="fake pass",
            details={
                "package_check_id": package["check_id"],
                "required_details": package["required_details"],
                "field_comparisons": [
                    {
                        "field": "样品名称",
                        "source_a_name": "封面",
                        "source_a_value": "射频脉冲电场消融系统",
                        "source_b_name": "检验报告首页",
                        "source_b_value": "射频脉冲电场消融系统",
                        "matched": True,
                        "judgement": "一致",
                    }
                ],
            },
            evidence=[{"source": "page 3 report_home_text", "page": None, "label": "首页", "value": None}],
        )


def load_minimal_report() -> dict[str, Any]:
    return json.loads((FIXTURES_DIR / "minimal_report_pages.json").read_text(encoding="utf-8"))


def test_service_returns_thirteen_judged_checks_with_summary_and_details():
    judge_client = FakeJudgeClient()
    service = ReportSelfCheckService(judge_client=judge_client)

    result = service.check_extracted_report(load_minimal_report(), task_id="task-1")

    assert result.task_id == "task-1"
    assert result.file_name == "minimal.pdf"
    assert len(result.check_results) == 13
    assert len(judge_client.packages) == 13
    assert result.summary.total_checks == 13
    assert result.summary.pass_count == 13
    assert result.summary.warning_count == 0
    assert result.summary.error_count == 0
    assert result.overall_status == CheckStatus.PASS
    assert result.check_results[0].details["package_check_id"] == "C00"
    assert result.check_results[0].details["field_comparisons"][0]["field"] == "样品名称"
    assert result.check_results[0].evidence[0].page == 3
    assert "检验报告首页" in result.check_results[0].evidence[0].value


def test_service_promotes_deterministic_c14_and_c15_candidates_to_warnings():
    report = {
        "file_name": "deterministic-table-issues.pdf",
        "pages": [
            {
                "page": 89,
                "text": "序号 检验项目 标准条款 标准要求 检验结果 单项结论 备注\n151 ME 设备 201.12.2 可用性",
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
                ),
            },
            {
                "page": 95,
                "text": (
                    "序号 检验项目 标准条款 标准要求 检验结果 单项结论 备注\n"
                    "157 电气安全 2.15 2.15.3 电磁兼容性 /\n"
                    "此处空白"
                ),
                "layout_words": [
                    {"text": "检验结果", "x0": 405.5, "y0": 183.7, "x1": 447.5, "y1": 194.2},
                    {"text": "单项", "x0": 463.7, "y0": 176.7, "x1": 484.8, "y1": 187.3},
                    {"text": "结论", "x0": 463.7, "y0": 190.4, "x1": 484.8, "y1": 200.9},
                    {"text": "备注", "x0": 511.3, "y0": 183.7, "x1": 532.4, "y1": 194.2},
                    {"text": "157", "x0": 50.9, "y0": 204.5, "x1": 66.7, "y1": 215.1},
                    {"text": "/", "x0": 423.9, "y0": 348.5, "x1": 429.1, "y1": 359.1},
                    {"text": "符合", "x0": 463.7, "y0": 293.6, "x1": 484.8, "y1": 304.1},
                ],
            },
        ],
    }
    service = ReportSelfCheckService(judge_client=FakeJudgeClient())

    result = service.check_extracted_report(report, task_id="task-table")

    c14 = next(item for item in result.check_results if item.check_id == "C14")
    c15 = next(item for item in result.check_results if item.check_id == "C15")
    assert c14.status == CheckStatus.WARNING
    assert c15.status == CheckStatus.WARNING
    assert any("备注" in finding.title for finding in c14.findings)
    assert any("续" in finding.title for finding in c15.findings)
    assert result.summary.warning_count == 2
    assert result.overall_status == CheckStatus.WARNING
