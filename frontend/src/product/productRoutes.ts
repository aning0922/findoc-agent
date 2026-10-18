export type Page = 'home' | 'companies' | 'overview' | 'documents' | 'analysis' | 'research' | 'reports';
export type ResearchSection = 'sources' | 'financial' | 'operating';
export type ProductRoute = { page: Page; company: string; home: boolean; task: string; run: string; report: string; revision: string; mode: 'qa' | 'operating'; section: ResearchSection; newResearch: boolean; key: string };

// URLs are read-only navigation intent. Each business component must validate server identity.
export function readProductRoute(url: URL): ProductRoute {
  const q = url.searchParams;
  for (const name of ['company', 'task', 'run', 'report', 'revision', 'mode', 'section', 'new', 'return_task', 'draft'])
    if (q.getAll(name).length > 1) throw new Error('地址身份参数重复，请从我的研究重新进入。');
  const match = url.pathname.match(/^\/companies\/([^/]+)\/(overview|analysis|documents)$/);
  const view = q.get('view');
  const page: Page = url.pathname === '/' ? 'home' : match ? match[2] as Page
    : url.pathname === '/research' ? 'research' : url.pathname === '/reports' ? 'reports'
    : url.pathname === '/companies' && ['overview', 'analysis', 'documents'].includes(view || '') ? view as Page : 'companies';
  return { page, home: page === 'home', company: match ? decodeURIComponent(match[1]) : q.get('company') || '',
    task: q.get('task') || '', run: q.get('run') || '', report: q.get('report') || '', revision: q.get('revision') || '',
    mode: q.get('mode') === 'qa' ? 'qa' : 'operating', newResearch: q.get('new') === '1',
    section: ['sources', 'financial'].includes(q.get('section') || '') ? q.get('section') as ResearchSection : 'operating',
    key: url.pathname + url.search };
}
export function pathFor(page: Page, company = ''): string {
  if (page === 'home') return `/${company ? `?company=${encodeURIComponent(company)}` : ''}`;
  if (page === 'companies') return '/companies';
  if (page === 'research' || page === 'reports') return `/${page}${company ? `?company=${encodeURIComponent(company)}` : ''}`;
  return company ? `/companies/${encodeURIComponent(company)}/${page}` : `/companies?view=${page}`;
}
export function taskSectionPath(task: string, company: string, section: ResearchSection): string {
  return `/research?${new URLSearchParams({ company, mode: 'operating', task, section })}`;
}
export function qaPath(company = '', returnTask = ''): string {
  return `/research?${new URLSearchParams({ ...(company ? { company } : {}), mode: 'qa', ...(returnTask ? { return_task: returnTask } : {}) })}`;
}
export function reportPath(report: string, revision: number): string {
  return `/reports?${new URLSearchParams({ report, revision: String(revision) })}`;
}
