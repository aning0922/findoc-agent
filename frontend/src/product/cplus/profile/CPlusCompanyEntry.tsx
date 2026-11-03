import { useEffect, useState } from 'react';
import type { Company } from '../../api.ts';
import { listDocuments } from '../../documentLibraryApi.ts';
import { CPlusCompany360 } from './CPlusCompany360.tsx';
import { AnnualDiffPanel, type AnnualSourceRef } from '../insights/AnnualDiffPanel.tsx';
import { PeerComparisonPanel, type PeerCollection } from '../comparisons/PeerComparisonPanel.tsx';
import { SegmentResearchPanel } from '../comparisons/SegmentCandidatesPanel.tsx';
import { ResearchTemplatesPanel } from '../templates/ResearchTemplatesPanel.tsx';
import type { ResearchDraft } from '../actions/researchDraft.ts';
import { CheckupExplanationPanel } from '../research/CheckupExplanationPanel.tsx';

export function CPlusCompanyEntry({companyId,companies}:{companyId:string;companies:Company[]}){
 const [sources,setSources]=useState<AnnualSourceRef[]>([]),[notice,setNotice]=useState('正在核验可用资料…'),[collections,setCollections]=useState<PeerCollection[]>([]),[refresh,setRefresh]=useState(0);
 useEffect(()=>{const controller=new AbortController();
  void listDocuments(controller.signal).then(async documents=>{
   const candidates=documents.filter(d=>d.status==='ready'&&d.metadata?.company_id);
   const results=await Promise.allSettled(candidates.map(async d=>{const response=await fetch(`/api/cplus/documents/${encodeURIComponent(d.document_id)}/research-source`,{signal:controller.signal,cache:'no-store'});if(!response.ok)throw Error();const s=await response.json() as AnnualSourceRef;if(s.kind!=='fast'||s.document_id!==d.document_id||s.company_id!==d.metadata?.company_id)throw Error();return s}));
   if(!controller.signal.aborted){const good=results.flatMap(r=>r.status==='fulfilled'?[r.value]:[]);setSources(good);setNotice(good.length<candidates.length?'部分资料未通过来源核验，已排除。':good.length?'只读来源核验完成。':'尚无可用于双年对比的完整年报。')}
  }).catch(()=>{if(!controller.signal.aborted)setNotice('资料身份暂不可核验，请稍后刷新。')});return()=>controller.abort();
 },[companyId,refresh]);
 useEffect(()=>{const controller=new AbortController();void Promise.allSettled(companies.map(async c=>{const r=await fetch(`/api/cplus/companies/${encodeURIComponent(c.company_id)}/statements`,{signal:controller.signal,cache:'no-store'});if(!r.ok)throw Error();return (await r.json()).collections as PeerCollection[]})).then(results=>{if(!controller.signal.aborted)setCollections(results.flatMap(r=>r.status==='fulfilled'?r.value:[]))});return()=>controller.abort()},[companies,refresh]);
 function draft(value:ResearchDraft){const id=crypto.randomUUID();sessionStorage.setItem(`findoc:cplus-research:draft:${id}`,JSON.stringify(value));window.location.assign(`/conversations?${new URLSearchParams({company:value.companyId,question:value.question,cplus_draft:id})}`)}
 return <><CPlusCompany360 companyId={companyId} companies={companies} onResearchDraft={draft}/>
 <p>{notice} <button onClick={()=>setRefresh(v=>v+1)}>刷新进阶研究资料</button></p>
 <details className="product-card cplus-module-card"><summary>跨年经营变化 · 双侧原文</summary><AnnualDiffPanel companyId={companyId} sources={sources.filter(s=>s.company_id===companyId)}/></details>
 <details className="product-card cplus-module-card"><summary>同行对标 · 明确选择可比数据</summary><p>先在各企业三表中提取候选，再刷新资料。每项选择具体期间，不自动挑最新版本。</p><PeerComparisonPanel companies={companies} collections={collections}/></details>
 <details className="product-card cplus-module-card"><summary>主营业务结构 · 产品与地区</summary><SegmentResearchPanel companyId={companyId} sources={sources.filter(s=>s.company_id===companyId)}/></details>
 <details className="product-card cplus-module-card"><summary>AI 体检解释 · 从程序规则到核查建议</summary><CheckupExplanationPanel companyId={companyId}/></details>
 <details className="product-card cplus-module-card"><summary>研究模板与指标释义</summary><ResearchTemplatesPanel companyId={companyId} sources={sources.filter(s=>s.company_id===companyId)} onResearchDraft={draft}/></details></>;
}
