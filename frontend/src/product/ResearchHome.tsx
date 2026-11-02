import type { Company, DataAccess } from './api.ts';
import { taskLabels } from './operatingResearch.ts';
import { taskPath, nextAction } from './researchJourney.ts';
import { useResearchTasks } from './useResearchTasks.ts';
import './ResearchDashboard.css';
import { researchTitle } from './researchTitle.ts';


export function ResearchHome({ companies, company }: { companies: Company[]; company: string; access?: DataAccess }) {
  const { tasks, error, loading, refresh } = useResearchTasks();
  const rows = tasks;
  const pending = rows.filter(t => !['completed', 'failed', 'refused'].includes(t.status));
  const failures = rows.filter(t => ['failed', 'refused'].includes(t.status));
  const current = pending[0] || failures[0];
  const completed = rows.filter(t => t.status === 'completed').slice(0, 5);
  return <div className="research-dashboard">
    <header className="dashboard-start" aria-label="开始新研究">
      <p className="eyebrow">你的财报研究工作台</p><h1>每一份研究，从可靠的依据开始</h1>
      <p>选好企业与年报，核对关键数据，再查看分析与原文证据。</p>
      <div className="dashboard-actions"><a className="dashboard-primary" href={`/research?${new URLSearchParams({ mode: 'operating', new: '1', ...(company ? { company } : {}) })}`}>开始新研究 <span aria-hidden="true">→</span></a><a href="/companies">添加企业与年报</a></div>
    </header>
    <section className="dashboard-section" aria-labelledby="pending-heading">
      <div className="dashboard-section-heading"><h2 id="pending-heading">需要继续的研究</h2><a href="/tasks">查看全部任务 →</a></div>
      {loading ? <p role="status">正在读取研究记录…</p> : error ? <div role="alert"><p>研究记录暂不可用：{error}</p><button onClick={refresh}>重新读取记录</button></div> : current ? <div className="dashboard-pending">
        <span className="dashboard-badge">{taskLabels[current.status]}</span><h3>{researchTitle(current, companies)}</h3>
        <p>{current.waiting_checkpoint ? '核对并保存所需的六项数据后，可继续研究。进入任务可查看每项进度。' : nextAction(current)}</p>
        <a href={taskPath(current)}>{current.waiting_checkpoint ? '继续核对数据' : ['failed', 'refused'].includes(current.status) ? '查看原因与下一步' : '查看研究进度'} →</a>
        {pending.length > 1 && <p className="dashboard-meta">另有 {pending.length - 1} 项研究待继续</p>}
      </div> : <div className="dashboard-empty"><h3>暂时没有待办</h3><p>新研究的核对进度和待处理事项会显示在这里。</p></div>}
    </section>
    <section className="dashboard-section" aria-labelledby="recent-heading">
      <div className="dashboard-section-heading"><h2 id="recent-heading">最近完成</h2><a href="/tasks?status=completed">全部已完成研究 →</a></div>
      <p className="dashboard-meta">阅读已保存的研究；打开后会重新核验来源，不会重新运行模型。</p>
      {loading ? <p role="status">正在读取已完成研究…</p> : error ? <p>记录暂未读到，请先重新读取。</p> : completed.length ? <ul className="dashboard-list">{completed.map(t => <li key={t.task_id}><a href={taskPath(t)}><div><strong>{researchTitle(t, companies)}</strong><p>已完成 · 模型解释待人工审阅</p></div><span>阅读结果 →</span></a></li>)}</ul> : <div className="dashboard-empty"><p>完成第一份研究后，你可以在这里继续阅读。</p></div>}
    </section>
  </div>;
}
