import type { METRICS } from "../evidence/contracts.ts";
import type { LimitedContent, Task } from "./operatingResearch.ts";
export type FactRow = {
    side: "first" | "second";
    company_id: string;
    company_name: string;
    period: number;
    metric_key: keyof typeof METRICS;
    raw_value: string;
    raw_unit: string;
    value_cny_yuan: string;
    disclosure_version: string;
    receipt_id: string;
    fact_id: string;
    document_id: string;
    source_revision: string;
    physical_page: number;
};
type AnalysisRow = {
    metric_key: keyof typeof METRICS;
    direction: string;
    absolute_change: string;
    percentage_change: string | null;
    percentage_reason: string | null;
    absolute_formula_id: string;
    percentage_formula_id: string;
    absolute_expression: string;
    percentage_expression: string;
    limitations: {
        message: string;
    }[];
};
export type Draft = {
    schema_version: "report-draft-v1";
    task_id: string;
    task_revision: number;
    title: string;
    report_type: string;
    research_question: string;
    generated_at: string;
    executive_summary: string[];
    side_labels: {
        first: string;
        second: string;
    };
    financial_facts: FactRow[];
    financial_analysis: AnalysisRow[];
    operating_information: LimitedContent["operating_descriptions"];
    model_interpretations: LimitedContent["model_interpretations"];
    unresolved_questions: string[];
    limitations: string[];
    evidence_appendix: Record<string, unknown>;
    field_verification: {
        path: string;
        status: string;
        identity: string;
    }[];
    test_mode: "simulated_test" | null;
    watermark: string | null;
    status: string;
    persisted: false;
};
export function validateDraft(d: Draft, task: Task, simulated: boolean): Draft {
    if (d.schema_version !== "report-draft-v1" || d.task_id !== task.task_id || d.task_revision !== task.revision || d.persisted !== false || d.financial_facts.length !== 6 || d.financial_analysis.length !== 3 || (d.test_mode === "simulated_test") !== simulated || d.status !== (simulated ? "simulated_draft" : "qualified_draft") || (simulated && !d.watermark) || d.model_interpretations.some(i => i.validation_status !== "pending_semantic_review" || i.verified_operating_attribution !== false))
        throw new Error("报告结构或研究身份不一致");
    return d;
}
