import type { Fact } from "./api.ts";
import type { Task } from "./operatingResearch.ts";
import { sides } from "./operatingResearch.ts";

export type SourceIntent = Pick<
  Fact,
  | "company_id"
  | "period"
  | "metric_key"
  | "document_id"
  | "source_revision"
  | "disclosure_version"
  | "fact_set_id"
  | "fact_id"
>;
const fields = [
  "company_id",
  "period",
  "metric_key",
  "document_id",
  "source_revision",
  "disclosure_version",
  "fact_set_id",
  "fact_id",
] as const;
export function intentOf(f: Fact): SourceIntent {
  return Object.fromEntries(fields.map((key) => [key, f[key]])) as SourceIntent;
}
// Persisted data is navigation intent. Only current server query facts can restore a selection.
export function revalidateIntents(
  raw: unknown,
  facts: Fact[],
  eligible: (f: Fact) => boolean,
): Record<string, string> {
  if (!Array.isArray(raw)) return {};
  const choices: Record<string, string> = {},
    conflicts = new Set<string>();
  for (const hint of raw) {
    if (
      !hint ||
      fields.some(
        (key) => typeof hint[key] !== (key === "period" ? "number" : "string"),
      )
    )
      continue;
    const matches = facts.filter(
      (f) => eligible(f) && fields.every((key) => f[key] === hint[key]),
    );
    if (matches.length !== 1) continue;
    const key = `${matches[0].period}/${matches[0].metric_key}`;
    if (choices[key] && choices[key] !== matches[0].fact_id) conflicts.add(key);
    choices[key] = matches[0].fact_id;
  }
  for (const key of conflicts) delete choices[key];
  return choices;
}
export function frozenTaskIntents(
  task: Task,
  company: string,
  facts: Fact[],
  eligible: (f: Fact) => boolean,
): SourceIntent[] {
  if (task.publication_eligibility?.status === "invalidated") return [];
  return sides.flatMap((side) => {
    const s = task.active_input[side];
    if (s.company_id !== company) return [];
    return s.choices.flatMap((choice) => {
      const revision = task.input.reports.find(
        (r) => r.document_id === choice.document_id,
      )?.expected_source_revision;
      const matches = facts.filter(
        (f) =>
          eligible(f) &&
          f.company_id === company &&
          f.period === s.period.year &&
          f.metric_key === choice.metric_key &&
          f.document_id === choice.document_id &&
          f.disclosure_version === choice.disclosure_version &&
          f.source_revision === revision &&
          (!choice.fact_id || f.fact_id === choice.fact_id) &&
          (!choice.fact_set_id || f.fact_set_id === choice.fact_set_id),
      );
      return matches.length === 1 ? [intentOf(matches[0])] : [];
    });
  });
}
export function savedSourceIntents(company: string): unknown {
  try {
    return JSON.parse(
      localStorage.getItem(`findoc:source-intent:${company}`) || "[]",
    );
  } catch {
    return [];
  }
}
export function saveSourceIntents(
  company: string,
  choices: Record<string, string>,
  facts: Fact[],
) {
  try {
    localStorage.setItem(
      `findoc:source-intent:${company}`,
      JSON.stringify(
        Object.entries(choices).flatMap(([key, id]) => {
          const f = facts.find(
            (f) =>
              f.company_id === company &&
              `${f.period}/${f.metric_key}` === key &&
              f.fact_id === id,
          );
          return f ? [intentOf(f)] : [];
        }),
      ),
    );
  } catch {
    /* server research input remains recoverable */
  }
}

export type SourceScope = {
  company: string;
  currentYear: number;
  previousYear: number;
  metrics: string[];
};
export function recoverTaskSources(
  task: Task,
  company: string,
  facts: Fact[],
  eligible: (f: Fact) => boolean,
) {
  const { first, second } = task.active_input;
  if (
    task.input.template !== "company_period_change" ||
    first.company_id !== company ||
    second.company_id !== company
  )
    throw new Error(
      "该研究不属于当前企业的两期分析，请更换研究来源或明确选择范围。",
    );
  const scope: SourceScope = {
    company,
    currentYear: first.period.year,
    previousYear: second.period.year,
    metrics: [
      ...new Set(
        [...first.choices, ...second.choices].map((c) => c.metric_key),
      ),
    ],
  };
  const intents = frozenTaskIntents(task, company, facts, eligible);
  // A task owns its whole scope. Missing task slots never inherit local hints.
  const choices = revalidateIntents(intents, facts, eligible);
  return { scope, choices, intents };
}
export function sourceCoverage(
  scope: SourceScope,
  choices: Record<string, string>,
  intents: SourceIntent[],
  facts: Fact[],
  eligible: (f: Fact) => boolean,
) {
  const validated = revalidateIntents(intents, facts, eligible);
  const periods = [
    ...new Set([scope.currentYear, scope.previousYear].filter((y) => y > 0)),
  ];
  const slots = periods.flatMap((year) =>
    scope.metrics.map((metric) => {
      const key = `${year}/${metric}`;
      const options = facts.filter(
        (f) =>
          f.company_id === scope.company &&
          f.period === year &&
          f.metric_key === metric &&
          eligible(f),
      );
      const chosen = choices[key];
      const valid =
        !!chosen &&
        validated[key] === chosen &&
        options.some((f) => f.fact_id === chosen);
      const status = valid
        ? "valid"
        : chosen
          ? "invalid"
          : options.length > 1
            ? "ambiguous"
            : "missing";
      return { key, year, metric, status, factId: valid ? chosen : undefined };
    }),
  );
  return {
    expected: slots.length,
    valid: slots.filter((s) => s.status === "valid").length,
    unresolved: slots.filter((s) => s.status !== "valid"),
    choices: Object.fromEntries(
      slots.filter((s) => s.factId).map((s) => [s.key, s.factId!]),
    ),
  };
}
