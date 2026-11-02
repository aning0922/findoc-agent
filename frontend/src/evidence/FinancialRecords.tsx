import { useEffect, useState } from 'react';
import { FinancialSession } from './FinancialSession.tsx';
import { discoverRecords, recordSelection } from './recordApi.ts';
import { METRICS } from './contracts.ts';
import { queryFacts } from '../product/operatingResearch.ts';
import type { Receipt } from './reviewApi.ts';

export function FinancialRecords(props: Parameters<typeof FinancialSession>[0] & {
  record: string; receiptId: string; factSetId: string;
  allowWrites?: boolean;
  compact?: boolean;
  selectMode: (record: string, receipt?: string, factSet?: string) => void;
}) {
  const { source } = props.data;
  const [records, setRecords] = useState<{ receipt: Receipt; saved: boolean | null }[]>([]);
  const [message, setMessage] = useState(props.receiptId ? '' : '正在只读查询本来源的接受与保存记录…');
  const [retry, setRetry] = useState(0);
  const year = Number(props.route.period) || source.report_year;
  const keys = (props.groupMetrics || Object.keys(METRICS)).slice().sort().join('|');
  useEffect(() => {
    const c = new AbortController();
    if (props.receiptId) return () => c.abort();
    void discoverRecords(source, recordSelection(source, [year], keys.split('|')), c.signal).then(async items => {
      const facts = await queryFacts(source.company_id, c.signal);
      const rows = items.map(receipt => ({ receipt, saved: facts.facts.some(f => f.fact_set_id === receipt.receipt_id && f.current_valid && f.source_revision === source.source_revision) ? true : null }));
      if (!c.signal.aborted) { setRecords(rows); setMessage(items.length ? '' : '本范围暂无已接受记录。本次勾选与核对只有明确提交后才形成接受。'); }
    }).catch(e => { if (!c.signal.aborted) { setRecords([]); setMessage(`记录暂不可核验：${e.message}`); } });
    return () => c.abort();
  }, [source, year, keys, retry, props.receiptId]);
  const selected = !!props.receiptId;
  const newReview = props.record === 'new';
  const readOnly = props.record !== 'save';
  const recordContent = <>
      <p>核对记录、数据保存和研究执行分别记录。阅读、刷新和返回不会提交操作。</p>
      {message && <p role="status">{message}</p>}
      {records.map(({ receipt, saved }) => <article key={receipt.receipt_id}>
        <p>{saved === true ? `本来源已有 ${receipt.review.candidates.length} 项已保存财务事实` : saved === false ? '已接受未保存' : '保存结果暂不可核验'} · {receipt.confirmation_kind === 'simulated_test' ? '隔离模拟' : '人工接受'} · 接受时间 {receipt.accepted_at}</p>
        <p>凭证 {receipt.receipt_id}</p>
        <button onClick={() => props.selectMode('read', receipt.receipt_id, saved === true ? receipt.receipt_id : '')}>查看这条核对记录（只读）</button>
      </article>)}
      {records.length > 1 && <p>有多条接受记录，请按凭证身份明确选择。系统不会自动选最近一条。</p>}
      <button onClick={() => setRetry(n => n + 1)}>刷新核对记录（只读）</button>
      {!newReview && props.allowWrites !== false && <button onClick={() => props.selectMode('new')}>开始新核对</button>}
      {props.returnHref && <a href={props.returnHref}>返回原研究（只读） →</a>}
  </>;
  return <>
    <section className="operating-card" aria-label="财务核对记录">
      {props.compact ? <details open={!newReview}><summary>{newReview ? '查看已有核对记录' : '财务核对记录 · 只读阅读'}</summary>{recordContent}</details> : <><h2>{newReview ? '新核对流程' : '财务核对记录 · 只读阅读'}</h2>{recordContent}</>}
    </section>
    {(newReview || selected) && <FinancialSession {...props}
      key={`${newReview ? 'new' : props.receiptId}:${props.record}`}
      recordId={selected ? props.receiptId : undefined}
      expectedFactSet={props.factSetId || undefined}
      readOnly={props.allowWrites === false || selected && readOnly}
      openSave={props.allowWrites === false ? undefined : () => props.selectMode('save', props.receiptId, props.factSetId)} />}
  </>;
}
