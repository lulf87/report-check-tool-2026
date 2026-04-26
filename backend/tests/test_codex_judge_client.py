from pathlib import Path

from app.config import settings
from app.models.report_self_check import CheckStatus
import pytest

from app.services.codex_judge_client import CodexCliTransport, CodexJudgeClient, CodexJudgeRuntimeError, StaticJudgeTransport


FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"


class FailingTransport:
    def send(self, prompt: str, schema_path: Path, image_paths: list[str] | None = None) -> str:
        raise RuntimeError("model unavailable")


def test_client_parses_valid_codex_json():
    payload = (FIXTURE_DIR / "codex_c02_pass.json").read_text(encoding="utf-8")
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


def test_client_converts_schema_validation_error_to_warning():
    client = CodexJudgeClient(transport=StaticJudgeTransport('{"check_id": "C12"}'))

    result = client.judge({"check_id": "C12", "check_name": "检验结果与单项结论逻辑", "evidence": {}})

    assert result.check_id == "C12"
    assert result.check_name == "检验结果与单项结论逻辑"
    assert result.status == CheckStatus.WARNING
    assert result.missing_evidence[0].expected_source == "Codex JSON output"


def test_client_raises_runtime_error_for_transport_failure():
    client = CodexJudgeClient(transport=FailingTransport())

    with pytest.raises(CodexJudgeRuntimeError, match="model unavailable"):
        client.judge({"check_id": "C02", "check_name": "首页基础字段一致性", "evidence": {}})


def test_prompt_requires_common_check_result_contract():
    prompt = CodexJudgeClient(transport=StaticJudgeTransport("{}"))._build_prompt(
        {
            "check_id": "C02",
            "check_name": "首页基础字段一致性",
            "required_details": ["field_comparisons"],
            "check_rules": ["示例规则"],
            "evidence": {},
        }
    )

    assert '"status": "pass | warning | error"' in prompt
    assert '"details": {}' in prompt
    assert '"findings": []' in prompt
    assert "不能使用 verdict、issues" in prompt
    assert "field_comparisons" in prompt
    assert "value 必须是原 PDF 摘录" in prompt
    assert "示例规则" in prompt


def test_prompt_uses_ptr_report_role_for_ptr_packages():
    prompt = CodexJudgeClient(transport=StaticJudgeTransport("{}"))._build_prompt(
        {
            "check_id": "PTR-2.2",
            "check_name": "PTR 第 2 章性能指标 vs report 标准要求摘录一致性 - 2.2",
            "required_details": ["ptr_clauses", "report_candidate_pages"],
            "check_rules": ["只核对标准要求"],
            "evidence": {},
        }
    )

    assert "PTR" in prompt
    assert "检验报告标准要求摘录一致性" in prompt
    assert "报告内部核对" not in prompt.split("。", maxsplit=1)[0]


def test_codex_cli_command_uses_supported_read_only_last_message_flags(monkeypatch):
    monkeypatch.setattr(settings, "codex_model", "gpt-test")
    monkeypatch.setattr(settings, "codex_reasoning_effort", "low")
    monkeypatch.setattr(settings, "codex_use_output_schema", False)
    schema_path = Path("/tmp/codex_check_result.schema.json")
    output_path = Path("/tmp/codex-last-message.json")

    command = CodexCliTransport().build_command(schema_path, output_path)

    assert "--ask-for-approval" not in command
    assert command[command.index("--sandbox") + 1] == "read-only"
    assert "--output-schema" not in command
    assert command[command.index("--output-last-message") + 1] == str(output_path)
    assert command[-1] == "-"
    assert command[command.index("--model") + 1] == "gpt-test"
    assert command[command.index("--config") + 1] == 'model_reasoning_effort="low"'
    assert command.index("--model") < command.index("-")


def test_codex_cli_command_attaches_images_after_output_path(monkeypatch):
    monkeypatch.setattr(settings, "codex_model", "gpt-test")
    monkeypatch.setattr(settings, "codex_reasoning_effort", "")
    monkeypatch.setattr(settings, "codex_use_output_schema", False)
    schema_path = Path("/tmp/codex_check_result.schema.json")
    output_path = Path("/tmp/codex-last-message.json")

    command = CodexCliTransport().build_command(schema_path, output_path, ["/tmp/page-001.png"])

    assert command[command.index("--image") + 1] == "/tmp/page-001.png"
    assert command.index("--image") < command.index("-")


def test_codex_cli_command_can_opt_into_output_schema(monkeypatch):
    monkeypatch.setattr(settings, "codex_model", "")
    monkeypatch.setattr(settings, "codex_reasoning_effort", "")
    monkeypatch.setattr(settings, "codex_use_output_schema", True)
    schema_path = Path("/tmp/codex_check_result.schema.json")

    command = CodexCliTransport().build_command(schema_path)

    assert command[command.index("--output-schema") + 1] == str(schema_path)
