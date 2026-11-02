import type { Company } from './api.ts';
import type { Task } from './operatingResearch.ts';
export function researchTitle(task: Task, companies: Company[]) {
  const name = (id: string) => companies.find(c => c.company_id === id)?.name || '企业研究';
  return task.input.template === 'company_period_change'
    ? `${name(task.input.first.company_id)} · ${task.input.first.period.year} / ${task.input.second.period.year} 年`
    : `${name(task.input.first.company_id)} × ${name(task.input.second.company_id)} · ${task.input.first.period.year} 年`;
}

