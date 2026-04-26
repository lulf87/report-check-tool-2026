import type { ReportSelfCheckResult } from '../../types/reportSelfCheck';
import { formatStatus, hasOnlyCodexDiagnostics } from './display';

function asStringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.map((item) => String(item)).filter(Boolean) : [];
}

function formatClauseList(items: string[]) {
  return items.length > 0 ? items.join('、') : '无';
}

export function OverallSummary({ result }: { result: ReportSelfCheckResult }) {
  const status = formatStatus(result.overall_status);
  const hasMeta = Object.values(result.report_meta).some(Boolean);
  const scopeSummary = result.ptr_report_scope_summary;
  const declaredClauses = asStringArray(scopeSummary?.declared_clause_prefixes);
  const actualClauses = asStringArray(scopeSummary?.actual_report_clause_prefixes);
  const missingClauses = asStringArray(scopeSummary?.missing_declared_clause_prefixes);
  const extraClauses = asStringArray(scopeSummary?.extra_report_clause_prefixes);
  const diagnosticCount = result.check_results.filter(hasOnlyCodexDiagnostics).length;
  const summaryLead =
    diagnosticCount === result.check_results.length && diagnosticCount > 0
      ? '本次核对没有形成有效判定，主要原因是系统调用或结果解析失败。请重新运行报告。'
      : status.description;

  return (
    <section className={`summary-panel ${status.tone}`}>
      <div>
        <p className="eyebrow">核对结果</p>
        <h2>{status.label}</h2>
        <p className="summary-lead">{summaryLead}</p>
        <p className="summary-file">文件：{result.file_name}</p>
      </div>

      <div className="summary-stats" aria-label="核对项统计">
        <div className="stat-card">
          <span>{result.summary.total_checks}</span>
          <small>总项数</small>
        </div>
        <div className="stat-card pass">
          <span>{result.summary.pass_count}</span>
          <small>通过</small>
        </div>
        <div className="stat-card warning">
          <span>{result.summary.warning_count}</span>
          <small>需复核</small>
        </div>
        <div className="stat-card error">
          <span>{result.summary.error_count}</span>
          <small>发现问题</small>
        </div>
      </div>

      {diagnosticCount > 0 ? (
        <div className="diagnostic-summary">
          <strong>{diagnosticCount} 项为系统诊断问题</strong>
          <span>这些项目没有得到可解析的 Codex 判定，不应作为报告内容风险处理。</span>
        </div>
      ) : null}

      {scopeSummary ? (
        <div className={`ptr-scope-summary ${missingClauses.length > 0 ? 'error' : extraClauses.length > 0 ? 'warning' : 'pass'}`}>
          <strong>检验项目范围总览</strong>
          <span>首页声明：{formatClauseList(declaredClauses)}</span>
          <span>报告实际：{formatClauseList(actualClauses)}</span>
          <span>缺漏条款：{formatClauseList(missingClauses)}</span>
          {extraClauses.length > 0 ? <span>额外条款：{formatClauseList(extraClauses)}</span> : null}
        </div>
      ) : null}

      {hasMeta ? (
        <dl className="report-meta">
          {result.report_meta.report_number ? (
            <div>
              <dt>报告编号</dt>
              <dd>{result.report_meta.report_number}</dd>
            </div>
          ) : null}
          {result.report_meta.sample_number ? (
            <div>
              <dt>样品编号</dt>
              <dd>{result.report_meta.sample_number}</dd>
            </div>
          ) : null}
          {result.report_meta.sample_name ? (
            <div>
              <dt>样品名称</dt>
              <dd>{result.report_meta.sample_name}</dd>
            </div>
          ) : null}
          {result.report_meta.client ? (
            <div>
              <dt>委托方</dt>
              <dd>{result.report_meta.client}</dd>
            </div>
          ) : null}
        </dl>
      ) : null}
    </section>
  );
}
