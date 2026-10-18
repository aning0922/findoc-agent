import type { ResearchSection } from './productRoutes.ts';

// Targets mirror the sections rendered by TaskPanel and OperatingResearch.
export function researchChapters(section: ResearchSection, status: string) {
  return [
    ...(section !== 'financial' ? [{ id: 'research-facts', label: '事实与证据' }] : []),
    ...(section === 'financial' || section === 'operating' && status === 'completed'
      ? [{ id: 'research-results', label: '分析结果' }] : []),
    { id: 'research-history', label: '研究记录' },
  ];
}
export function focusResearchTarget(): boolean {
  const id = location.hash.slice(1);
  if (!/^research-(facts|results|history|recovery)$|^fact-(first|second)-(revenue|net_profit_parent|operating_cash_flow)$/.test(id)) return false;
  const target = document.getElementById(id);
  if (!target) return false;
  for (let parent = target.parentElement; parent; parent = parent.parentElement)
    if (parent instanceof HTMLDetailsElement) parent.open = true;
  target.focus({ preventScroll: true });
  target.scrollIntoView({ block: 'start' });
  return true;
}
