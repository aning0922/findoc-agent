import type { Company } from './api.ts';
import { CompanySetup } from './CompanySetup.tsx';
import { pathFor, qaPath } from './productRoutes.ts';
export function CompanyDirectory({ companies, loading }: { companies: Company[]; loading: boolean }) {
  return <div className="company-directory">
    <header className="page-heading"><p className="eyebrow">COMPANIES & DOCUMENTS</p><h1>企业与资料</h1><p>选择企业查看年报、核对财务数据，或开展新的研究。</p></header>
    <section className="surface directory-card" aria-label="企业目录">
      <h2>我的企业</h2>
      {!companies.length && <p role="status">{loading ? '正在读取企业目录…' : '尚无企业，请建立企业后准备资料。'}</p>}
      <ul className="company-list">{companies.map(c => <li key={c.company_id} data-company-id={c.company_id}>
        <div><h3>{c.name}</h3><p>{c.security_code} · {c.exchange}</p></div>
        <nav aria-label={`${c.name} 功能`}><a href={pathFor('overview', c.company_id)}>企业概览</a><a href={pathFor('documents', c.company_id)}>财报资料</a><a href={pathFor('analysis', c.company_id)}>财务分析</a><a href={qaPath(c.company_id)}>原文问答</a></nav>
      </li>)}</ul>
    </section>
    <CompanySetup />
  </div>;
}
