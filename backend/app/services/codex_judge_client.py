import json
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Protocol

from app.config import settings
from app.models.report_self_check import CheckResult, CheckStatus, Confidence, MissingEvidence


class CodexJudgeRuntimeError(RuntimeError):
    pass


class JudgeTransport(Protocol):
    def send(self, prompt: str, schema_path: Path, image_paths: list[str] | None = None) -> str:
        raise NotImplementedError


class StaticJudgeTransport:
    def __init__(self, response: str):
        self.response = response

    def send(self, prompt: str, schema_path: Path, image_paths: list[str] | None = None) -> str:
        return self.response


class CodexCliTransport:
    def build_command(
        self,
        schema_path: Path,
        output_path: Path | None = None,
        image_paths: list[str] | None = None,
    ) -> list[str]:
        command = [
            settings.codex_command,
            "exec",
            "--sandbox",
            "read-only",
        ]
        if settings.codex_model:
            command.extend(["--model", settings.codex_model])
        if settings.codex_reasoning_effort:
            command.extend(["--config", f'model_reasoning_effort="{settings.codex_reasoning_effort}"'])
        if settings.codex_use_output_schema:
            command.extend(["--output-schema", str(schema_path)])
        if output_path is not None:
            command.extend(["--output-last-message", str(output_path)])
        for image_path in image_paths or []:
            command.extend(["--image", image_path])
        command.append("-")
        return command

    def send(self, prompt: str, schema_path: Path, image_paths: list[str] | None = None) -> str:
        with TemporaryDirectory(prefix="report-self-check-codex-") as tmp_dir:
            output_path = Path(tmp_dir) / "last-message.json"
            completed = subprocess.run(
                self.build_command(schema_path, output_path, image_paths),
                input=prompt,
                text=True,
                capture_output=True,
                timeout=settings.codex_timeout_seconds,
                check=False,
            )
            if completed.returncode != 0:
                raise RuntimeError(_compact_cli_error(completed.stderr, completed.stdout))
            if output_path.exists():
                output = output_path.read_text(encoding="utf-8").strip()
                if output:
                    return output
            return completed.stdout.strip()


class CodexJudgeClient:
    def __init__(self, transport: JudgeTransport | None = None):
        self.transport = transport or CodexCliTransport()
        self.schema_path = Path(__file__).resolve().parents[1] / "schemas" / "codex_check_result.schema.json"

    def judge(self, evidence_package: dict) -> CheckResult:
        prompt = self._build_prompt(evidence_package)
        image_paths = [str(path) for path in evidence_package.get("image_paths", []) if path]
        try:
            raw = self.transport.send(prompt, self.schema_path, image_paths)
        except Exception as exc:
            raise CodexJudgeRuntimeError(f"Codex 调用失败：{exc}") from exc

        try:
            payload = json.loads(raw)
            return CheckResult.model_validate(payload)
        except Exception as exc:
            return CheckResult(
                check_id=str(evidence_package.get("check_id", "")),
                check_name=str(evidence_package.get("check_name", "")),
                status=CheckStatus.WARNING,
                confidence=Confidence.LOW,
                summary="Codex 判断结果无法解析，需人工复核。",
                missing_evidence=[
                    MissingEvidence(
                        label="codex_json",
                        reason=str(exc),
                        expected_source="Codex JSON output",
                    )
                ],
            )

    def _build_prompt(self, evidence_package: dict) -> str:
        check_id = str(evidence_package.get("check_id", ""))
        check_name = str(evidence_package.get("check_name", ""))
        required_details = evidence_package.get("required_details", [])
        check_rules = evidence_package.get("check_rules", [])
        if check_id.startswith("PTR-"):
            role_description = (
                "你是医疗器械 PTR 产品技术要求与检验报告标准要求摘录一致性的判断器。"
                "本轮只判断 report 检验项目表中的标准要求是否完整、一致地摘录 PTR 第 2 章中首页声明范围内的要求。"
            )
            image_description = "如果本轮附加了图片，你必须把附加图片作为原 PTR 扫描页证据一起审阅。"
        elif check_id.startswith("RECORD-REPORT-"):
            evidence = evidence_package.get("evidence") if isinstance(evidence_package.get("evidence"), dict) else {}
            standard = str(evidence.get("record_report_standard") or "")
            standard_text = "GB 9706.202-2021" if standard == "gb9706_202" else "GB 9706.1-2020"
            source_text = (
                "原始记录判定可能来自实测数据、备注、手写符号或程序抽取的符号判断。"
                if standard == "gb9706_202"
                else "原始记录判定来自对应条款小项的勾选判定。"
            )
            deterministic_guidance = (
                "判定优先级：必须先看 evidence.deterministic_issues、evidence.report_judgement "
                "和 evidence.record_aggregate_judgement。"
                "如果 deterministic_issues 为空，且 report_judgement 与 record_aggregate_judgement 一致，"
                "必须输出 pass，findings 和 missing_evidence 必须为空；"
                "不得仅因兜底映射、OCR 条款号差异、父条款覆盖分支条款或未逐字列出每个分支条款而输出 warning。"
                "如果 deterministic_issues 包含 mismatch，必须输出 error。"
                "如果 deterministic_issues 包含 record_evidence_missing、record_judgement_missing、"
                "report_judgement_missing 或其他缺失/不确定项，才输出 warning。"
            )
            if standard == "gb9706_202":
                deterministic_guidance += (
                    "对 GB 9706.202-2021，mapping_method 为 parent_clause_sequence 或 sequence_fallback "
                    "是程序允许的映射方式；只要双方聚合判定一致且 deterministic_issues 为空，"
                    "这些映射方式本身不是风险。报告标准条款为 201.x.x 父条款时，"
                    "可按对应原始记录序号下的所有分支条款整体核对，不要求每个 OCR 分支条款完全同号。"
                )
            role_description = (
                "你是医疗器械原始记录与检验报告判定一致性的判断器。"
                f"本轮只判断一个 report 序号的 {standard_text} 单项结论是否与原始记录对应条款小项一致。"
                f"{source_text}{deterministic_guidance}"
            )
            image_description = "如果本轮附加了图片，你必须把附加图片作为原始记录或报告 PDF 页面证据一起审阅。"
        else:
            role_description = "你是医疗器械检验报告内部核对的判断器。"
            image_description = "如果本轮附加了图片，你必须把附加图片作为原 PDF 照片页证据一起审阅。"
        return (
            f"{role_description}"
            "只能依据输入证据判断，不得编造证据。"
            f"{image_description}"
            "请只输出一个 JSON 对象，不要输出 Markdown、代码块或解释性正文。\n\n"
            "输出 JSON 必须严格使用以下顶层字段，不能使用 verdict、issues 等替代字段：\n"
            "{\n"
            f'  "check_id": "{check_id}",\n'
            f'  "check_name": "{check_name}",\n'
            '  "status": "pass | warning | error",\n'
            '  "confidence": "high | medium | low",\n'
            '  "summary": "一句中文结论",\n'
            '  "details": {},\n'
            '  "findings": [],\n'
            '  "evidence": [],\n'
            '  "missing_evidence": []\n'
            "}\n\n"
            "字段要求：\n"
            "- status 只能是 pass、warning、error。\n"
            "- confidence 只能是 high、medium、low。\n"
            "- details 必须是对象，并且至少包含证据包 required_details 中列出的明细键；"
            "如果某个明细无法判断，也要在 details 中给出空数组、null 或说明对象。\n"
            "- findings 必须是数组。每个问题对象必须包含 severity、title、detail、pages、related_fields；"
            "severity 只能是 warning 或 error。\n"
            "- evidence 必须是数组。应尽量列出用于判定的原 PDF 原文证据；"
            "非空时每项至少包含 source、page、label、value，其中 value 必须是原 PDF 摘录，不要填 null。\n"
            "- missing_evidence 必须是数组。可以为空；非空时每项至少包含 label 和 reason。\n"
            f"- 本项 required_details 为：{json.dumps(required_details, ensure_ascii=False)}。\n\n"
            f"本项核对规则必须遵守：{json.dumps(check_rules, ensure_ascii=False)}。\n\n"
            f"核对证据包：\n{json.dumps(evidence_package, ensure_ascii=False, indent=2)}"
        )


def _compact_cli_error(stderr: str, stdout: str) -> str:
    text = "\n".join(part.strip() for part in [stderr, stdout] if part.strip())
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    priority_lines = [
        line
        for line in lines
        if line.startswith("ERROR:")
        or "The model" in line
        or "does not exist" in line
        or "not have access" in line
        or "stream disconnected" in line
    ]
    selected = priority_lines[-4:] or lines[-8:]
    message = "\n".join(selected)
    return message[:1200] or "Codex CLI exited with a non-zero status"
