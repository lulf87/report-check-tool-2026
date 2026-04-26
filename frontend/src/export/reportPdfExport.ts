import type { CheckResult, ReportSelfCheckResult } from '../types/reportSelfCheck';

export type ReportExportMode = 'self' | 'ptr-report';

const STATUS_LABELS: Record<string, string> = {
  pass: '通过',
  warning: '需复核',
  error: '发现问题',
};

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
  <main>
    <header class="report-header">
      <p class="eyebrow">PDF 导出</p>
      <h1>${escapeHtml(title)}</h1>
      <p>${escapeHtml(fileLine(result, mode))}</p>
      <p>导出时间：${escapeHtml(generatedAt)}</p>
    </header>
    ${summarySection(result)}
    ${mode === 'ptr-report' ? ptrScopeSection(result) : ''}
    ${result.check_results.map((check) => checkSection(check, mode)).join('')}
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

function fileLine(result: ReportSelfCheckResult, mode: ReportExportMode) {
  if (mode === 'ptr-report') {
    return `PTR：${result.ptr_file_name ?? '未返回文件名'}；报告：${result.report_file_name ?? result.file_name}`;
  }
  return `报告：${result.file_name}`;
}

function summarySection(result: ReportSelfCheckResult) {
  return `<section class="summary">
    <h2>总览</h2>
    <dl>
      <div><dt>总体状态</dt><dd>${escapeHtml(statusLabel(result.overall_status))}</dd></div>
      <div><dt>总项数</dt><dd>${result.summary.total_checks}</dd></div>
      <div><dt>通过</dt><dd>${result.summary.pass_count}</dd></div>
      <div><dt>需复核</dt><dd>${result.summary.warning_count}</dd></div>
      <div><dt>发现问题</dt><dd>${result.summary.error_count}</dd></div>
    </dl>
    ${reportMetaSection(result)}
  </section>`;
}

function reportMetaSection(result: ReportSelfCheckResult) {
  const meta = result.report_meta;
  const rows = [
    ['报告编号', meta.report_number],
    ['样品编号', meta.sample_number],
    ['样品名称', meta.sample_name],
    ['委托方', meta.client],
  ].filter(([, value]) => Boolean(value));
  if (rows.length === 0) return '';
  return `<dl>${rows.map(([label, value]) => `<div><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value)}</dd></div>`).join('')}</dl>`;
}

function ptrScopeSection(result: ReportSelfCheckResult) {
  const scope = result.ptr_report_scope_summary;
  if (!scope) return '';
  return `<section>
    <h2>检验项目范围</h2>
    <dl>
      <div><dt>首页声明条款</dt><dd>${escapeHtml(formatList(scope.declared_clause_prefixes))}</dd></div>
      <div><dt>报告实际条款</dt><dd>${escapeHtml(formatList(scope.actual_report_clause_prefixes))}</dd></div>
      <div><dt>缺漏条款</dt><dd>${escapeHtml(formatList(scope.missing_declared_clause_prefixes))}</dd></div>
      <div><dt>额外条款</dt><dd>${escapeHtml(formatList(scope.extra_report_clause_prefixes))}</dd></div>
    </dl>
  </section>`;
}

function checkSection(check: CheckResult, mode: ReportExportMode) {
  const leafReviews = recordsFrom(check.details.leaf_clause_reviews);
  return `<section class="check">
    <h2>${escapeHtml(check.check_id)} ${escapeHtml(check.check_name)}</h2>
    <p class="status">状态：${escapeHtml(statusLabel(check.status))}；置信度：${escapeHtml(check.confidence)}</p>
    ${check.summary ? `<p>${escapeHtml(check.summary)}</p>` : ''}
    ${mode === 'ptr-report' && leafReviews.length > 0 ? leafReviewSection(leafReviews) : ''}
    ${findingsSection(check)}
    ${missingEvidenceSection(check)}
  </section>`;
}

function leafReviewSection(reviews: Record<string, unknown>[]) {
  return `<div class="leaf-list">
    ${reviews
      .map((review) => {
        const title = [review.prefix, review.title].filter(Boolean).join(' ');
        const pages = formatPages(review.report_entry_pages);
        const ptrText = textValue(review.ptr_display_text ?? review.ptr_requirement_text, '未提取到 PTR 内容');
        const reportText =
          review.report_presence === 'missing'
            ? '报告中未检出该条款。'
            : textValue(review.report_display_text ?? review.report_standard_requirement_text, '未提取到报告内容');
        return `<article class="leaf">
          <h3>${escapeHtml(title)}</h3>
          <p class="muted">${escapeHtml(pages)}</p>
          <div class="columns">
            <div><h4>PTR 内容</h4><pre>${escapeHtml(ptrText)}</pre></div>
            <div><h4>报告内容</h4><pre>${escapeHtml(reportText)}</pre></div>
          </div>
        </article>`;
      })
      .join('')}
  </div>`;
}

function findingsSection(check: CheckResult) {
  if (check.findings.length === 0) return '';
  return `<div>
    <h3>问题与风险</h3>
    ${check.findings
      .map(
        (finding) => `<article class="finding">
          <strong>${escapeHtml(finding.title)}</strong>
          <p>${escapeHtml(finding.detail)}</p>
        </article>`,
      )
      .join('')}
  </div>`;
}

function missingEvidenceSection(check: CheckResult) {
  if (check.missing_evidence.length === 0) return '';
  return `<div>
    <h3>证据不足，建议人工确认</h3>
    ${check.missing_evidence
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

function formatPages(value: unknown) {
  const pages = Array.isArray(value) ? value.map((item) => String(item)).filter(Boolean) : [];
  return pages.length > 0 ? `报告第 ${pages.join('、')} 页` : '报告未检出';
}

function formatList(value: unknown) {
  const values = Array.isArray(value) ? value.map((item) => String(item)).filter(Boolean) : [];
  return values.length > 0 ? values.join('、') : '无';
}

function textValue(value: unknown, fallback: string) {
  if (value === null || value === undefined || value === '') return fallback;
  if (typeof value === 'string') return value;
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  return fallback;
}

function recordsFrom(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? value.filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === 'object' && !Array.isArray(item)) : [];
}

function humanTextValue(value: unknown, fallback: string) {
  if (value === null || value === undefined || value === '') return fallback;
  if (typeof value === 'string') return value;
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  return '包含结构化诊断信息，建议重新运行或人工复核。';
}

function statusLabel(status: string) {
  return STATUS_LABELS[status] ?? status;
}

function sanitizeFileName(name: string) {
  return name.replace(/[\\/:*?"<>|]+/g, '-').replace(/\s+/g, ' ').trim() || 'result.pdf';
}

function escapeHtml(value: string) {
  return value.replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;').replaceAll("'", '&#39;');
}

function printCss() {
  return `
    @page { size: A4; margin: 14mm; }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      color: #17211a;
      font-family: "Source Han Sans SC", "Noto Sans CJK SC", "PingFang SC", "Microsoft YaHei", sans-serif;
      line-height: 1.65;
      background: white;
    }
    main { display: grid; gap: 16px; }
    section, .report-header {
      break-inside: avoid;
      border: 1px solid #ded6c4;
      border-radius: 8px;
      padding: 14px;
    }
    h1, h2, h3, h4, p { margin-top: 0; }
    h1 { font-size: 24px; margin-bottom: 8px; }
    h2 { font-size: 18px; margin-bottom: 8px; }
    h3 { font-size: 15px; margin-bottom: 6px; }
    h4 { margin-bottom: 6px; color: #4d5a4b; }
    .eyebrow, .muted, .status { color: #66705f; }
    dl { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; margin: 0; }
    dt { color: #66705f; font-size: 12px; }
    dd { margin: 2px 0 0; font-weight: 700; overflow-wrap: anywhere; }
    .leaf-list { display: grid; gap: 12px; }
    .leaf { break-inside: avoid; border-top: 1px solid #eee5d4; padding-top: 10px; }
    .columns { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
    pre {
      margin: 0;
      white-space: pre-wrap;
      word-break: break-word;
      border-radius: 6px;
      padding: 10px;
      background: #f7f1e5;
      font-family: inherit;
      font-size: 12px;
    }
    .finding { border-left: 3px solid #b42318; padding-left: 10px; }
    .evidence-warning { border-left-color: #b7791f; }
  `;
}
