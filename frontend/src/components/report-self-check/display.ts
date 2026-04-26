import type { CheckResult, CheckStatus, Confidence } from '../../types/reportSelfCheck';

export const statusMeta: Record<CheckStatus, { label: string; tone: string; description: string }> = {
  pass: { label: '通过', tone: 'pass', description: '未发现需要处理的问题' },
  warning: { label: '需复核', tone: 'warning', description: '证据不足或存在需人工确认的风险' },
  error: { label: '发现问题', tone: 'error', description: '发现明确不一致或缺失项' },
};

export const confidenceLabel: Record<Confidence, string> = {
  high: '高置信度',
  medium: '中置信度',
  low: '低置信度',
};

export function formatStatus(status: CheckStatus) {
  return statusMeta[status];
}

export function formatConfidence(confidence: Confidence) {
  return confidenceLabel[confidence];
}

export function isCodexDiagnosticRecord(item: Record<string, unknown>) {
  const label = String(item.label ?? '').toLowerCase();
  const reason = String(item.reason ?? item.detail ?? item.value ?? '');
  return (
    label === 'codex_json' ||
    reason.includes('OpenAI Codex') ||
    reason.includes('核对证据包') ||
    reason.includes('"check_id"') ||
    reason.includes('The model')
  );
}

export function hasOnlyCodexDiagnostics(check: CheckResult) {
  return (
    check.status === 'warning' &&
    check.missing_evidence.length > 0 &&
    check.missing_evidence.every(isCodexDiagnosticRecord)
  );
}

export function extractActionableDiagnostic(raw: string) {
  if (raw.includes('The model') && raw.includes('does not exist')) {
    return 'Codex 模型不可用，需检查后端模型配置后重新运行。';
  }

  if (raw.includes('无法解析') || raw.includes('JSON')) {
    return 'Codex 返回内容未通过结构化解析，需重新运行或查看技术诊断。';
  }

  if (raw.includes('failed to load skill')) {
    return 'Codex 启动时加载本地技能失败，需检查本机 Codex 配置。';
  }

  return '系统未能得到可用于判定的结构化结果，需重新运行或查看技术诊断。';
}

export function compactDiagnostic(raw: string, maxLength = 1200) {
  const lines = raw
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
  const priority = lines.filter(
    (line) =>
      line.startsWith('ERROR:') ||
      line.includes('The model') ||
      line.includes('does not exist') ||
      line.includes('failed to load skill') ||
      line.includes('stream disconnected'),
  );
  const text = (priority.length ? priority.slice(-6) : lines.slice(0, 12)).join('\n');
  return text.length > maxLength ? `${text.slice(0, maxLength)}...` : text;
}
