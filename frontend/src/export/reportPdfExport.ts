import type { CheckResult, Finding, ReportSelfCheckResult } from '../types/reportSelfCheck';

export type ReportExportMode = 'self' | 'ptr-report';

const STATUS_LABELS: Record<string, string> = {
  pass: '通过',
  warning: '需复核',
  error: '发现问题',
};

const CONFIDENCE_LABELS: Record<string, string> = {
  high: '高置信度',
  medium: '中置信度',
  low: '低置信度',
};

const DETAIL_LABELS: Record<string, string> = {
  actual: '实际值',
  actual_conclusion: '实际单项结论',
  actual_report_clause_prefixes: '报告实际条款',
  actual_value: '实际值',
  component_name: '组件名称',
  declared_clause_prefixes: '首页声明条款',
  expected: '应为',
  expected_conclusion: '应为单项结论',
  field: '字段',
  field_comparisons: '字段核对明细',
  inspection_project: '检验项目',
  judgement: '判断说明',
  leaf_clause_comparisons: '最细条款一致性判断',
  leaf_clause_reviews: '最细条款证据',
  matched: '是否一致',
  missing_declared_clause_prefixes: '缺漏条款',
  page: '页码',
  pages: '页码',
  parent_prefix: '上级条款',
  prefix: '条款号',
  ptr_clause_prefix: 'PTR 条款',
  ptr_display_text: 'PTR 内容',
  ptr_page: 'PTR 页码',
  ptr_referenced_requirement_text: 'PTR 引用内容',
  ptr_reference_context_text: 'PTR 引用上下文',
  ptr_requirement_text: 'PTR 要求',
  reason: '原因',
  report_candidate_pages: '报告候选页',
  report_display_text: '报告内容',
  report_entry_pages: '报告页码',
  report_presence: '报告是否出现',
  report_scope_text: '报告首页检验项目',
  report_standard_requirement_text: '报告标准要求摘录',
  source_a_name: '来源 A',
  source_a_page: 'A 页码',
  source_a_value: 'A 值',
  source_b_name: '来源 B',
  source_b_page: 'B 页码',
  source_b_value: 'B 值',
  status: '状态',
  summary: '摘要',
  test_results: '检验结果',
  title: '标题',
};

const PREFERRED_DETAIL_COLUMNS = [
  'sequence_number',
  'prefix',
  'ptr_clause_prefix',
  'parent_prefix',
  'field',
  'component_name',
  'inspection_project',
  'page',
  'ptr_page',
  'report_entry_pages',
  'report_presence',
  'source_a_name',
  'source_a_page',
  'source_a_value',
  'source_b_name',
  'source_b_page',
  'source_b_value',
  'expected',
  'actual',
  'test_results',
  'actual_conclusion',
  'expected_conclusion',
  'matched',
  'judgement',
  'reason',
];

export function buildReportExportTitle(result: ReportSelfCheckResult, mode: ReportExportMode) {
  const prefix = mode === 'ptr-report' ? 'PTR与报告核对' : '报告自身核对';
  return `${prefix}-${sanitizeFileName(result.report_file_name ?? result.file_name ?? 'result')}`;
}

export function buildReportExportHtml(result: ReportSelfCheckResult, mode: ReportExportMode) {
  const title = mode === 'ptr-report' ? 'PTR 与报告核对结果' : '报告自身核对结果';
  const generatedAt = new Date().toLocaleString('zh-CN');
  const htmlTitle = escapeHtml(buildReportExportTitle(result, mode));

  return `<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <title>${htmlTitle}</title>
  <style>${printCss()}</style>
</head>
<body>
  <main class="report-document">
    ${coverSection(result, mode, title, generatedAt)}
    ${summarySection(result)}
    ${mode === 'ptr-report' ? ptrScopeSection(result) : ''}
    ${issueListSection(result)}
    ${detailSection(result, mode)}
    ${systemDiagnosticsSection(result)}
    <footer class="report-footer">本报告为系统辅助核对结果，最终结论应结合原始 PDF 和人工复核确认。</footer>
  </main>
</body>
</html>`;
}

export function printReportResultAsPdf(result: ReportSelfCheckResult, mode: ReportExportMode) {
  if (typeof window === 'undefined' || typeof document === 'undefined' || !document.body) {
    return false;
  }

  const iframe = document.createElement('iframe');
  iframe.title = 'PDF 导出打印框架';
  iframe.setAttribute('aria-hidden', 'true');
  Object.assign(iframe.style, {
    position: 'fixed',
    right: '0',
    bottom: '0',
    width: '0',
    height: '0',
    border: '0',
    visibility: 'hidden',
  });

  document.body.appendChild(iframe);

  const iframeWindow = iframe.contentWindow;
  const iframeDocument = iframeWindow?.document;
  if (!iframeWindow || !iframeDocument) {
    iframe.remove();
    return false;
  }

  const cleanup = () => {
    window.setTimeout(() => {
      iframe.remove();
    }, 1000);
  };

  iframe.addEventListener(
    'load',
    () => {
      window.setTimeout(() => {
        iframeWindow.focus();
        iframeWindow.print();
        cleanup();
      }, 0);
    },
    { once: true },
  );

  iframeDocument.open();
  iframeDocument.write(buildReportExportHtml(result, mode));
  iframeDocument.close();
  return true;
}

function coverSection(result: ReportSelfCheckResult, mode: ReportExportMode, title: string, generatedAt: string) {
  const fileRows =
    mode === 'ptr-report'
      ? [
          ['PTR 文件', result.ptr_file_name ?? '未返回文件名'],
          ['报告文件', result.report_file_name ?? result.file_name],
        ]
      : [['报告文件', result.file_name]];
  const metaRows = [
    ['报告编号', result.report_meta.report_number],
    ['样品编号', result.report_meta.sample_number],
    ['样品名称', result.report_meta.sample_name],
    ['委托方', result.report_meta.client],
    ['生成时间', generatedAt],
  ].filter(([, value]) => Boolean(value));

  return `<section class="cover-section">
    <div class="cover-header">
      <div>
        <p class="kicker">核对报告</p>
        <h1>${escapeHtml(title)}</h1>
      </div>
      <span class="status-badge status-${statusClass(result.overall_status)}">${escapeHtml(statusLabel(result.overall_status))}</span>
    </div>
    <p class="cover-note">本报告为系统辅助核对结果，用于快速定位 PTR 与检验报告之间的摘录差异、缺漏条款和需人工确认事项。</p>
    <table class="meta-table">
      <tbody>
        ${[...fileRows, ...metaRows].map(([label, value]) => infoRow(label, value)).join('')}
      </tbody>
    </table>
  </section>`;
}

function summarySection(result: ReportSelfCheckResult) {
  return `<section class="report-section">
    <h2>核对结论摘要</h2>
    <div class="summary-grid">
      ${metricBlock('总体状态', statusLabel(result.overall_status), result.overall_status)}
      ${metricBlock('总项数', String(result.summary.total_checks))}
      ${metricBlock('通过', String(result.summary.pass_count), 'pass')}
      ${metricBlock('需复核', String(result.summary.warning_count), 'warning')}
      ${metricBlock('发现问题', String(result.summary.error_count), 'error')}
    </div>
  </section>`;
}

function ptrScopeSection(result: ReportSelfCheckResult) {
  const scope = result.ptr_report_scope_summary;
  if (!scope) return '';
  return `<section class="report-section">
    <h2>检验项目范围核对</h2>
    <table class="info-table">
      <tbody>
        ${infoRow('首页声明条款', formatList(scope.declared_clause_prefixes))}
        ${infoRow('报告实际条款', formatList(scope.actual_report_clause_prefixes))}
        ${infoRow('缺漏条款', formatList(scope.missing_declared_clause_prefixes))}
        ${infoRow('额外条款', formatList(scope.extra_report_clause_prefixes))}
      </tbody>
    </table>
  </section>`;
}

function issueListSection(result: ReportSelfCheckResult) {
  const issues = result.check_results.filter((check) => check.status !== 'pass');
  const rows =
    issues.length > 0
      ? issues.map(
          (check, index) => `<tr>
            <td>${index + 1}</td>
            <td>${escapeHtml(check.check_id)}</td>
            <td>${escapeHtml(issueType(check))}</td>
            <td>${escapeHtml(check.summary || check.check_name)}</td>
            <td>${escapeHtml(reportPageSummary(check))}</td>
          </tr>`,
        )
      : [
          `<tr>
            <td colspan="5" class="empty-cell">未发现需要处理的问题。</td>
          </tr>`,
        ];

  return `<section class="report-section">
    <h2>问题与缺漏清单</h2>
    <table class="issue-table">
      <thead>
        <tr>
          <th>序号</th>
          <th>核对项</th>
          <th>类型</th>
          <th>结论摘要</th>
          <th>页码/条款</th>
        </tr>
      </thead>
      <tbody>${rows.join('')}</tbody>
    </table>
  </section>`;
}

function detailSection(result: ReportSelfCheckResult, mode: ReportExportMode) {
  return mode === 'ptr-report' ? ptrDetailSection(result) : selfDetailSection(result);
}

function ptrDetailSection(result: ReportSelfCheckResult) {
  const blocks = result.check_results
    .filter((check) => check.check_id !== 'PTR-SCOPE-COVERAGE')
    .map(ptrCheckBlock)
    .filter(Boolean);

  return `<section class="report-section page-break-before">
    <h2>逐条款对照明细</h2>
    ${blocks.length > 0 ? blocks.join('') : '<p class="empty-state">未返回可展示的逐条款对照内容。</p>'}
  </section>`;
}

function selfDetailSection(result: ReportSelfCheckResult) {
  const blocks = result.check_results
    .map((check) => genericCheckBlock(check))
    .filter(Boolean);

  return `<section class="report-section page-break-before">
    <h2>核对明细</h2>
    ${blocks.length > 0 ? blocks.join('') : '<p class="empty-state">未返回可展示的核对明细。</p>'}
  </section>`;
}

function ptrCheckBlock(check: CheckResult) {
  const leafReviews = recordsFrom(check.details.leaf_clause_reviews);
  if (leafReviews.length === 0) return genericCheckBlock(check);
  const comparisons = recordsFrom(check.details.leaf_clause_comparisons);
  const comparisonTables = detailTablesSection(check.details, ['leaf_clause_reviews']);

  return `<article class="check-block status-left-${statusClass(check.status)}">
    ${checkHeader(check)}
    ${systemDiagnosticInline(check)}
    <div class="leaf-list">
      ${leafReviews.map((review) => leafReviewBlock(review, comparisons)).join('')}
    </div>
    ${comparisonTables}
  </article>`;
}

function leafReviewBlock(review: Record<string, unknown>, comparisons: Record<string, unknown>[]) {
  const prefix = String(review.prefix ?? '');
  const title = [prefix, review.title].filter(Boolean).join(' ');
  const pages = formatPages(review.report_entry_pages);
  const ptrText = textValue(review.ptr_display_text ?? review.ptr_requirement_text, '未提取到 PTR 内容');
  const reportText =
    review.report_presence === 'missing'
      ? '报告中未检出该条款。'
      : textValue(review.report_display_text ?? review.report_standard_requirement_text, '未提取到报告内容');
  const comparison = comparisons.find((item) => String(item.prefix ?? item.ptr_clause_prefix ?? '') === prefix);
  const judgement = comparison ? textValue(comparison.judgement ?? comparison.summary ?? comparison.status, '') : '';

  return `<article class="leaf-block">
    <div class="leaf-heading">
      <h4>${escapeHtml(title || '未命名条款')}</h4>
      <span>${escapeHtml(pages)}</span>
    </div>
    ${judgement ? `<p class="judgement">${escapeHtml(judgement)}</p>` : ''}
    <div class="compare-grid">
      <div>
        <h5>PTR 内容</h5>
        <pre>${escapeHtml(ptrText)}</pre>
      </div>
      <div>
        <h5>报告内容</h5>
        <pre>${escapeHtml(reportText)}</pre>
      </div>
    </div>
  </article>`;
}

function genericCheckBlock(check: CheckResult) {
  const visibleMissingEvidence = check.missing_evidence.filter((item) => !isSystemDiagnosticItem(item));
  const details = detailTablesSection(check.details);
  const findings = findingsSection(check.findings);
  const missing = visibleMissingEvidence.length > 0 ? missingEvidenceSection(visibleMissingEvidence) : '';

  return `<article class="check-block status-left-${statusClass(check.status)}">
    ${checkHeader(check)}
    ${systemDiagnosticInline(check)}
    ${details}
    ${findings}
    ${missing}
  </article>`;
}

function checkHeader(check: CheckResult) {
  return `<header class="check-heading">
    <div>
      <p class="check-id">${escapeHtml(check.check_id)}</p>
      <h3>${escapeHtml(check.check_name)}</h3>
    </div>
    <div class="check-status">
      <span class="status-badge status-${statusClass(check.status)}">${escapeHtml(statusLabel(check.status))}</span>
      <span class="confidence">${escapeHtml(confidenceLabel(check.confidence))}</span>
    </div>
    ${check.summary ? `<p class="check-summary">${escapeHtml(check.summary)}</p>` : ''}
  </header>`;
}

function systemDiagnosticInline(check: CheckResult) {
  if (!isSystemDiagnosticCheck(check)) return '';
  return `<div class="diagnostic-inline">
    <strong>本项未形成结构化判定</strong>
    <span>以下 PTR/报告内容仍按系统已提取的证据完整列出，需人工复核。</span>
  </div>`;
}

function detailTablesSection(details: Record<string, unknown>, excludedKeys: string[] = []) {
  const entries = Object.entries(details).filter(([, value]) => hasDisplayValue(value));
  const visibleEntries = entries.filter(([key]) => !excludedKeys.includes(key));
  if (visibleEntries.length === 0) return '';

  return `<div class="detail-list">
    ${visibleEntries.map(([key, value]) => detailEntry(key, value)).join('')}
  </div>`;
}

function detailEntry(key: string, value: unknown) {
  if (Array.isArray(value) && value.every(isRecord)) {
    return `<section class="detail-entry">
      <h4>${escapeHtml(labelFor(key))}</h4>
      ${recordTable(value)}
    </section>`;
  }

  if (isRecord(value)) {
    return `<section class="detail-entry">
      <h4>${escapeHtml(labelFor(key))}</h4>
      <table class="detail-table">
        <tbody>${Object.entries(value).map(([itemKey, itemValue]) => infoRow(labelFor(itemKey), readableValue(itemValue))).join('')}</tbody>
      </table>
    </section>`;
  }

  return `<section class="detail-entry">
    <h4>${escapeHtml(labelFor(key))}</h4>
    <table class="detail-table">
      <tbody>${infoRow('内容', readableValue(value))}</tbody>
    </table>
  </section>`;
}

function recordTable(rows: Record<string, unknown>[]) {
  if (rows.length === 0) return '<p class="empty-state">无</p>';
  const columns = collectColumns(rows);
  return `<table class="detail-table">
    <thead>
      <tr>${columns.map((column) => `<th>${escapeHtml(labelFor(column))}</th>`).join('')}</tr>
    </thead>
    <tbody>
      ${rows
        .map((row) => `<tr>${columns.map((column) => `<td>${escapeHtml(readableValue(row[column]))}</td>`).join('')}</tr>`)
        .join('')}
    </tbody>
  </table>`;
}

function collectColumns(rows: Record<string, unknown>[]) {
  const keys = new Set(rows.flatMap((row) => Object.keys(row)));
  return [...PREFERRED_DETAIL_COLUMNS.filter((key) => keys.has(key)), ...[...keys].filter((key) => !PREFERRED_DETAIL_COLUMNS.includes(key))];
}

function findingsSection(findings: Finding[]) {
  if (findings.length === 0) return '';
  return `<div class="finding-list">
    <h4>问题与风险</h4>
    ${findings
      .map(
        (finding) => `<article class="finding">
          <strong>${escapeHtml(finding.title)}</strong>
          <p>${escapeHtml(finding.detail)}</p>
          ${finding.pages.length > 0 ? `<p class="muted">页码：${escapeHtml(finding.pages.join('、'))}</p>` : ''}
          ${finding.expected || finding.actual ? expectedActualTable(finding) : ''}
        </article>`,
      )
      .join('')}
  </div>`;
}

function expectedActualTable(finding: Finding) {
  return `<table class="mini-table">
    <tbody>
      ${finding.expected ? infoRow('应为', finding.expected) : ''}
      ${finding.actual ? infoRow('实际', finding.actual) : ''}
    </tbody>
  </table>`;
}

function missingEvidenceSection(items: Record<string, unknown>[]) {
  return `<div class="finding-list">
    <h4>证据不足，建议人工确认</h4>
    ${items
      .map((item, index) => {
        const title = humanTextValue(item.title ?? item.label ?? item.source, `证据 ${index + 1}`);
        const reason = humanTextValue(item.reason ?? item.detail ?? item.value, '未说明原因');
        const expectedSource = humanTextValue(item.expected_source, '');
        return `<article class="finding evidence-warning">
          <strong>${escapeHtml(title)}</strong>
          <p>${escapeHtml(reason)}</p>
          ${expectedSource ? `<p class="muted">需要来源：${escapeHtml(expectedSource)}</p>` : ''}
        </article>`;
      })
      .join('')}
  </div>`;
}

function systemDiagnosticsSection(result: ReportSelfCheckResult) {
  const diagnostics = result.check_results.flatMap((check) =>
    check.missing_evidence.filter(isSystemDiagnosticItem).map((item) => ({ check, item })),
  );
  if (diagnostics.length === 0) return '';

  return `<section class="report-section diagnostics-section page-break-before">
    <h2>系统诊断记录</h2>
    <p class="section-note">该部分表示系统未形成有效结构化判定，不代表报告内容本身存在问题。</p>
    ${diagnostics
      .map(
        ({ check, item }) => `<article class="diagnostic-item">
          <strong>${escapeHtml(check.check_id)} ${escapeHtml(check.check_name)}</strong>
          <p>系统返回结果解析失败。</p>
          <p class="muted">${escapeHtml(formatDiagnosticReason(item))}</p>
        </article>`,
      )
      .join('')}
  </section>`;
}

function metricBlock(label: string, value: string, tone = '') {
  return `<div class="metric ${tone ? `metric-${statusClass(tone)}` : ''}">
    <span>${escapeHtml(label)}</span>
    <strong>${escapeHtml(value)}</strong>
  </div>`;
}

function infoRow(label: string, value: unknown) {
  return `<tr><th>${escapeHtml(label)}</th><td>${escapeHtml(humanTextValue(value, '无'))}</td></tr>`;
}

function issueType(check: CheckResult) {
  if (isSystemDiagnosticCheck(check)) return '系统诊断';
  return check.status === 'error' ? '发现问题' : '需人工复核';
}

function reportPageSummary(check: CheckResult) {
  const pages = new Set<string>();
  for (const finding of check.findings) {
    for (const page of finding.pages) {
      pages.add(String(page));
    }
  }
  for (const review of recordsFrom(check.details.leaf_clause_reviews)) {
    for (const page of valuesFrom(review.report_entry_pages)) {
      pages.add(String(page));
    }
  }

  if (pages.size > 0) return `报告第 ${[...pages].join('、')} 页`;
  return check.check_id.startsWith('PTR-') ? check.check_id.replace(/^PTR-/, '') : '未标明';
}

function formatPages(value: unknown) {
  const pages = valuesFrom(value);
  return pages.length > 0 ? `报告第 ${pages.join('、')} 页` : '报告未检出';
}

function formatList(value: unknown) {
  const values = valuesFrom(value);
  return values.length > 0 ? values.join('、') : '无';
}

function textValue(value: unknown, fallback: string) {
  if (value === null || value === undefined || value === '') return fallback;
  if (typeof value === 'string') return value;
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  return fallback;
}

function humanTextValue(value: unknown, fallback: string) {
  if (value === null || value === undefined || value === '') return fallback;
  if (typeof value === 'string') return value;
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  return '包含结构化诊断信息，建议重新运行或人工复核。';
}

function readableValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return '未提供';
  if (typeof value === 'boolean') return value ? '是' : '否';
  if (typeof value === 'string' || typeof value === 'number') return String(value);
  if (Array.isArray(value)) {
    if (value.length === 0) return '无';
    return value.map((item) => readableValue(item)).join('、');
  }
  if (isRecord(value)) {
    return Object.entries(value)
      .map(([key, item]) => `${labelFor(key)}：${readableValue(item)}`)
      .join('；');
  }
  return String(value);
}

function hasDisplayValue(value: unknown) {
  if (value === null || value === undefined || value === '') return false;
  if (Array.isArray(value)) return value.length > 0;
  if (isRecord(value)) return Object.keys(value).length > 0;
  return true;
}

function valuesFrom(value: unknown) {
  return Array.isArray(value) ? value.map((item) => String(item)).filter(Boolean) : [];
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

function recordsFrom(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? value.filter(isRecord) : [];
}

function isSystemDiagnosticCheck(check: CheckResult) {
  return check.status === 'warning' && check.missing_evidence.length > 0 && check.missing_evidence.every(isSystemDiagnosticItem);
}

function isSystemDiagnosticItem(item: Record<string, unknown>) {
  const label = String(item.label ?? '').toLowerCase();
  const reason = String(item.reason ?? item.detail ?? item.value ?? '');
  const expectedSource = String(item.expected_source ?? '');
  return (
    label === 'codex_json' ||
    expectedSource.includes('Codex JSON') ||
    reason.includes('OpenAI Codex') ||
    reason.includes('"check_id"') ||
    reason.includes('JSON parse') ||
    reason.includes('JSON') ||
    reason.includes('The model')
  );
}

function formatDiagnosticReason(item: Record<string, unknown>) {
  const reason = String(item.reason ?? item.detail ?? item.value ?? '');
  if (reason.includes('The model') && reason.includes('does not exist')) {
    return 'Codex 模型不可用，需检查后端模型配置后重新运行。';
  }
  if (reason.includes('JSON')) {
    return '系统未能得到可用于判定的结构化结果，建议重新运行或人工确认。';
  }
  return '系统未能得到可用于判定的结果，建议重新运行或人工确认。';
}

function statusLabel(status: string) {
  return STATUS_LABELS[status] ?? status;
}

function confidenceLabel(confidence: string) {
  return CONFIDENCE_LABELS[confidence] ?? confidence;
}

function labelFor(key: string) {
  return DETAIL_LABELS[key] ?? key.replaceAll('_', ' ');
}

function statusClass(status: string) {
  if (status === 'pass' || status === 'warning' || status === 'error') return status;
  return 'neutral';
}

function sanitizeFileName(name: string) {
  return name.replace(/[\\/:*?"<>|]+/g, '-').replace(/\s+/g, ' ').trim() || 'result.pdf';
}

function escapeHtml(value: string) {
  return value.replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;').replaceAll("'", '&#39;');
}

function printCss() {
  return `
    @page { size: A4; margin: 14mm 12mm 16mm; }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      color: #111827;
      background: #fff;
      font-family: "Source Han Sans SC", "Noto Sans CJK SC", "PingFang SC", "Microsoft YaHei", Arial, sans-serif;
      font-size: 11.5px;
      line-height: 1.55;
    }
    .report-document {
      max-width: 186mm;
      margin: 0 auto;
    }
    .cover-section {
      padding: 0 0 9mm;
      margin: 0 0 8mm;
      border-bottom: 2px solid #111827;
    }
    .cover-header {
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 8mm;
      margin-bottom: 5mm;
    }
    .kicker {
      margin: 0 0 2mm;
      color: #344054;
      font-size: 10px;
      font-weight: 700;
      letter-spacing: 0;
    }
    h1, h2, h3, h4, h5, p { margin-top: 0; }
    h1 { margin-bottom: 0; font-size: 24px; line-height: 1.25; }
    h2 { margin-bottom: 4mm; font-size: 16px; padding-bottom: 2mm; border-bottom: 1px solid #98a2b3; }
    h3 { margin-bottom: 2mm; font-size: 13px; }
    h4 { margin-bottom: 2mm; font-size: 12px; }
    h5 { margin-bottom: 1.5mm; color: #344054; font-size: 10px; }
    .cover-note, .section-note, .muted, .confidence {
      color: #475467;
    }
    .report-section {
      margin-bottom: 8mm;
      break-inside: avoid;
    }
    .summary-grid {
      display: grid;
      grid-template-columns: repeat(5, minmax(0, 1fr));
      border: 1px solid #d0d5dd;
    }
    .metric {
      min-height: 18mm;
      padding: 3mm;
      border-right: 1px solid #d0d5dd;
    }
    .metric:last-child { border-right: 0; }
    .metric span {
      display: block;
      color: #475467;
      font-size: 10px;
    }
    .metric strong {
      display: block;
      margin-top: 2mm;
      font-size: 18px;
      line-height: 1.1;
    }
    .metric-pass strong, .status-pass { color: #067647; }
    .metric-warning strong, .status-warning { color: #b54708; }
    .metric-error strong, .status-error { color: #b42318; }
    .status-neutral { color: #344054; }
    .status-badge {
      display: inline-block;
      white-space: nowrap;
      border: 1px solid currentColor;
      border-radius: 2px;
      padding: 1mm 2mm;
      font-size: 10px;
      font-weight: 700;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      table-layout: fixed;
    }
    th, td {
      border: 1px solid #d0d5dd;
      padding: 2mm;
      vertical-align: top;
      overflow-wrap: anywhere;
    }
    th {
      width: 28mm;
      background: #f2f4f7;
      color: #344054;
      font-weight: 700;
      text-align: left;
    }
    .issue-table th {
      width: auto;
      text-align: left;
    }
    .issue-table th:first-child,
    .issue-table td:first-child {
      width: 12mm;
      text-align: center;
    }
    .empty-cell, .empty-state {
      color: #475467;
    }
    .check-block {
      margin-bottom: 5mm;
      border: 1px solid #d0d5dd;
      break-inside: avoid;
    }
    .status-left-pass { border-left: 3px solid #067647; }
    .status-left-warning { border-left: 3px solid #b54708; }
    .status-left-error { border-left: 3px solid #b42318; }
    .check-heading {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 2mm 4mm;
      padding: 3mm;
      border-bottom: 1px solid #e4e7ec;
      background: #fcfcfd;
    }
    .check-id {
      margin-bottom: 1mm;
      color: #175cd3;
      font-weight: 700;
    }
    .check-summary {
      grid-column: 1 / -1;
      margin-bottom: 0;
      color: #344054;
    }
    .check-status {
      display: flex;
      align-items: center;
      gap: 2mm;
    }
    .leaf-list, .finding-list {
      display: grid;
      gap: 3mm;
      padding: 3mm;
    }
    .detail-list {
      display: grid;
      gap: 3mm;
      padding: 0 3mm 3mm;
    }
    .detail-entry {
      break-inside: avoid;
    }
    .detail-table {
      font-size: 10px;
    }
    .detail-table th,
    .detail-table td {
      padding: 1.6mm;
    }
    .leaf-block {
      break-inside: avoid;
      border-top: 1px solid #e4e7ec;
      padding-top: 3mm;
    }
    .leaf-block:first-child {
      border-top: 0;
      padding-top: 0;
    }
    .leaf-heading {
      display: flex;
      justify-content: space-between;
      gap: 4mm;
      margin-bottom: 2mm;
    }
    .leaf-heading span {
      color: #475467;
      white-space: nowrap;
    }
    .judgement {
      margin-bottom: 2mm;
      color: #344054;
    }
    .compare-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 3mm;
    }
    pre {
      margin: 0;
      min-height: 18mm;
      white-space: pre-wrap;
      word-break: break-word;
      border: 1px solid #e4e7ec;
      border-radius: 2px;
      padding: 2.5mm;
      background: #f8fafc;
      font-family: inherit;
      font-size: 10.5px;
    }
    .finding {
      border-left: 2px solid #b42318;
      padding-left: 3mm;
      break-inside: avoid;
    }
    .evidence-warning { border-left-color: #b54708; }
    .mini-table { margin-top: 2mm; }
    .diagnostics-section {
      border-top: 1px solid #d0d5dd;
      padding-top: 4mm;
    }
    .diagnostic-item {
      margin-bottom: 3mm;
      border-left: 2px solid #667085;
      padding-left: 3mm;
      break-inside: avoid;
    }
    .diagnostic-inline {
      display: grid;
      gap: 1mm;
      margin: 3mm;
      border-left: 2px solid #667085;
      padding: 2mm 3mm;
      background: #f8fafc;
      color: #344054;
    }
    .diagnostic-inline strong {
      color: #111827;
    }
    .report-footer {
      margin-top: 8mm;
      padding-top: 3mm;
      border-top: 1px solid #d0d5dd;
      color: #667085;
      font-size: 10px;
    }
    .page-break-before { break-before: page; }
  `;
}
