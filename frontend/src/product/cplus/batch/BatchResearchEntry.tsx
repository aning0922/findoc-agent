import { useState } from 'react';
import type { Company } from '../../api.ts';
import { listDocuments } from '../../documentLibraryApi.ts';
import type { AnnualSourceRef } from '../insights/AnnualDiffPanel.tsx';
import { BatchResearchPanel } from './BatchResearchPanel.tsx';

export function BatchResearchEntry({companies}:{companies:Company[]}){
 const [sources,setSources]=useState<AnnualSourceRef[]>([]),[loaded,setLoaded]=useState(false),[busy,setBusy]=useState(false),[notice,setNotice]=useState('');
 async function load(){setBusy(true);try{const documents=await listDocuments(new AbortController().signal);const eligible=documents.filter(d=>d.status==='ready');const results=await Promise.allSettled(eligible.map(async d=>{const r=await fetch(`/api/cplus/documents/${encodeURIComponent(d.document_id)}/research-source`,{cache:'no-store'});if(!r.ok)throw Error();const ref=await r.json() as AnnualSourceRef;if(ref.kind!=='fast'||ref.document_id!==d.document_id||ref.company_id!==d.metadata?.company_id)throw Error();return ref}));setSources(results.flatMap(r=>r.status==='fulfilled'?[r.value]:[]));setLoaded(true);setNotice(results.some(r=>r.status==='rejected')?'部分资料未通过身份核验，未纳入批次选项。':'可用资料核验完成，尚未执行任务。')}catch{setNotice('批量资料暂不可核验，请稍后重试。')}finally{setBusy(false)}}
 return <section><button disabled={busy} onClick={()=>void load()}>{loaded?'刷新批量研究资料':'读取批量研究资料'}</button><p role="status">{notice}</p>{loaded&&<BatchResearchPanel key={sources.map(s=>s.source_revision).join(':')} companies={companies} sources={sources}/>}</section>;
}
