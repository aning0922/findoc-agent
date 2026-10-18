import { useRef, useState } from 'react';
import styles from './ResearchJourney.module.css';
export function CompanySetup({ id, expanded = false }: { id?: string; expanded?: boolean }) {
  const [name, setName] = useState(''), [code, setCode] = useState(''), [exchange, setExchange] = useState('SSE');
  const [message, setMessage] = useState(''), [busy, setBusy] = useState(false), [unknown, setUnknown] = useState(false);
  const lock = useRef(false);
  return <details id={id} open={expanded || undefined} className={styles.upload}><summary>目录中没有要研究的企业？建立企业</summary><p>填写企业正式名称与证券身份，建立后再核对并绑定财报。</p><form onSubmit={async e => {
    e.preventDefault(); if (lock.current || unknown) return; lock.current = true; setBusy(true);
    try { const r = await fetch('/api/companies', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name, security_code: code, exchange, country: 'CN' }) });
      if (r.status >= 500) { setUnknown(true); throw new Error('建立企业结果未知，请先刷新企业目录核对，系统不会自动重新提交。'); }
      if (!r.ok) throw new Error(r.status === 409 ? '证券身份已存在，请刷新目录选择已有企业。' : '企业名称或证券身份未通过校验，请核对填写。');
      const v = await r.json(); if (typeof v.company_id !== 'string') { setUnknown(true); throw new Error('返回身份不完整，请只读刷新企业目录。'); }
      location.assign(`/research?${new URLSearchParams({ company: v.company_id, mode: 'operating', new: '1' })}`);
    } catch (error) { if (error instanceof TypeError) setUnknown(true); setMessage(error instanceof TypeError ? '连接中断，建立企业结果未知，请只读刷新目录核对。' : error instanceof Error ? error.message : '建立结果未知，请刷新目录核对。'); }
    finally { lock.current = false; setBusy(false); }
  }}><div className={styles.formGrid}><label>企业正式名称<input required value={name} onChange={e => setName(e.target.value)} /></label><label>证券代码<input required value={code} onChange={e => setCode(e.target.value)} /></label><label>交易所<select value={exchange} onChange={e => setExchange(e.target.value)}><option value="SSE">上海证券交易所</option><option value="SZSE">深圳证券交易所</option></select></label></div><button disabled={busy || unknown}>建立企业并开始研究</button></form>{message && <p role="alert">{message}</p>}<a href="/">只读刷新企业目录 →</a></details>;
}
