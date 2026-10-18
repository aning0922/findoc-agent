import { useEffect, useRef, useState } from 'react';
import { QADialog } from './QADialog.tsx';
import { StatusNotice } from './StatusNotice.tsx';
import { readExactReport, type ReportDetail } from './reportPersistence.ts';
import { compareReportFields } from './reportComparison.ts';
export function ReportVersionComparison({ detail, simulated, close }: { detail: ReportDetail; simulated: boolean; close: () => void }) {
  const [left, setLeft] = useState(Math.max(1, detail.report.revision - (detail.report.revision === detail.current_revision ? 1 : 0)));
  const [right, setRight] = useState(detail.current_revision), [pair, setPair] = useState<[ReportDetail, ReportDetail] | null>(null);
  const [error, setError] = useState(''), [attempt, setAttempt] = useState(0), [busy, setBusy] = useState(true);
  const serial = useRef(0);
  useEffect(() => {
    const controller = new AbortController(), n = ++serial.current;
    if (left >= right) return () => controller.abort();
    void Promise.allSettled([
      readExactReport(detail.report.report_id, left, simulated, controller.signal),
      readExactReport(detail.report.report_id, right, simulated, controller.signal),
    ]).then(results => {
      if (controller.signal.aborted || n !== serial.current) return;
      if (results[0].status === 'fulfilled' && results[1].status === 'fulfilled') {
        setPair([results[0].value, results[1].value]);
      } else setError('版本读取失败或身份不一致，未完成对照。请重新读取两个版本。');
      setBusy(false);
    });
    return () => controller.abort();
  }, [detail.report.report_id, left, right, simulated, attempt]);
  useEffect(() => {
    const refresh = () => { setPair(null); setError(''); setBusy(true); setAttempt(n => n + 1); }; window.addEventListener('focus', refresh); document.addEventListener('visibilitychange', refresh);
    const timer = setInterval(refresh, 30000);
    return () => { clearInterval(timer); window.removeEventListener('focus', refresh); document.removeEventListener('visibilitychange', refresh); };
  }, []);
  const comparison = pair && compareReportFields(...pair);
  const choices = (value: number, set: (n: number) => void, label: string) => <label>{label}<select aria-label={label} value={value} onChange={e => { setPair(null); setError(''); setBusy(true); set(Number(e.target.value)); }}>{Array.from({ length: detail.current_revision }, (_, i) => <option key={i} value={i+1}>v{i+1}</option>)}</select></label>;
  return <QADialog title="报告版本对照" close={close} className="report-comparison-dialog"><section aria-label="报告版本对照">
    <p>仅对照保存的字段文字；文字发生变化不代表正确性提升。用户断言与经营解释均待人工语义审阅。</p>
    <div className="report-comparison-selectors">{choices(left, setLeft, '较早版本')}{choices(right, setRight, '较新版本')}<button disabled={busy && left < right} onClick={() => { setPair(null); setError(''); setBusy(true); setAttempt(n => n + 1); }}>重新读取两个版本</button></div>
    {busy && left < right && <p role="status">正在分别核验两个精确版本…</p>}{(error || left >= right) && <p role="alert">{error || '请选择较早版本与较新版本。'}</p>}
    {pair && comparison && <>
      {pair.some(d => d.current_eligibility.status === 'invalidated') && <StatusNotice state="invalidated" title="来源已失效 · 仅供历史审计对照">对照不能恢复保存或导出资格。</StatusNotice>}
      <div className="report-comparison-times">{pair.map(d => <p key={d.report.revision}><strong>v{d.report.revision}</strong> · 保存于 {new Date(d.report.created_at).toLocaleString('zh-CN')}<br />{d.report.editor_revision.title || d.report.trusted_snapshot.title}</p>)}</div>
      <div className="report-comparison-fields">{[comparison.title, ...comparison.conclusions].map(row => <section key={row.field} data-field={row.field} data-changed={row.changed}><h3>{row.field} · {row.changed ? '字段变化' : '相同'}</h3><div>{[row.left, row.right].map((text, i) => <div key={i}><strong>v{pair[i].report.revision}</strong><p>{text ?? (row.field === '用户编辑标题' ? '未设置用户标题（使用原系统标题）' : '此版本未设置此结论')}</p></div>)}</div></section>)}</div>
      <p>{comparison.financialEqual ? '固定财务事实与公式快照相同' : '固定财务事实或公式快照存在变化，请查阅证据'}</p>
      <p>{comparison.sourcesEqual ? '来源快照相同' : '来源快照存在变化，请查阅证据'}</p><p>{comparison.frozenEqual ? '冻结研究正文与证据相同' : '冻结研究正文或证据存在变化，需审计核验'}</p><p>各版本的生成时间与保存时间分别保留于审计附录。{!comparison.generationTimeEqual && '生成时间不同。'}</p>
    </>}
    <button onClick={close}>返回报告</button>
  </section></QADialog>;
}
