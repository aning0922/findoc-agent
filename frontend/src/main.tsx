import { lazy, StrictMode, Suspense } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
// App bootstrap lazily opens the product route; keep the legacy bundle independent.
// oxlint-disable-next-line react/only-export-components
const EvidenceWorkbench = lazy(() => import('./evidence/EvidenceWorkbench.tsx'))

// oxlint-disable-next-line react/only-export-components
const FinancialProduct = lazy(() => import('./product/FinancialProduct.tsx'))

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    {window.location.pathname === '/evidence' ? <Suspense fallback={<p role="status">正在打开证据工作台…</p>}><EvidenceWorkbench /></Suspense> : window.location.pathname === "/legacy" ? <App /> : <Suspense fallback={<p role="status">正在打开企业研究空间…</p>}><FinancialProduct /></Suspense>}
  </StrictMode>,
)
