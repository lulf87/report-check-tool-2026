export type CheckStatus = 'pass' | 'warning' | 'error';
export type Confidence = 'high' | 'medium' | 'low';
export type RecordReportCheckMode = 'quick' | 'full_codex';

export interface RecordReportCheckOptions {
  record_report_mode: RecordReportCheckMode;
  record_report_concurrency: number;
}

export interface Finding {
  severity: 'warning' | 'error';
  title: string;
  detail: string;
  expected?: string | null;
  actual?: string | null;
  pages: number[];
  related_fields: string[];
}

export interface CheckResult {
  check_id: string;
  check_name: string;
  status: CheckStatus;
  confidence: Confidence;
  summary: string;
  details: Record<string, unknown>;
  findings: Finding[];
  evidence: Array<Record<string, unknown>>;
  missing_evidence: Array<Record<string, unknown>>;
}

export interface ReportSelfCheckResult {
  task_id: string;
  file_name: string;
  ptr_file_name?: string;
  record_file_name?: string;
  report_file_name?: string;
  record_report_mode?: RecordReportCheckMode;
  record_report_concurrency?: number;
  homepage_scope?: Record<string, unknown> | null;
  ptr_report_scope_summary?: Record<string, unknown> | null;
  record_report_summary?: Record<string, unknown> | null;
  overall_status: CheckStatus;
  report_meta: {
    report_number: string;
    sample_number: string;
    sample_name: string;
    client: string;
  };
  summary: {
    total_checks: number;
    pass_count: number;
    warning_count: number;
    error_count: number;
  };
  check_results: CheckResult[];
}

export interface PtrReportCheckResult extends ReportSelfCheckResult {}

export interface ReportSelfCheckTask {
  task_id: string;
  file_name: string;
  ptr_file_name?: string;
  record_file_name?: string;
  report_file_name?: string;
  record_report_mode?: RecordReportCheckMode;
  record_report_concurrency?: number;
  homepage_scope?: Record<string, unknown> | null;
  ptr_report_scope_summary?: Record<string, unknown> | null;
  record_report_summary?: Record<string, unknown> | null;
  status: 'running' | 'completed' | 'error';
  current_check_id: string | null;
  current_check_name: string;
  completed_checks: number;
  total_checks: number;
  logs: string[];
  result: ReportSelfCheckResult | null;
  error: string | null;
}
