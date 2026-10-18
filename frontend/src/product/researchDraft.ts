export type Config = { company: string; year: string; document: string; versions: Record<string, string>; facts: Record<string, string> };
import { metrics, sides, type Side, type Template } from './operatingResearch.ts';

export type Draft = { id: string; template: Template; config: Record<Side, Config>; stage: number; notice: string[] };
export const emptyConfig = (company = ''): Config => ({ company, year: '', document: '', versions: {}, facts: {} });
const clearSource = (c: Config): Config => ({ ...c, document: '', versions: {}, facts: {} });

// A draft belongs to one creation flow. Company filters and old company drafts
// never select its template. The URL carries intent only; task admission rechecks it.
export function draftIdentity(): string {
  const url = new URL(location.href);
  const id = url.searchParams.get('draft');
  if (id && /^[a-f0-9-]{36}$/.test(id) && url.searchParams.getAll('draft').length === 1) return id;
  const next = crypto.randomUUID();
  if (!url.searchParams.has('task')) {
    url.searchParams.set('draft', next);
    history.replaceState(null, '', url);
  }
  return next;
}
export function readDraft(id: string): Draft | null {
  try {
    const v = JSON.parse(sessionStorage.getItem(`findoc:research-draft-v2:${id}`) || 'null');
    if (v?.id !== id || !['company_period_change', 'company_same_period_comparison'].includes(v.template)
      || ![1, 2, 3].includes(v.stage) || !Array.isArray(v.notice) || !v.notice.every((n: unknown) => typeof n === 'string')) return null;
    for (const side of sides) {
      const c = v.config?.[side];
      if (!c || !['company', 'year', 'document'].every(k => typeof c[k] === 'string')
        || !['versions', 'facts'].every(k => c[k] && typeof c[k] === 'object' && !Array.isArray(c[k])
          && Object.entries(c[k]).every(([metric, value]) => metrics.includes(metric) && typeof value === 'string'))) return null;
    }
    return v;
  } catch { return null; }
}
export function writeDraft(draft: Draft) {
  try { sessionStorage.setItem(`findoc:research-draft-v2:${draft.id}`, JSON.stringify(draft)); } catch { /* optional intent */ }
}
export function changeDraftScope(config: Record<Side, Config>, template: Template, side: Side, update: Partial<Config>): Record<Side, Config> {
  const next = { ...config, [side]: { ...config[side], ...update } };
  if (update.company !== undefined && update.company !== config[side].company) {
    next[side] = clearSource(next[side]);
    if (template === 'company_period_change') {
      const other = side === 'first' ? 'second' : 'first';
      next[other] = clearSource({ ...config[other], company: update.company });
    }
  }
  if (update.year !== undefined && update.year !== config[side].year) {
    next[side] = clearSource(next[side]);
    if (template === 'company_same_period_comparison') {
      const other = side === 'first' ? 'second' : 'first';
      next[other] = clearSource({ ...config[other], year: update.year });
    }
  }
  if (update.document !== undefined && update.document !== config[side].document)
    next[side] = { ...next[side], versions: {}, facts: {} };
  return next;
}
export function changeDraftTemplate(config: Record<Side, Config>, template: Template): Record<Side, Config> {
  return { first: clearSource(config.first), second: clearSource({ ...config.second,
    company: template === 'company_period_change' ? config.first.company : config.second.company === config.first.company ? '' : config.second.company,
    year: template === 'company_same_period_comparison' ? config.first.year : config.second.year }) };
}
