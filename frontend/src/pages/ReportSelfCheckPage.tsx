import { useEffect, useRef, useState } from 'react';

import { getReportSelfCheckTask, startPtrReportCheck, startReportSelfCheck } from '../api/reportSelfCheck';
import { CheckResultCard } from '../components/report-self-check/CheckResultCard';
import { OverallSummary } from '../components/report-self-check/OverallSummary';
import { printReportResultAsPdf } from '../export/reportPdfExport';
import type { CheckResult, ReportSelfCheckResult, ReportSelfCheckTask } from '../types/reportSelfCheck';

const POLL_INTERVAL_MS = 2000;
type CheckMode = 'self' | 'ptr-report';

const MODE_COPY: Record<
  CheckMode,
  {
    label: string;
    shortLabel: string;
    description: string;
    uploadTitle: string;
    waitingText: string;
    runningText: string;
    startText: string;
    loadingText: string;
    failureText: string;
    progressLabel: string;
    passDescription: string;
  }
> = {
  self: {
    label: '报告自身核对',
    shortLabel: '自身核对',
    description:
      '上传 PDF 报告后，系统会逐项调用 Codex 判断已启用的内部一致性检查项，并把发现的问题整理成可处理的明细。',
    uploadTitle: '上传报告 PDF',
    waitingText: '选择报告并开始核对后，这里会显示当前检查项、进度和执行日志。',
    runningText: '核对进度',
    startText: '开始核对',
    loadingText: '核对中...',
    failureText: '报告自身核对失败',
    progressLabel: '报告自身核对进度',
    passDescription: '这些项目未发现内部不一致。',
  },
  'ptr-report': {
    label: 'PTR 与报告核对',
    shortLabel: 'PTR 核对',
    description:
      '分别上传 PTR 产品技术要求 PDF 和检验报告 PDF，系统会对照两份文件输出核对进度、发现问题和证据明细。',
    uploadTitle: '上传 PTR 与报告 PDF',
    waitingText: '选择 PTR 和检验报告后开始核对，这里会显示当前检查项、进度和执行日志。',
    runningText: 'PTR 与报告核对进度',
    startText: '开始 PTR 核对',
    loadingText: 'PTR 核对中...',
    failureText: 'PTR 与报告核对失败',
    progressLabel: 'PTR 与报告核对进度',
    passDescription: '这些项目未发现 PTR 与报告之间的不一致。',
  },
};
const ENABLED_CHECK_IDS = [
  'C00',
  'C01',
  'C02',
  'C03',
  'C04',
  'C06',
  'C07',
  'C08',
  'C12',
  'C13',
  'C14',
  'C15',
  'C16',
] as const;
const ENABLED_CHECK_COUNT = ENABLED_CHECK_IDS.length;

function getLastTaskKey(mode: CheckMode) {
  return `report-self-check:${mode}:last-task-id`;
}

function delay(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function formatFileSize(size: number) {
  if (size < 1024 * 1024) return `${Math.max(1, Math.round(size / 1024))} KB`;
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}

function groupChecks(checks: CheckResult[]) {
  return {
    error: checks.filter((check) => check.status === 'error'),
    warning: checks.filter((check) => check.status === 'warning'),
    pass: checks.filter((check) => check.status === 'pass'),
  };
}

function ResultGroup({
  title,
  description,
  checks,
}: {
  title: string;
  description: string;
  checks: CheckResult[];
}) {
  if (checks.length === 0) return null;

  return (
    <section className="result-group">
      <div className="section-heading">
        <div>
          <h2>{title}</h2>
          <p>{description}</p>
        </div>
        <span>{checks.length} 项</span>
      </div>
      <div className="check-grid">
        {checks.map((check) => (
          <CheckResultCard key={check.check_id} check={check} />
        ))}
      </div>
    </section>
  );
}

export function ReportSelfCheckPage() {
  const [mode, setMode] = useState<CheckMode>('self');
  const [file, setFile] = useState<File | null>(null);
  const [ptrFile, setPtrFile] = useState<File | null>(null);
  const [reportFile, setReportFile] = useState<File | null>(null);
  const [result, setResult] = useState<ReportSelfCheckResult | null>(null);
  const [task, setTask] = useState<ReportSelfCheckTask | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const requestTokenRef = useRef(0);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const ptrFileInputRef = useRef<HTMLInputElement | null>(null);
  const reportFileInputRef = useRef<HTMLInputElement | null>(null);

  async function applyTask(nextTask: ReportSelfCheckTask, requestToken: number, taskMode: CheckMode) {
    if (requestTokenRef.current === requestToken) {
      setTask(nextTask);
    }

    while (requestTokenRef.current === requestToken && nextTask.status === 'running') {
      await delay(POLL_INTERVAL_MS);

      if (requestTokenRef.current !== requestToken) {
        return;
      }

      nextTask = await getReportSelfCheckTask(nextTask.task_id);

      if (requestTokenRef.current !== requestToken) {
        return;
      }

      setTask(nextTask);
    }

    if (requestTokenRef.current === requestToken && nextTask.status === 'completed' && nextTask.result) {
      setResult(nextTask.result);
    }

    if (requestTokenRef.current === requestToken && nextTask.status === 'error') {
      setError(nextTask.error ?? MODE_COPY[taskMode].failureText);
      window.localStorage.removeItem(getLastTaskKey(taskMode));
    }
  }

  function restoreTask(nextMode: CheckMode) {
    const taskId = window.localStorage.getItem(getLastTaskKey(nextMode));
    if (!taskId) {
      return;
    }

    const requestToken = requestTokenRef.current + 1;
    requestTokenRef.current = requestToken;
    setLoading(true);

    getReportSelfCheckTask(taskId)
      .then((restoredTask) => applyTask(restoredTask, requestToken, nextMode))
      .catch(() => {
        window.localStorage.removeItem(getLastTaskKey(nextMode));
      })
      .finally(() => {
        if (requestTokenRef.current === requestToken) {
          setLoading(false);
        }
      });
  }

  useEffect(() => {
    restoreTask(mode);
  }, []);

  function clearTaskState(nextMode: CheckMode, clearSavedTask: boolean) {
    requestTokenRef.current += 1;
    setError(null);
    setResult(null);
    setTask(null);
    setLoading(false);
    if (clearSavedTask) {
      window.localStorage.removeItem(getLastTaskKey(nextMode));
    }
  }

  function handleModeChange(nextMode: CheckMode) {
    if (nextMode === mode) {
      return;
    }

    setMode(nextMode);
    setFile(null);
    setPtrFile(null);
    setReportFile(null);
    if (fileInputRef.current) fileInputRef.current.value = '';
    if (ptrFileInputRef.current) ptrFileInputRef.current.value = '';
    if (reportFileInputRef.current) reportFileInputRef.current.value = '';
    clearTaskState(nextMode, false);
    restoreTask(nextMode);
  }

  function selectFile(nextFile: File | null) {
    if (!nextFile && fileInputRef.current) {
      fileInputRef.current.value = '';
    }
    setFile(nextFile);
    clearTaskState('self', true);
  }

  function selectPtrFile(nextFile: File | null) {
    if (!nextFile && ptrFileInputRef.current) {
      ptrFileInputRef.current.value = '';
    }
    setPtrFile(nextFile);
    clearTaskState('ptr-report', true);
  }

  function selectReportFile(nextFile: File | null) {
    if (!nextFile && reportFileInputRef.current) {
      reportFileInputRef.current.value = '';
    }
    setReportFile(nextFile);
    clearTaskState('ptr-report', true);
  }

  async function handleRun() {
    const canStartSelfCheck = mode === 'self' && file;
    const canStartPtrReportCheck = mode === 'ptr-report' && ptrFile && reportFile;

    if (loading || (!canStartSelfCheck && !canStartPtrReportCheck)) {
      return;
    }

    const requestToken = requestTokenRef.current + 1;
    requestTokenRef.current = requestToken;
    setLoading(true);
    setError(null);
    setResult(null);
    setTask(null);

    try {
      const nextTask =
        mode === 'self' ? await startReportSelfCheck(file as File) : await startPtrReportCheck(ptrFile as File, reportFile as File);
      window.localStorage.setItem(getLastTaskKey(mode), nextTask.task_id);
      await applyTask(nextTask, requestToken, mode);
    } catch (caught) {
      if (requestTokenRef.current === requestToken) {
        setError(caught instanceof Error ? caught.message : MODE_COPY[mode].failureText);
      }
    } finally {
      if (requestTokenRef.current === requestToken) {
        setLoading(false);
      }
    }
  }

  function handleExportPdf() {
    if (!result) {
      return;
    }
    const printed = printReportResultAsPdf(result, mode);
    if (!printed) {
      setError('未能打开 PDF 打印预览，请确认浏览器允许打印后重试。');
    }
  }

  const progressPercent = task && task.total_checks ? Math.round((task.completed_checks / task.total_checks) * 100) : 0;
  const grouped = result ? groupChecks(result.check_results) : null;
  const priorityChecks = result?.check_results.filter((check) => check.status !== 'pass') ?? [];
  const copy = MODE_COPY[mode];
  const canRun = mode === 'self' ? Boolean(file) : Boolean(ptrFile && reportFile);

  return (
    <main className="app-shell">
      <section className="hero">
        <div>
          <p className="eyebrow">Codex 报告核对工作台</p>
          <h1>{copy.label}</h1>
          <p>
            {copy.description}
            {mode === 'self' ? ` 当前启用 ${ENABLED_CHECK_COUNT} 个检查项。` : ''}
          </p>
        </div>
        <div className="hero-card">
          <strong>{mode === 'self' ? `${ENABLED_CHECK_COUNT} 项` : '范围'}</strong>
          <span>{mode === 'self' ? '已启用检查项' : '按首页检验项目'}</span>
        </div>
      </section>

      <section className="workspace-grid">
        <div className="upload-panel">
          <p className="eyebrow">第一步</p>
          <h2>选择核对模式</h2>
          <div className="mode-switch" role="radiogroup" aria-label="核对模式">
            {(Object.keys(MODE_COPY) as CheckMode[]).map((nextMode) => (
              <button
                aria-checked={mode === nextMode}
                className={mode === nextMode ? 'active' : ''}
                key={nextMode}
                role="radio"
                type="button"
                onClick={() => {
                  handleModeChange(nextMode);
                }}
              >
                {MODE_COPY[nextMode].label}
              </button>
            ))}
          </div>

          <h2>{copy.uploadTitle}</h2>

          {mode === 'self' ? (
            <>
              <input
                className="sr-only"
                id="report-file"
                ref={fileInputRef}
                type="file"
                accept="application/pdf,.pdf"
                onChange={(event) => {
                  selectFile(event.target.files?.[0] ?? null);
                }}
              />
              <label
                className="file-drop"
                htmlFor="report-file"
                onDragOver={(event) => {
                  event.preventDefault();
                }}
                onDrop={(event) => {
                  event.preventDefault();
                  selectFile(event.dataTransfer.files?.[0] ?? null);
                }}
              >
                <span>选择或拖入报告文件</span>
                <small>支持 PDF，建议先用样例报告验证流程。</small>
              </label>

              {file ? (
                <div className="selected-file">
                  <div>
                    <strong>{file.name}</strong>
                    <span>{formatFileSize(file.size)}</span>
                  </div>
                  <button
                    className="ghost-button"
                    type="button"
                    onClick={() => {
                      selectFile(null);
                    }}
                  >
                    清除
                  </button>
                </div>
              ) : null}
            </>
          ) : (
            <div className="dual-upload-grid">
              <div>
                <input
                  className="sr-only"
                  id="ptr-file"
                  ref={ptrFileInputRef}
                  type="file"
                  accept="application/pdf,.pdf"
                  onChange={(event) => {
                    selectPtrFile(event.target.files?.[0] ?? null);
                  }}
                />
                <label
                  className="file-drop compact"
                  htmlFor="ptr-file"
                  onDragOver={(event) => {
                    event.preventDefault();
                  }}
                  onDrop={(event) => {
                    event.preventDefault();
                    selectPtrFile(event.dataTransfer.files?.[0] ?? null);
                  }}
                >
                  <span>PTR 产品技术要求 PDF</span>
                  <small>选择或拖入 PTR 文件。</small>
                </label>

                {ptrFile ? (
                  <div className="selected-file">
                    <div>
                      <strong>{ptrFile.name}</strong>
                      <span>{formatFileSize(ptrFile.size)}</span>
                    </div>
                    <button
                      className="ghost-button"
                      type="button"
                      onClick={() => {
                        selectPtrFile(null);
                      }}
                    >
                      清除
                    </button>
                  </div>
                ) : null}
              </div>

              <div>
                <input
                  className="sr-only"
                  id="ptr-report-file"
                  ref={reportFileInputRef}
                  type="file"
                  accept="application/pdf,.pdf"
                  onChange={(event) => {
                    selectReportFile(event.target.files?.[0] ?? null);
                  }}
                />
                <label
                  className="file-drop compact"
                  htmlFor="ptr-report-file"
                  onDragOver={(event) => {
                    event.preventDefault();
                  }}
                  onDrop={(event) => {
                    event.preventDefault();
                    selectReportFile(event.dataTransfer.files?.[0] ?? null);
                  }}
                >
                  <span>report 检验报告 PDF</span>
                  <small>选择或拖入检验报告文件。</small>
                </label>

                {reportFile ? (
                  <div className="selected-file">
                    <div>
                      <strong>{reportFile.name}</strong>
                      <span>{formatFileSize(reportFile.size)}</span>
                    </div>
                    <button
                      className="ghost-button"
                      type="button"
                      onClick={() => {
                        selectReportFile(null);
                      }}
                    >
                      清除
                    </button>
                  </div>
                ) : null}
              </div>
            </div>
          )}

          <button className="primary-button" type="button" disabled={!canRun || loading} onClick={handleRun}>
            {loading ? copy.loadingText : copy.startText}
          </button>
        </div>

        <section className="progress-panel" aria-live="polite">
          <p className="eyebrow">运行状态</p>
          <h2>{task ? copy.runningText : '等待上传'}</h2>
          {task ? (
            <>
              <div className="progress-meter">
                <div>
                  <strong>{progressPercent}%</strong>
                  <span>
                    已完成 {task.completed_checks}/{task.total_checks} 项
                  </span>
                </div>
                <progress aria-label={copy.progressLabel} value={task.completed_checks} max={task.total_checks} />
              </div>
              <p className="current-check">
                当前：
                {task.current_check_id ? `${task.current_check_id} ${task.current_check_name}` : task.current_check_name}
              </p>
              <details className="technical-details">
                <summary>查看执行日志和任务 ID</summary>
                <p>任务 ID：{task.task_id}</p>
                <ol>
                  {task.logs.map((line, index) => (
                    <li key={`${line}-${index}`}>{line}</li>
                  ))}
                </ol>
              </details>
            </>
          ) : (
            <p className="muted">{copy.waitingText}</p>
          )}
        </section>
      </section>

      {error ? (
        <p className="error-banner" role="alert">
          {error}
        </p>
      ) : null}

      {result ? (
        <section className="result-area">
          <div className="result-context">
            <div className="result-title-row">
              <div>
                <p className="eyebrow">当前结果</p>
                <h2>{copy.label}</h2>
              </div>
              <button className="export-button" type="button" onClick={handleExportPdf}>
                导出 PDF
              </button>
            </div>
            {mode === 'ptr-report' ? (
              <p>
                PTR：{result.ptr_file_name ?? task?.ptr_file_name ?? '未返回文件名'}；报告：
                {result.report_file_name ?? task?.report_file_name ?? result.file_name}
              </p>
            ) : (
              <p>报告：{result.file_name}</p>
            )}
          </div>
          <OverallSummary result={result} />

          {priorityChecks.length > 0 ? (
            <section className="priority-strip">
              <h2>优先处理</h2>
              <p>{mode === 'self' ? '以下项目需要先复核或修正，再查看通过项。' : '以下 PTR 与报告差异需要先复核或修正，再查看通过项。'}</p>
              <div>
                {priorityChecks.map((check) => (
                  <a href={`#check-${check.check_id}`} key={check.check_id}>
                    {check.check_id} {check.check_name}
                  </a>
                ))}
              </div>
            </section>
          ) : null}

          {grouped ? (
            <>
              <ResultGroup
                title="发现问题"
                description="这些项目存在明确问题，建议优先处理。"
                checks={grouped.error}
              />
              <ResultGroup
                title="需要人工复核"
                description={mode === 'self' ? '这些项目证据不足或存在不确定性。' : '这些项目在 PTR 与报告对照中证据不足或存在不确定性。'}
                checks={grouped.warning}
              />
              <ResultGroup title="已通过" description={copy.passDescription} checks={grouped.pass} />
            </>
          ) : null}
        </section>
      ) : null}
    </main>
  );
}
