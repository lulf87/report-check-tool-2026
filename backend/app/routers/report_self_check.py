from pathlib import Path
from shutil import rmtree
from tempfile import NamedTemporaryFile, mkdtemp
from threading import Lock
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Form, HTTPException, UploadFile

from app.config import settings
from app.models.report_self_check import CheckResult
from app.services.pdf_document_loader import PDFDocumentLoader
from app.services.ptr_report_check_service import PtrReportCheckService
from app.services.record_report_check_service import RecordReportCheckService, normalize_record_report_options
from app.services.report_evidence_builder import APPROVED_CHECK_IDS
from app.services.report_self_check_service import ReportSelfCheckService

router = APIRouter()
TASKS: dict[str, dict] = {}
TASKS_LOCK = Lock()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/check")
async def check_report(file: UploadFile):
    extracted = await _load_uploaded_pdf(file)
    try:
        result = ReportSelfCheckService().check_extracted_report(extracted)
        return result.model_dump(mode="json")
    finally:
        _cleanup_extracted_report(extracted)


@router.post("/check/start")
async def start_check_report(file: UploadFile, background_tasks: BackgroundTasks):
    extracted = await _load_uploaded_pdf(file)
    task_id = str(uuid4())
    _set_task(
        task_id,
        {
            "task_id": task_id,
            "file_name": extracted["file_name"],
            "status": "running",
            "current_check_id": None,
            "current_check_name": "等待开始",
            "completed_checks": 0,
            "total_checks": len(APPROVED_CHECK_IDS),
            "logs": ["任务已创建，等待后端开始核对。"],
            "result": None,
            "error": None,
        },
    )
    background_tasks.add_task(_run_check_task, task_id, extracted)
    return _get_task(task_id)


@router.post("/ptr-report/check")
async def check_ptr_report(ptr_file: UploadFile, report_file: UploadFile):
    extracted_ptr, extracted_report = await _load_uploaded_pdf_pair(ptr_file, report_file)
    try:
        result = PtrReportCheckService().check_extracted_pair(extracted_ptr, extracted_report)
        return result.model_dump(mode="json")
    finally:
        _cleanup_extracted_report(extracted_ptr)
        _cleanup_extracted_report(extracted_report)


@router.post("/ptr-report/check/start")
async def start_check_ptr_report(ptr_file: UploadFile, report_file: UploadFile, background_tasks: BackgroundTasks):
    extracted_ptr, extracted_report = await _load_uploaded_pdf_pair(ptr_file, report_file)
    task_id = str(uuid4())
    _set_task(
        task_id,
        {
            "task_id": task_id,
            "file_name": extracted_report["file_name"],
            "ptr_file_name": extracted_ptr["file_name"],
            "report_file_name": extracted_report["file_name"],
            "status": "running",
            "current_check_id": None,
            "current_check_name": "等待开始",
            "completed_checks": 0,
            "total_checks": 0,
            "logs": ["PTR-report 核对任务已创建，等待后端开始核对。"],
            "result": None,
            "error": None,
        },
    )
    background_tasks.add_task(_run_ptr_report_check_task, task_id, extracted_ptr, extracted_report)
    return _get_task(task_id)


@router.post("/record-report/check")
async def check_record_report(
    record_file: UploadFile,
    report_file: UploadFile,
    record_report_mode: str = Form("quick"),
    record_report_concurrency: int = Form(4),
):
    extracted_record, extracted_report = await _load_record_report_pdf_pair(record_file, report_file)
    normalized_mode, normalized_concurrency = normalize_record_report_options(
        record_report_mode,
        record_report_concurrency,
    )
    try:
        result = RecordReportCheckService().check_extracted_pair(
            extracted_record,
            extracted_report,
            record_report_mode=normalized_mode,
            record_report_concurrency=normalized_concurrency,
        )
        return result.model_dump(mode="json")
    finally:
        _cleanup_extracted_report(extracted_record)
        _cleanup_extracted_report(extracted_report)


@router.post("/record-report/check/start")
async def start_check_record_report(
    record_file: UploadFile,
    report_file: UploadFile,
    background_tasks: BackgroundTasks,
    record_report_mode: str = Form("quick"),
    record_report_concurrency: int = Form(4),
):
    extracted_record, extracted_report = await _load_record_report_pdf_pair(record_file, report_file)
    normalized_mode, normalized_concurrency = normalize_record_report_options(
        record_report_mode,
        record_report_concurrency,
    )
    task_id = str(uuid4())
    _set_task(
        task_id,
        {
            "task_id": task_id,
            "file_name": extracted_report["file_name"],
            "record_file_name": extracted_record["file_name"],
            "report_file_name": extracted_report["file_name"],
            "record_report_mode": normalized_mode,
            "record_report_concurrency": normalized_concurrency,
            "status": "running",
            "current_check_id": None,
            "current_check_name": "等待开始",
            "completed_checks": 0,
            "total_checks": 0,
            "logs": [f"record-report 核对任务已创建，模式={normalized_mode}，并发={normalized_concurrency}。"],
            "result": None,
            "error": None,
        },
    )
    background_tasks.add_task(
        _run_record_report_check_task,
        task_id,
        extracted_record,
        extracted_report,
        normalized_mode,
        normalized_concurrency,
    )
    return _get_task(task_id)


@router.get("/tasks/{task_id}")
def get_check_task(task_id: str):
    task = _get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


async def _load_uploaded_pdf(file: UploadFile) -> dict:
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    render_dir = Path(mkdtemp(prefix="report-self-check-pages-")) if settings.render_pages else None
    try:
        with NamedTemporaryFile(suffix=".pdf", delete=True) as tmp:
            tmp.write(await file.read())
            tmp.flush()
            try:
                extracted = PDFDocumentLoader().load(Path(tmp.name), render_dir=render_dir)
            except Exception as exc:
                raise HTTPException(status_code=400, detail="Invalid PDF file") from exc
            extracted["file_name"] = file.filename
            extracted["_render_dir"] = str(render_dir) if render_dir is not None else ""
            return extracted
    except Exception:
        if render_dir is not None:
            rmtree(render_dir, ignore_errors=True)
        raise


async def _load_uploaded_pdf_pair(ptr_file: UploadFile, report_file: UploadFile) -> tuple[dict, dict]:
    extracted_ptr = None
    extracted_report = None
    try:
        extracted_ptr = await _load_uploaded_pdf_with_options(ptr_file, render_textless_pages=True)
        extracted_report = await _load_uploaded_pdf_with_options(report_file, render_textless_pages=False)
        return extracted_ptr, extracted_report
    except Exception:
        if extracted_ptr is not None:
            _cleanup_extracted_report(extracted_ptr)
        if extracted_report is not None:
            _cleanup_extracted_report(extracted_report)
        raise


async def _load_record_report_pdf_pair(record_file: UploadFile, report_file: UploadFile) -> tuple[dict, dict]:
    extracted_record = None
    extracted_report = None
    try:
        extracted_record = await _load_uploaded_pdf_with_options(record_file, render_textless_pages=False)
        extracted_report = await _load_uploaded_pdf_with_options(report_file, render_textless_pages=False)
        return extracted_record, extracted_report
    except Exception:
        if extracted_record is not None:
            _cleanup_extracted_report(extracted_record)
        if extracted_report is not None:
            _cleanup_extracted_report(extracted_report)
        raise


async def _load_uploaded_pdf_with_options(file: UploadFile, render_textless_pages: bool) -> dict:
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    render_dir = Path(mkdtemp(prefix="report-self-check-pages-")) if settings.render_pages else None
    try:
        with NamedTemporaryFile(suffix=".pdf", delete=True) as tmp:
            tmp.write(await file.read())
            tmp.flush()
            try:
                extracted = PDFDocumentLoader().load(
                    Path(tmp.name),
                    render_dir=render_dir,
                    render_textless_pages=render_textless_pages,
                )
            except Exception as exc:
                raise HTTPException(status_code=400, detail="Invalid PDF file") from exc
            extracted["file_name"] = file.filename
            extracted["_render_dir"] = str(render_dir) if render_dir is not None else ""
            return extracted
    except Exception:
        if render_dir is not None:
            rmtree(render_dir, ignore_errors=True)
        raise


def _run_check_task(task_id: str, extracted: dict) -> None:
    def update_progress(event: dict) -> None:
        package = event["package"]
        check_id = str(package["check_id"])
        check_name = str(package["check_name"])
        if event["event"] == "start":
            _update_task(
                task_id,
                status="running",
                current_check_id=check_id,
                current_check_name=check_name,
                logs=[f"[{event['index']:02d}/{event['total']}] 开始 {check_id} {check_name}"],
            )
            return

        result: CheckResult = event["result"]
        _update_task(
            task_id,
            completed_checks=event["index"],
            current_check_id=check_id,
            current_check_name=check_name,
            logs=[
                (
                    f"[{event['index']:02d}/{event['total']}] 完成 {check_id} {check_name}："
                    f"{result.status}，findings={len(result.findings)}，missing={len(result.missing_evidence)}"
                )
            ],
        )

    try:
        result = ReportSelfCheckService().check_extracted_report(
            extracted,
            task_id=task_id,
            progress_callback=update_progress,
        )
    except Exception as exc:
        _update_task(task_id, status="error", error=str(exc), logs=[f"任务失败：{exc}"])
        _cleanup_extracted_report(extracted)
        return

    _update_task(
        task_id,
        status="completed",
        completed_checks=len(result.check_results),
        current_check_id=None,
        current_check_name="已完成",
        result=result.model_dump(mode="json"),
        logs=[f"全部 {len(result.check_results)} 项核对已完成。"],
    )
    _cleanup_extracted_report(extracted)


def _run_ptr_report_check_task(task_id: str, extracted_ptr: dict, extracted_report: dict) -> None:
    def update_progress(event: dict) -> None:
        package = event["package"]
        check_id = str(package["check_id"])
        check_name = str(package["check_name"])
        if event["event"] == "start":
            _update_task(
                task_id,
                status="running",
                total_checks=event["total"],
                current_check_id=check_id,
                current_check_name=check_name,
                logs=[f"[{event['index']:02d}/{event['total']}] 开始 PTR-report {check_id} {check_name}"],
            )
            return

        result: CheckResult = event["result"]
        _update_task(
            task_id,
            total_checks=event["total"],
            completed_checks=event["index"],
            current_check_id=check_id,
            current_check_name=check_name,
            logs=[
                (
                    f"[{event['index']:02d}/{event['total']}] 完成 PTR-report {check_id} {check_name}："
                    f"{result.status}，findings={len(result.findings)}，missing={len(result.missing_evidence)}"
                )
            ],
        )

    try:
        result = PtrReportCheckService().check_extracted_pair(
            extracted_ptr,
            extracted_report,
            task_id=task_id,
            progress_callback=update_progress,
        )
    except Exception as exc:
        _update_task(task_id, status="error", error=str(exc), logs=[f"PTR-report 核对任务失败：{exc}"])
        _cleanup_extracted_report(extracted_ptr)
        _cleanup_extracted_report(extracted_report)
        return

    _update_task(
        task_id,
        status="completed",
        total_checks=len(result.check_results),
        completed_checks=len(result.check_results),
        current_check_id=None,
        current_check_name="已完成",
        result=result.model_dump(mode="json"),
        logs=[f"PTR-report 全部 {len(result.check_results)} 项核对已完成。"],
    )
    _cleanup_extracted_report(extracted_ptr)
    _cleanup_extracted_report(extracted_report)


def _run_record_report_check_task(
    task_id: str,
    extracted_record: dict,
    extracted_report: dict,
    record_report_mode: str = "quick",
    record_report_concurrency: int = 4,
) -> None:
    def update_progress(event: dict) -> None:
        package = event["package"]
        check_id = str(package["check_id"])
        check_name = str(package["check_name"])
        if event["event"] == "start":
            _update_task(
                task_id,
                status="running",
                total_checks=event["total"],
                current_check_id=check_id,
                current_check_name=check_name,
                logs=[f"[{event['index']:02d}/{event['total']}] 开始 record-report {check_id} {check_name}"],
            )
            return

        result: CheckResult = event["result"]
        completed_checks = int(event.get("completed") or event["index"])
        cache_text = "，cache=hit" if event.get("cached") else ""
        _update_task(
            task_id,
            total_checks=event["total"],
            completed_checks=completed_checks,
            current_check_id=check_id,
            current_check_name=check_name,
            logs=[
                (
                    f"[{event['index']:02d}/{event['total']}] 完成 record-report {check_id} {check_name}："
                    f"{result.status}，findings={len(result.findings)}，missing={len(result.missing_evidence)}{cache_text}"
                )
            ],
        )

    try:
        result = RecordReportCheckService().check_extracted_pair(
            extracted_record,
            extracted_report,
            task_id=task_id,
            progress_callback=update_progress,
            record_report_mode=record_report_mode,
            record_report_concurrency=record_report_concurrency,
        )
    except Exception as exc:
        _update_task(task_id, status="error", error=str(exc), logs=[f"record-report 核对任务失败：{exc}"])
        _cleanup_extracted_report(extracted_record)
        _cleanup_extracted_report(extracted_report)
        return

    _update_task(
        task_id,
        status="completed",
        total_checks=len(result.check_results),
        completed_checks=len(result.check_results),
        current_check_id=None,
        current_check_name="已完成",
        result=result.model_dump(mode="json"),
        logs=[f"record-report 全部 {len(result.check_results)} 项核对已完成。"],
    )
    _cleanup_extracted_report(extracted_record)
    _cleanup_extracted_report(extracted_report)


def _get_task(task_id: str) -> dict | None:
    with TASKS_LOCK:
        task = TASKS.get(task_id)
        return task.copy() if task is not None else None


def _set_task(task_id: str, task: dict) -> None:
    with TASKS_LOCK:
        TASKS[task_id] = task


def _update_task(task_id: str, logs: list[str] | None = None, **updates) -> None:
    with TASKS_LOCK:
        task = TASKS[task_id]
        if logs:
            task["logs"] = [*task.get("logs", []), *logs][-200:]
        task.update(updates)


def _cleanup_extracted_report(extracted: dict) -> None:
    render_dir = extracted.get("_render_dir")
    if render_dir:
        rmtree(str(render_dir), ignore_errors=True)
