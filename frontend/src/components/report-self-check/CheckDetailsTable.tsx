import type { ReactNode } from 'react';

const FIELD_LABELS: Record<string, string> = {
  actual: '实际值',
  actual_conclusion: '实际单项结论',
  actual_report_clause_count: '报告实际条款数',
  actual_report_clause_prefixes: '报告实际条款',
  actual_value: '实际值',
  check_name: '检查项',
  component: '组件',
  component_name: '组件名称',
  confidence: '置信度',
  detail: '说明',
  declared_clause_count: '首页声明条款数',
  declared_clause_prefixes: '首页声明条款',
  declared_selectors: '首页声明范围',
  duplicate_numbers: '重复序号',
  duplicate_pages: '重复页码',
  empty_field_rows: '空字段行',
  expected: '应为',
  expected_conclusion: '应为单项结论',
  expected_source: '期望证据来源',
  extra_report_clause_prefixes: '报告额外条款',
  field: '字段',
  field_comparisons: '字段核对明细',
  final_page_match: '末页匹配',
  inspection_project: '检验项目',
  judgement: '判断说明',
  label: '证据项',
  leaf_clause_comparisons: '最细条款一致性判断',
  leaf_clause_reviews: '最细条款证据',
  matched: '是否一致',
  missing_declared_clause_prefixes: '缺漏条款',
  missing_numbers: '缺失序号',
  missing_pages: '缺失页码',
  page: '页码',
  pages: '页码',
  page_infos: '页码信息',
  parent_prefix: '上级条款',
  prefix: '条款号',
  ptr_clause_prefix: 'PTR 条款',
  ptr_display_text: 'PTR 展示内容',
  ptr_page: 'PTR 页码',
  ptr_referenced_requirement_text: 'PTR 引用内容',
  ptr_reference_context_text: 'PTR 引用上下文',
  ptr_requirement_text: 'PTR 要求',
  reason: '原因',
  report_candidate_pages: '报告候选页',
  report_entry_pages: '报告页码',
  report_display_text: '报告展示内容',
  report_presence: '报告是否出现',
  report_scope_text: '报告首页检验项目',
  report_standard_requirement_text: '报告标准要求摘录',
  related_fields: '相关字段',
  rows: '行明细',
  sample_tail: '样品编号尾号',
  section_order_ok: '章节顺序正常',
  sequence_list: '序号列表',
  sequence_number: '序号',
  sequence_results: '序号结果明细',
  source: '来源',
  source_a_name: '来源 A',
  source_a_page: 'A 页码',
  source_a_value: 'A 值',
  source_b_name: '来源 B',
  source_b_page: 'B 页码',
  source_b_value: 'B 值',
  status: '状态',
  summary: '摘要',
  term_groups: '术语组',
  test_results: '检验结果',
  title: '标题',
  total_consistent: '总页数一致',
  value: '值',
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

function labelFor(key: string) {
  return FIELD_LABELS[key] ?? key.replaceAll('_', ' ');
}

function formatPrimitive(value: unknown): string {
  if (value === null || value === undefined || value === '') return '未提供';
  if (typeof value === 'boolean') return value ? '是' : '否';
  return String(value);
}

function renderInlineValue(value: unknown): ReactNode {
  if (Array.isArray(value)) {
    if (value.length === 0) return <span className="muted">无</span>;
    if (value.every((item) => !isRecord(item) && !Array.isArray(item))) {
      return value.map((item, index) => (
        <span className="value-chip" key={`${String(item)}-${index}`}>
          {formatPrimitive(item)}
        </span>
      ));
    }
  }

  if (isRecord(value)) {
    return <DescriptionList value={value} compact />;
  }

  return formatPrimitive(value);
}

function collectColumns(rows: Record<string, unknown>[]) {
  const preferred = [
    'sequence_number',
    'prefix',
    'parent_prefix',
    'field',
    'component_name',
    'inspection_project',
    'page',
    'ptr_page',
    'report_presence',
    'report_entry_pages',
    'source_a_name',
    'source_a_value',
    'source_b_name',
    'source_b_value',
    'test_results',
    'actual_conclusion',
    'expected_conclusion',
    'matched',
    'judgement',
    'reason',
  ];
  const keys = new Set(rows.flatMap((row) => Object.keys(row)));
  return [...preferred.filter((key) => keys.has(key)), ...[...keys].filter((key) => !preferred.includes(key))];
}

function ArrayTable({ rows }: { rows: Record<string, unknown>[] }) {
  const columns = collectColumns(rows);

  return (
    <div className="table-scroll">
      <table className="data-table">
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column}>{labelFor(column)}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, rowIndex) => (
            <tr key={rowIndex}>
              {columns.map((column) => (
                <td key={column}>{renderInlineValue(row[column])}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function DescriptionList({ value, compact = false }: { value: Record<string, unknown>; compact?: boolean }) {
  return (
    <dl className={compact ? 'description-list compact' : 'description-list'}>
      {Object.entries(value).map(([key, item]) => (
        <div key={key}>
          <dt>{labelFor(key)}</dt>
          <dd>{renderDetailValue(item)}</dd>
        </div>
      ))}
    </dl>
  );
}

function renderDetailValue(value: unknown): ReactNode {
  if (Array.isArray(value)) {
    if (value.length === 0) return <span className="empty-inline">无</span>;
    if (value.every(isRecord)) return <ArrayTable rows={value} />;

    return (
      <div className="chip-list">
        {value.map((item, index) => (
          <span className="value-chip" key={`${String(item)}-${index}`}>
            {formatPrimitive(item)}
          </span>
        ))}
      </div>
    );
  }

  if (isRecord(value)) return <DescriptionList value={value} />;

  return <span>{formatPrimitive(value)}</span>;
}

export function CheckDetailsTable({ details }: { details: Record<string, unknown> }) {
  const entries = Object.entries(details);

  if (entries.length === 0) {
    return <p className="empty-inline">本项未返回明细，建议人工复核。</p>;
  }

  return (
    <div className="detail-stack">
      {entries.map(([key, value]) => (
        <section className="detail-section" key={key}>
          <h4>{labelFor(key)}</h4>
          {renderDetailValue(value)}
        </section>
      ))}
    </div>
  );
}
