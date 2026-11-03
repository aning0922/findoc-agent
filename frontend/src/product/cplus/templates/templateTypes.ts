import type {AnnualSourceRef} from '../insights/AnnualDiffPanel.tsx';
export type TemplateId='overview'|'cash'|'peer'|'changes';
export const templates:{id:TemplateId;label:string;question:string}[]=[
 {id:'overview',label:'年度经营概览',question:'请结合所选年报原文整理主要业务、财务概览与经营风险。'},
 {id:'cash',label:'现金流质量',question:'请对照两年经营现金流与归母净利润，列出待核对的差异。'},
 {id:'peer',label:'竞争对标',question:'请对照明确选择企业的同年指标与竞争披露，不推定投资结论。'},
 {id:'changes',label:'经营变化分析',question:'请对照两年业务、研发与风险原文，区分双侧证据与缺失。'}];
export const labels:Record<string,string>={revenue:'营业收入',net_profit_parent:'归母净利润',operating_cash_flow:'经营现金流',total_assets:'总资产',total_liabilities:'总负债'};
export type Point={cell_id:string;company_id:string;report_year:number;metric_key:string;raw_decimal:string;raw_unit:string;financial_review:string;time:{kind:string;as_of_date?:string;period_start?:string;period_end?:string};evidence_refs:{document_id:string;source_revision:string;physical_page:number}[]};
export type Evidence={source_ref:AnnualSourceRef;physical_page:number;text:string};
export type TemplateResult={schema_version:'template-run-v1';run_id:string;revision:1;template_id:TemplateId;template_version:'cplus-template-v1';question:string;financial_authority:false;selected_sources:AnnualSourceRef[];financial_points:Point[];missing_metrics:{company_id:string;report_year:number;metric_key:string;reason:string}[];changes:{metric_key:string;delta_decimal:string|null;change_percent_decimal:string|null;reason:string|null;comparison_kind:string}[];checkup_rules:{rule_id:string;status:string;observation:string|null;reason:string|null}[];peer_comparisons:{metric_key:string;state:string;reason:string|null;point_refs:string[];differences:{delta_decimal:string}[]}[];topics:{topic:string;program_label:string;left:{state:string;evidence_refs:Evidence[]};right:{state:string;evidence_refs:Evidence[]}}[];findings:{section:string;evidence_ref:Evidence}[];interpretation:string|null;provider_outcome:string;current_source_status?:string};
export const uuid=/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/;
export function sameSources(a:AnnualSourceRef[],b:AnnualSourceRef[]){const keys:(keyof AnnualSourceRef)[]=['kind','workspace_id','company_id','document_id','source_revision','content_sha256','parser_version','report_year','attempt','report_type','basis','period_start','period_end','identity_status','selected_pages'];return a.length===b.length&&a.every(s=>b.some(r=>keys.every(k=>JSON.stringify(s[k]??null)===JSON.stringify(r[k]??null))))}
export async function readJSON<T>(path:string):Promise<T>{const r=await fetch('/api'+path,{cache:'no-store'});if(!r.ok)throw Error('只读查询未完成（'+r.status+'）');return r.json() as Promise<T>}
