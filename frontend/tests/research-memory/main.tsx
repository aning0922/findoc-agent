import { useState } from 'react';
import { createRoot } from 'react-dom/client';
import { ResearchMemoryPanel } from '../../src/product/researchMemory/ResearchMemoryPanel.tsx';
import { prepareVerifiedDemoHints } from '../../src/demo/demoHintBoundary.ts';
function Harness() {
  const [scope, setScope] = useState(0);
  return <div className="findoc-app"><button onClick={() => setScope(x => x + 1)}>切换上下文</button><button onClick={() => prepareVerifiedDemoHints({lease_generation: 2, seed_version:'test'})}>切换代次</button><ResearchMemoryPanel companyId={`company-${scope}`} conversationId={`conversation-${scope}`} /></div>;
}
createRoot(document.getElementById('root')!).render(<Harness />);
