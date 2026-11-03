import {useState} from 'react';
import {createRoot} from 'react-dom/client';
import {ShowcaseReportsPanel} from '../../src/product/showcaseReports/ShowcaseReportsPanel.tsx';
function App(){const [scope,setScope]=useState('generation-1');return <div className="findoc-app"><button onClick={()=>setScope('generation-2')}>切换范围</button><ShowcaseReportsPanel scopeKey={scope}/></div>}
createRoot(document.getElementById('root')!).render(<App/>);
