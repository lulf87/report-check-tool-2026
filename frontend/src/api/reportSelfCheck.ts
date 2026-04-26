import type { ReportSelfCheckResult, ReportSelfCheckTask } from '../types/reportSelfCheck';

async function readErrorMessage(response: Response): Promise<string> {
  const fallback = '报告自身核对失败';
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
    throw new Error(await readErrorMessage(response));
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
