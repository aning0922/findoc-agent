import {useState} from 'react';
import {createRoot} from 'react-dom/client';
import {CPlusWorkspace} from './product/cplus/CPlusWorkspace.tsx';
import type {CPlusData,View} from './product/cplus/CPlusWorkspace.tsx';
const data:CPlusData={company:'示例企业 A（虚构）',peer:'示例企业 B（虚构）',companyCode:'TEST-A',kpis:[{label:'关注企业',value:'12'},{label:'已准备年报',value:'42'},{label:'完成研究',value:'28'},{label:'导出报告',value:'16'}],series:[{year:'2022',value:52},{year:'2023',value:73},{year:'2024',value:91},{year:'2025',value:113}],statements:{balance:[{name:'总资产',current:'2,480',prior:'2,110'},{name:'总负债',current:'1,210',prior:'1,034'},{name:'货币资金',current:'370',prior:'298'}],income:[{name:'营业收入',current:'1,120',prior:'970'},{name:'归母净利润',current:'123',prior:'104'}],cash:[{name:'经营现金流净额',current:'160',prior:'137'},{name:'投资现金流净额',current:'-90',prior:'-74'}]}};
function Preview(){const [view,setView]=useState<View>('home');return <CPlusWorkspace view={view} onNavigate={setView} data={data} onAction={()=>{}}/>}
document.body.classList.add('cp-preview');
createRoot(document.getElementById('root')!).render(<Preview/>);
