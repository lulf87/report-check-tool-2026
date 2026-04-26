import type { Finding } from '../../types/reportSelfCheck';

function severityLabel(severity: Finding['severity']) {
  return severity === 'error' ? '错误' : '需复核';
}

export function FindingsList({ findings }: { findings: Finding[] }) {
  if (findings.length === 0) {
    return <p className="empty-inline">未发现具体问题。</p>;
  }

  return (
    <div className="finding-list">
      {findings.map((finding, index) => (
        <article className={`finding-card ${finding.severity}`} key={`${finding.title}-${index}`}>
          <div className="finding-header">
            <span className={`status-pill ${finding.severity}`}>{severityLabel(finding.severity)}</span>
            <strong>{finding.title}</strong>
          </div>
          <p>{finding.detail}</p>
          <div className="finding-meta">
            {finding.pages.length > 0 ? <span>页码：{finding.pages.join('、')}</span> : null}
            {finding.related_fields.length > 0 ? <span>字段：{finding.related_fields.join('、')}</span> : null}
          </div>
          {(finding.expected || finding.actual) && (
            <dl className="expected-actual">
              {finding.expected ? (
                <div>
                  <dt>应为</dt>
                  <dd>{finding.expected}</dd>
                </div>
              ) : null}
              {finding.actual ? (
                <div>
                  <dt>实际</dt>
                  <dd>{finding.actual}</dd>
                </div>
              ) : null}
            </dl>
          )}
        </article>
      ))}
    </div>
  );
}
