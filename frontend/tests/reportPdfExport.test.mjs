import assert from 'node:assert/strict';
import test from 'node:test';

import { buildReportExportHtml, buildReportExportTitle, printReportResultAsPdf } from '/tmp/report-pdf-export-test/export/reportPdfExport.js';

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
  assert.match(html, /核对结论摘要/);
  assert.match(html, /问题与缺漏清单/);
  assert.match(html, /核对明细/);
  assert.match(html, /本报告为系统辅助核对结果/);
  assert.doesNotMatch(html, /PDF 导出/);
  assert.doesNotMatch(html, /window\.open/);
});

test('buildReportExportHtml uses a print-specific report layout instead of app chrome', () => {
  const html = buildReportExportHtml(baseResult(), 'self');

  assert.match(html, /class="report-document"/);
  assert.match(html, /class="cover-section"/);
  assert.match(html, /class="issue-table"/);
  assert.match(html, /@page \{ size: A4; margin:/);
  assert.doesNotMatch(html, /开始 PTR 核对/);
  assert.doesNotMatch(html, /上传 PTR 与报告 PDF/);
});

test('buildReportExportHtml hides raw internal detail field names in self-check export', () => {
  const result = baseResult();
  result.check_results[0].details = {
    report_display_text: '用户真正需要看的报告文字',
    leaf_clause_reviews: [{ ptr_display_text: '内部 PTR 文本' }],
  };

  const html = buildReportExportHtml(result, 'self');

  assert.doesNotMatch(html, /report_display_text/);
  assert.doesNotMatch(html, /leaf_clause_reviews/);
  assert.doesNotMatch(html, /ptr_display_text/);
});

test('buildReportExportHtml includes readable self-check detail rows without raw field names', () => {
  const result = baseResult();
  result.check_results[0].details = {
    field_comparisons: [
      {
        field: '样品名称',
        expected: '产品 A',
        actual: '产品 B',
        matched: false,
        source_a_page: 1,
        source_b_page: 2,
      },
    ],
  };

  const html = buildReportExportHtml(result, 'self');

  assert.match(html, /字段核对明细/);
  assert.match(html, /样品名称/);
  assert.match(html, /产品 A/);
  assert.match(html, /产品 B/);
  assert.match(html, /是否一致/);
  assert.doesNotMatch(html, /field_comparisons/);
  assert.doesNotMatch(html, /source_a_page/);
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
  assert.match(html, /检验项目范围核对/);
  assert.match(html, /逐条款对照明细/);
  assert.match(html, /PTR 内容/);
  assert.match(html, /报告内容/);
  assert.match(html, /PTR 中的脉冲幅度要求/);
  assert.match(html, /报告中的脉冲幅度要求/);
  assert.doesNotMatch(html, /leaf_clause_reviews/);
  assert.doesNotMatch(html, /ptr_display_text/);
  assert.doesNotMatch(html, /report_display_text/);
});

test('buildReportExportHtml keeps full PTR comparison details even when Codex judgement is a system diagnostic', () => {
  const result = {
    ...baseResult(),
    ptr_file_name: 'ptr.pdf',
    report_file_name: 'report.pdf',
    check_results: [
      {
        check_id: 'PTR-2.1',
        check_name: 'PTR 第 2 章性能指标 vs report 标准要求摘录一致性 - 2.1',
        status: 'warning',
        confidence: 'low',
        summary: 'Codex 判断结果无法解析，需人工复核。',
        details: {
          leaf_clause_reviews: [
            {
              prefix: '2.1.15',
              title: '感知后房室间期',
              ptr_display_text: 'PTR 表 1 对应内容：20 ... 350，允许误差 ±20ms。',
              report_display_text: '报告表格内容：20 ... 350，允许误差 ±20ms。',
              report_entry_pages: [30],
            },
          ],
        },
        findings: [],
        evidence: [],
        missing_evidence: [
          {
            label: 'codex_json',
            reason: 'JSON parse error',
            expected_source: 'Codex JSON output',
          },
        ],
      },
    ],
  };

  const html = buildReportExportHtml(result, 'ptr-report');

  assert.match(html, /逐条款对照明细/);
  assert.match(html, /2\.1\.15 感知后房室间期/);
  assert.match(html, /PTR 表 1 对应内容：20 \.\.\. 350/);
  assert.match(html, /报告表格内容：20 \.\.\. 350/);
  assert.match(html, /本项未形成结构化判定/);
  assert.match(html, /系统诊断记录/);
  assert.doesNotMatch(html, /codex_json/);
});

test('buildReportExportHtml separates system diagnostics from report content findings', () => {
  const result = baseResult();
  result.check_results[0].missing_evidence = [
    {
      label: 'codex_json',
      reason: 'JSON parse error',
      expected_source: 'Codex JSON output',
    },
  ];

  const html = buildReportExportHtml(result, 'self');

  assert.match(html, /系统诊断记录/);
  assert.match(html, /系统返回结果解析失败/);
  assert.match(html, /该部分表示系统未形成有效结构化判定/);
  assert.doesNotMatch(html, /codex_json/);
  assert.doesNotMatch(html, /Codex JSON output/);
});

test('buildReportExportTitle creates filesystem-friendly names for both modes', () => {
  assert.equal(buildReportExportTitle(baseResult(), 'self'), '报告自身核对-report.pdf');
  assert.equal(buildReportExportTitle(baseResult(), 'ptr-report'), 'PTR与报告核对-report.pdf');
  assert.equal(
    buildReportExportTitle({ ...baseResult(), record_report_standard: 'gb9706_202' }, 'record-report'),
    '原始记录与报告核对-GB 9706.202-2021-report.pdf',
  );
});

test('buildReportExportHtml includes record-report standard and GB 9706.202 detail fields', () => {
  const result = {
    ...baseResult(),
    record_file_name: 'record.pdf',
    report_file_name: 'report.pdf',
    record_report_standard: 'gb9706_202',
    check_results: [
      {
        check_id: 'RECORD-REPORT-GB9706-202-119',
        check_name: '序号 119 / 条款 201.4.2.3.101 原始记录核对',
        status: 'warning',
        confidence: 'high',
        summary: '需人工复核。',
        details: {
          record_report_standard: 'gb9706_202',
          mapping_method: 'sequence_fallback',
          sequence: 119,
          report_standard_clause: '201.4.2.3.101',
          report_judgement: '不适用',
          record_aggregate_judgement: '缺失',
          record_entries: [
            {
              record_sequence: 1,
              clauses: ['201.4.2.3.101'],
              measured_data: '△',
              remark: '见风险管理文件',
              symbol_judgement: 'drawing_delta_mark',
            },
          ],
        },
        findings: [],
        evidence: [],
        missing_evidence: [],
      },
    ],
  };

  const html = buildReportExportHtml(result, 'record-report');

  assert.match(html, /原始记录与报告核对结果/);
  assert.match(html, /核对标准/);
  assert.match(html, /GB 9706\.202-2021/);
  assert.match(html, /映射方式/);
  assert.match(html, /序号顺序兜底/);
  assert.match(html, /实测数据/);
  assert.match(html, /原始记录符号判断/);
  assert.doesNotMatch(html, /record_report_standard/);
});

test('printReportResultAsPdf prints through a hidden iframe without opening a popup window', () => {
  const originalWindow = globalThis.window;
  const originalDocument = globalThis.document;
  let openCalled = false;
  let appendCalled = false;
  let printCalled = false;
  let removed = false;
  let loadCallback = null;

  const iframeDocument = {
    open() {},
    write(html) {
      assert.match(html, /报告自身核对结果/);
    },
    close() {
      loadCallback?.();
    },
  };
  const iframe = {
    style: {},
    contentWindow: {
      document: iframeDocument,
      focus() {},
      print() {
        printCalled = true;
      },
    },
    setAttribute() {},
    addEventListener(event, callback) {
      assert.equal(event, 'load');
      loadCallback = callback;
    },
    remove() {
      removed = true;
    },
  };

  globalThis.window = {
    open() {
      openCalled = true;
    },
    setTimeout(callback) {
      callback();
      return 1;
    },
  };
  globalThis.document = {
    body: {
      appendChild(node) {
        appendCalled = true;
        assert.equal(node, iframe);
      },
    },
    createElement(tagName) {
      assert.equal(tagName, 'iframe');
      return iframe;
    },
  };

  try {
    assert.equal(printReportResultAsPdf(baseResult(), 'self'), true);
    assert.equal(openCalled, false);
    assert.equal(appendCalled, true);
    assert.equal(printCalled, true);
    assert.equal(removed, true);
  } finally {
    globalThis.window = originalWindow;
    globalThis.document = originalDocument;
  }
});
