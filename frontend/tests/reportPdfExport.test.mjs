import assert from 'node:assert/strict';
import test from 'node:test';

import { buildReportExportHtml, buildReportExportTitle } from '/tmp/report-pdf-export-test/export/reportPdfExport.js';

function baseResult() {
  return {
    task_id: 'task-1',
    file_name: 'report.pdf',
    overall_status: 'warning',
    report_meta: {
      report_number: 'QW2025-0001',
      sample_number: 'S-001',
      sample_name: '样品',
      client: '委托方',
    },
    summary: {
      total_checks: 1,
      pass_count: 0,
      warning_count: 1,
      error_count: 0,
    },
    check_results: [
      {
        check_id: 'C02',
        check_name: '首页基础字段一致性',
        status: 'warning',
        confidence: 'high',
        summary: '字段需复核。',
        details: {},
        findings: [],
        evidence: [],
        missing_evidence: [],
      },
    ],
  };
}

test('buildReportExportHtml includes self-check summary and check results', () => {
  const html = buildReportExportHtml(baseResult(), 'self');

  assert.match(html, /报告自身核对结果/);
  assert.match(html, /report\.pdf/);
  assert.match(html, /首页基础字段一致性/);
  assert.match(html, /字段需复核/);
  assert.match(html, /window\.print/);
});

test('buildReportExportHtml includes PTR scope and leaf clause comparison columns', () => {
  const result = {
    ...baseResult(),
    ptr_file_name: 'ptr.pdf',
    report_file_name: 'report.pdf',
    ptr_report_scope_summary: {
      declared_clause_prefixes: ['2.1.2'],
      actual_report_clause_prefixes: ['2.1.2'],
      missing_declared_clause_prefixes: [],
    },
    check_results: [
      {
        check_id: 'PTR-2.1',
        check_name: 'PTR 第 2 章性能指标 vs report 标准要求摘录一致性 - 2.1',
        status: 'pass',
        confidence: 'high',
        summary: '一致。',
        details: {
          leaf_clause_reviews: [
            {
              prefix: '2.1.2',
              title: '脉冲幅度',
              ptr_display_text: 'PTR 中的脉冲幅度要求',
              report_display_text: '报告中的脉冲幅度要求',
              report_entry_pages: [26, 27],
            },
          ],
        },
        findings: [],
        evidence: [],
        missing_evidence: [],
      },
    ],
  };

  const html = buildReportExportHtml(result, 'ptr-report');

  assert.match(html, /PTR 与报告核对结果/);
  assert.match(html, /ptr\.pdf/);
  assert.match(html, /首页声明条款/);
  assert.match(html, /PTR 内容/);
  assert.match(html, /报告内容/);
  assert.match(html, /PTR 中的脉冲幅度要求/);
  assert.match(html, /报告中的脉冲幅度要求/);
});

test('buildReportExportTitle creates filesystem-friendly names for both modes', () => {
  assert.equal(buildReportExportTitle(baseResult(), 'self'), '报告自身核对-report.pdf');
  assert.equal(buildReportExportTitle(baseResult(), 'ptr-report'), 'PTR与报告核对-report.pdf');
});
