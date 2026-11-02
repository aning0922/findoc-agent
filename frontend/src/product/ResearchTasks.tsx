import { useState } from 'react';
import type { Company } from './api.ts';
import { taskLabels } from './operatingResearch.ts';
import { taskPath, nextAction } from './researchJourney.ts';
import { useResearchTasks } from './useResearchTasks.ts';
import { researchTitle } from './researchTitle.ts';
import './ResearchDashboard.css';

export function ResearchTasks({ companies }: { companies: Company[] }) {
  const { tasks, error, loading, refresh } = useResearchTasks();
  const [status, setStatus] = useState(new URLSearchParams(location.search).get('status') === 'completed' ? 'completed' : 'all');
  const [company, setCompany] = useState('');
  const rows = tasks.filter(t => (!company || [t.input.first.company_id, t.input.second.company_id].includes(company)) && (status === 'all' || (status === 'completed' ? t.status === 'completed' : status === 'failed' ? ['failed', 'refused'].includes(t.status) : !['completed', 'failed', 'refused'].includes(t.status))));
  return <div className="research-dashboard"><header className="page-heading"><p className="eyebrow">RESEARCH</p><h1>研究任务</h1><p>继续核对、查看进度，或阅读已完成的研究。</p></header>
    <section className="dashboard-section"><div className="task-list-filters"><label>企业筛选<select value={company} onChange={e => setCompany(e.target.value)}><option value="">全部企业</option>{companies.map(c => <option key={c.company_id} value={c.company_id}>{c.name}</option>)}</select></label><label>任务状态<select value={status} onChange={e => setStatus(e.target.value)}><option value="all">全部任务</option><option value="pending">待处理</option><option value="completed">已完成</option><option value="failed">未取得结果</option></select></label><button onClick={refresh}>刷新记录</button></div>
      {loading ? <p role="status">正在读取研究任务…</p> : error ? <p role="alert">研究任务暂不可用：{error}。请刷新记录。</p> : rows.length ? <ul className="dashboard-list">{rows.map(t => <li key={t.task_id}><a href={taskPath(t)}><div><strong>{researchTitle(t, companies)}</strong><p>{taskLabels[t.status]} · {nextAction(t)}</p></div><span>{t.status === 'completed' ? '阅读结果' : '查看任务'} →</span></a></li>)}</ul> : <div className="dashboard-empty"><p>当前筛选下没有研究任务。</p><a href="/research?mode=operating&new=1">开始新研究 →</a></div>}
    </section></div>;
}
