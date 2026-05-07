import type { RecordReportCheckOptions, ReportSelfCheckResult, ReportSelfCheckTask } from '../types/reportSelfCheck';

async function readErrorMessage(response: Response, fallback = '报告自身核对失败'): Promise<string> {
  const contentType = response.headers.get('content-type') ?? '';

  if (contentType.includes('application/json')) {
    const body: unknown = await response.json();

    if (body && typeof body === 'object' && 'detail' in body) {
      const detail = (body as { detail: unknown }).detail;

      if (typeof detail === 'string' && detail) {
        return detail;
      }
    }

    return fallback;
  }

  const message = await response.text();
  return message || fallback;
}

export async function runReportSelfCheck(file: File): Promise<ReportSelfCheckResult> {
  const formData = new FormData();
  formData.append('file', file);

  const response = await fetch('/api/report-self-check/check', {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    throw new Error(await readErrorMessage(response));
  }

  return response.json() as Promise<ReportSelfCheckResult>;
}

export async function startReportSelfCheck(file: File): Promise<ReportSelfCheckTask> {
  const formData = new FormData();
  formData.append('file', file);

  const response = await fetch('/api/report-self-check/check/start', {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    throw new Error(await readErrorMessage(response));
  }

  return response.json() as Promise<ReportSelfCheckTask>;
}

export async function startPtrReportCheck(ptrFile: File, reportFile: File): Promise<ReportSelfCheckTask> {
  const formData = new FormData();
  formData.append('ptr_file', ptrFile);
  formData.append('report_file', reportFile);

  const response = await fetch('/api/report-self-check/ptr-report/check/start', {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    throw new Error(await readErrorMessage(response, 'PTR 与报告核对失败'));
  }

  return response.json() as Promise<ReportSelfCheckTask>;
}

export async function startRecordReportCheck(
  recordFile: File,
  reportFile: File,
  options: RecordReportCheckOptions = {
    record_report_standard: 'gb9706_1',
    record_report_mode: 'quick',
    record_report_concurrency: 4,
  },
): Promise<ReportSelfCheckTask> {
  const formData = new FormData();
  formData.append('record_file', recordFile);
  formData.append('report_file', reportFile);
  formData.append('record_report_standard', options.record_report_standard);
  formData.append('record_report_mode', options.record_report_mode);
  formData.append('record_report_concurrency', String(options.record_report_concurrency));

  const response = await fetch('/api/report-self-check/record-report/check/start', {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    throw new Error(await readErrorMessage(response, '原始记录与报告核对失败'));
  }

  return response.json() as Promise<ReportSelfCheckTask>;
}

export async function getReportSelfCheckTask(taskId: string): Promise<ReportSelfCheckTask> {
  const response = await fetch(`/api/report-self-check/tasks/${taskId}`);

  if (!response.ok) {
    throw new Error(await readErrorMessage(response));
  }

  return response.json() as Promise<ReportSelfCheckTask>;
}
