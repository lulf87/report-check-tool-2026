import type { CheckResult } from '../../types/reportSelfCheck';
import { FindingsList } from './FindingsList';
import {
  compactDiagnostic,
  extractActionableDiagnostic,
  formatConfidence,
  formatStatus,
  hasOnlyCodexDiagnostics,
  isCodexDiagnosticRecord,
} from './display';

function readableTitle(item: Record<string, unknown>, index: number) {
  const label = String(item.label ?? item.source ?? item.title ?? '').trim();
  if (label === 'codex_json') return '系统返回结果解析失败';
  return label || `证据 ${index + 1}`;
}

function readableText(value: unknown, fallback = '') {
  if (value === null || value === undefined || value === '') return fallback;
  if (typeof value === 'string') return value;
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  return '包含结构化数据，已收起在技术诊断中。';
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

function recordsFrom(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? value.filter(isRecord) : [];
}

function textFrom(value: unknown, fallback = '未提取到内容') {
  const text = readableText(value, fallback).trim();
  return text || fallback;
}

function findLeafComparison(check: CheckResult, prefix: string) {
  return recordsFrom(check.details.leaf_clause_comparisons).find((item) => String(item.prefix ?? item.ptr_clause_prefix ?? '') === prefix);
}

function renderPages(value: unknown) {
  const pages = Array.isArray(value) ? value.map((item) => String(item)).filter(Boolean) : [];
  return pages.length > 0 ? `报告第 ${pages.join('、')} 页` : '报告未检出';
}

function comparisonText(value: Record<string, unknown> | undefined) {
  if (!value) return '';
  return textFrom(value.judgement ?? value.summary ?? value.status, '');
}

function PtrClauseComparisonList({ check }: { check: CheckResult }) {
  const reviews = recordsFrom(check.details.leaf_clause_reviews);
  if (reviews.length === 0) return null;

  return (
    <section className="ptr-clause-list">
      <h4>PTR 与报告内容对照</h4>
      {reviews.map((review, index) => {
        const prefix = String(review.prefix ?? '');
        const comparison = findLeafComparison(check, prefix);
        const reportMissing = review.report_presence === 'missing';
        const ptrText = textFrom(review.ptr_display_text ?? review.ptr_requirement_text);
        const reportText = reportMissing
          ? '报告中未检出该条款。'
          : textFrom(review.report_display_text ?? review.report_standard_requirement_text);

        return (
          <div className={`ptr-clause-row ${reportMissing ? 'missing' : ''}`} key={`${prefix}-${index}`}>
            <header>
              <div>
                <strong>
                  {prefix} {String(review.title ?? '')}
                </strong>
                <span>{renderPages(review.report_entry_pages)}</span>
              </div>
              {comparisonText(comparison) ? <small>{comparisonText(comparison)}</small> : null}
            </header>
            <div className="ptr-clause-columns">
              <section>
                <h5>PTR 内容</h5>
                <pre>{ptrText}</pre>
              </section>
              <section>
                <h5>报告内容</h5>
                <pre>{reportText}</pre>
              </section>
            </div>
          </div>
        );
      })}
    </section>
  );
}

function RecordReportComparisonPanel({ check }: { check: CheckResult }) {
  const entries = recordsFrom(check.details.record_entries);
  const sequence = readableText(check.details.sequence, '');
  const clause = readableText(check.details.report_standard_clause, '');
  const reportPage = readableText(check.details.report_page, '');
  const recordJudgement = readableText(check.details.record_aggregate_judgement, '缺失');
  const reportJudgement = readableText(check.details.report_judgement, '缺失');
  const reportRequirement = textFrom(check.details.report_standard_requirement, '未提取到报告标准要求');

  return (
    <section className="record-report-panel">
      <header>
        <div>
          <h4>序号级核对明细</h4>
          <p>
            序号 {sequence || '-'}；条款 {clause || '-'}
            {reportPage ? `；报告第 ${reportPage} 页` : ''}
          </p>
        </div>
        <div className="judgement-pair">
          <span>报告：{reportJudgement}</span>
          <span>原始记录：{recordJudgement}</span>
        </div>
      </header>

      <details open={check.status !== 'pass'}>
        <summary>查看报告要求和匹配到的原始记录小项（{entries.length} 项）</summary>
        <div className="record-report-columns">
          <section>
            <h5>报告标准要求</h5>
            <pre>{reportRequirement}</pre>
          </section>
          <section>
            <h5>原始记录小项</h5>
            {entries.length > 0 ? (
              <div className="record-entry-list">
                {entries.map((entry, index) => (
                  <article key={`${entry.page}-${entry.record_sequence}-${index}`}>
                    <header>
                      <strong>
                        第 {readableText(entry.page, '-')} 页 / {readableText(entry.record_sequence, `小项 ${index + 1}`)}
                      </strong>
                      <span>{readableText(entry.judgement, '缺失')}</span>
                    </header>
                    <p>条款：{Array.isArray(entry.clauses) ? entry.clauses.join('、') : readableText(entry.clauses, '-')}</p>
                    <pre>{textFrom(entry.requirement_text, '未提取到原始记录要求文本')}</pre>
                  </article>
                ))}
              </div>
            ) : (
              <p className="empty-inline">未匹配到原始记录小项。</p>
            )}
          </section>
        </div>
      </details>
    </section>
  );
}

function renderMissingEvidenceCard(item: Record<string, unknown>, index: number) {
  const rawReason = String(item.reason ?? item.detail ?? item.value ?? '');
  const title = readableTitle(item, index);
  const reason = isCodexDiagnosticRecord(item) ? extractActionableDiagnostic(rawReason) : readableText(rawReason, '未说明原因');
  const expectedSource = item.expected_source ? String(item.expected_source) : '';

  return (
    <article className="missing-card" key={`${title}-${index}`}>
      <div>
        <strong>{title}</strong>
        <p>{reason}</p>
      </div>
      {expectedSource ? <small>需要来源：{expectedSource}</small> : null}
      {isCodexDiagnosticRecord(item) && rawReason ? (
        <details className="raw-diagnostic">
          <summary>查看技术诊断</summary>
          <pre>{compactDiagnostic(rawReason)}</pre>
        </details>
      ) : null}
    </article>
  );
}

export function CheckResultCard({ check }: { check: CheckResult }) {
  const status = formatStatus(check.status);
  const systemDiagnosticOnly = hasOnlyCodexDiagnostics(check);
  const isPtrClauseCheck = check.check_id.startsWith('PTR-') && check.check_id !== 'PTR-SCOPE-COVERAGE';
  const isRecordReportCheck = check.check_id.startsWith('RECORD-REPORT-GB9706-1-');

  return (
    <article className={`check-card ${status.tone}`} id={`check-${check.check_id}`}>
      <header className="check-card-header">
        <div>
          <p className="check-id">{check.check_id}</p>
          <h3>{check.check_name}</h3>
        </div>
        <div className="badge-row">
          <span className={`status-pill ${status.tone}`}>{status.label}</span>
          <span className="confidence-pill">{formatConfidence(check.confidence)}</span>
        </div>
      </header>

      {check.summary ? <p className="check-summary">{check.summary}</p> : null}

      {systemDiagnosticOnly ? (
        <section className="system-notice" role="note">
          <strong>本项没有形成有效判定</strong>
          <span>这是系统调用或解析问题，不代表报告内容本身存在该项风险。建议重新运行本报告。</span>
        </section>
      ) : null}

      {isPtrClauseCheck ? <PtrClauseComparisonList check={check} /> : null}
      {isRecordReportCheck ? <RecordReportComparisonPanel check={check} /> : null}

      {check.findings.length > 0 || (!isPtrClauseCheck && !isRecordReportCheck) ? (
        <section className="card-section">
          <h4>问题与风险</h4>
          <FindingsList findings={check.findings} />
        </section>
      ) : null}

      {check.missing_evidence.length > 0 ? (
        <section className="card-section evidence-warning">
          <h4>证据不足，建议人工确认</h4>
          <div className="missing-list">{check.missing_evidence.map(renderMissingEvidenceCard)}</div>
        </section>
      ) : null}
    </article>
  );
}
