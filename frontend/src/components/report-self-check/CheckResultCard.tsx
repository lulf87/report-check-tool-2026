import type { CheckResult } from '../../types/reportSelfCheck';
import { CheckDetailsTable } from './CheckDetailsTable';
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

function renderEvidenceRecord(item: Record<string, unknown>, index: number) {
  const title = readableTitle(item, index);
  const page = item.page ? `第 ${item.page} 页` : '';
  const label = item.label && item.label !== title ? String(item.label) : '';
  const value = readableText(item.value);

  return (
    <li key={`${title}-${index}`}>
      <strong>{title}</strong>
      {[page, label, value].filter(Boolean).map((part) => (
        <span key={part}>{part}</span>
      ))}
    </li>
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

      <details className={isPtrClauseCheck ? 'technical-details' : undefined}>
        <summary>{isPtrClauseCheck ? '查看技术明细' : '核对明细'}</summary>
        <CheckDetailsTable details={check.details} />
      </details>

      {check.findings.length > 0 || !isPtrClauseCheck ? (
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

      {check.evidence.length > 0 ? (
        <details className="technical-details">
          <summary>查看证据来源</summary>
          <ul>{check.evidence.map(renderEvidenceRecord)}</ul>
        </details>
      ) : null}
    </article>
  );
}
