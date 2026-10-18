import { useCallback, useEffect, useRef, useState } from "react";
import { json } from "./api.ts";
import type { Company, DataAccess } from "./api.ts";
import type { Task } from "./operatingResearch.ts";
import { ReportPaper } from "./ReportPaper.tsx";
import { ReportHistory, ReportSaveControls } from "./ReportHistory.tsx";
import { validateDraft } from "./reportDraft.ts";
import type { Draft } from "./reportDraft.ts";
import { assertSavedOwner } from './reportState.ts';
import './ReportWorkspace.css';
import { ReportContextHeader } from './TaskContextHeader.tsx';
import { ReportNavigation } from "./ReportNavigation.tsx";
import { useReportNavigation } from "./reportNavigationContext.ts";
import { reportPath } from "./productRoutes.ts";
export function ReportPreview(props: { companies: Company[]; access: DataAccess; company: string }) {
    return <ReportNavigation><ReportPreviewContent {...props} /></ReportNavigation>;
}
function ReportPreviewContent({ companies, access }: {
    companies: Company[];
    access: DataAccess;
    company: string;
}) {
    const [tasks, setTasks] = useState<Task[]>([]), [selected, setSelected] = useState(new URLSearchParams(location.search).get("task") || "");
    const [before, setBefore] = useState<number | null>(null), [draft, setDraft] = useState<Draft | null>(null), [error, setError] = useState(""), [busy, setBusy] = useState(false);
    const [reading, setReading] = useState(() => new URLSearchParams(location.search).has('report'));
    const { requestLeave } = useReportNavigation();
    const serial = useRef(0), controller = useRef<AbortController | null>(null);
    useEffect(() => () => { serial.current++; controller.current?.abort(); }, []);
    const simulated = (access.label || "").includes("simulated_test");
    const list = useCallback(async (cursor?: number) => {
        try {
            const p = await json<{
                items: Task[];
                next_before: number | null;
            }>(`/research/tasks?limit=50${cursor ? `&before=${cursor}` : ""}`, new AbortController().signal);
            setTasks(old => cursor ? [...old, ...p.items] : p.items);
            setBefore(p.next_before);
        }
        catch {
            setError("研究列表读取失败，请重试读取。");
        }
    }, []);
    useEffect(() => { const c = new AbortController(); void json<{
        items: Task[];
        next_before: number | null;
    }>("/research/tasks?limit=50", c.signal).then(p => { if (!c.signal.aborted) {
        setTasks(p.items);
        setBefore(p.next_before);
    } }).catch(() => { if (!c.signal.aborted)
        setError("研究列表读取失败，请重试读取。"); }); return () => c.abort(); }, []);
    useEffect(() => {
        const c = new AbortController();
        let checkSequence = 0;
        const check = async () => {
            const checking = ++checkSequence;
            if (!draft) {
                void list();
                return;
            }
            try {
                const task = await json<Task>(`/research/tasks/${draft.task_id}`, c.signal);
                if (task.revision !== draft.task_revision || task.publication_eligibility?.status !== "current_at_read")
                    throw new Error("研究来源或接受资格已失效");
                for (const document of [...new Map(draft.financial_facts.map(f => [f.document_id, f])).values()]) {
                    const source = await json<{
                        source_revision: string;
                        content_sha256: string;
                    }>(`/documents/${document.document_id}/source?${new URLSearchParams({ company_id: document.company_id, source_revision: document.source_revision })}`, c.signal);
                    if (source.source_revision !== document.source_revision)
                        throw new Error("PDF 来源已变化");
                }
                for (const id of new Set(draft.financial_facts.map(f => f.company_id))) {
                    const query = await access.query(id, c.signal);
                    for (const row of draft.financial_facts.filter(f => f.company_id === id)) {
                        if (!query.facts.some(f => f.fact_id === row.fact_id && f.fact_set_id === row.receipt_id && f.disclosure_version === row.disclosure_version && f.value_cny_yuan === row.value_cny_yuan && access.eligible(f)))
                            throw new Error("财务事实或接受凭证已失效");
                    }
                }
            }
            catch (e) {
                if (!c.signal.aborted && checking === checkSequence) {
                    setDraft(null);
                    setError(`当前草稿资格已撤销：${e instanceof Error ? e.message : "核验失败"}`);
                }
            }
        };
        window.addEventListener("focus", check);
        const timer = window.setInterval(check, 30000);
        return () => { c.abort(); window.removeEventListener("focus", check); clearInterval(timer); };
    }, [draft, access, list]);
    const available = tasks.filter(t => t.graph_version === "d21-operating-graph-v2" && t.status === "completed" && t.execution_status === "idle" && t.publication_eligibility?.status === "current_at_read");
    async function generate() {
        const id = ++serial.current;
        controller.current?.abort();
        const c = new AbortController();
        controller.current = c;
        setReading(false); setDraft(null);
        setError("");
        setBusy(true);
        try {
            const task = await json<Task>(`/research/tasks/${encodeURIComponent(selected)}`, c.signal);
            if (task.status !== "completed" || task.publication_eligibility?.status !== "current_at_read")
                throw new Error("研究当前资格已失效或资料不完整");
            const result = validateDraft(await json<Draft>("/reports/drafts", c.signal, { task_id: task.task_id, expected_revision: task.revision }), task, simulated);
            if (id === serial.current)
                setDraft(result);
        }
        catch (e) {
            if (id === serial.current && !c.signal.aborted)
                setError(`草稿生成失败：${e instanceof Error ? e.message : "来源失效或数据不完整"}。未生成报告；请核验来源与接受凭证后重新操作。`);
        }
        finally {
            if (id === serial.current)
                setBusy(false);
        }
    }
    const label = (t: Task) => { const a = companies.find(c => c.company_id === t.input.first.company_id)?.name || t.input.first.company_id; const b = companies.find(c => c.company_id === t.input.second.company_id)?.name || t.input.second.company_id; return t.input.template === "company_period_change" ? `${a} · ${t.input.second.period.year}→${t.input.first.period.year}` : `${a} vs ${b} · ${t.input.first.period.year}`; };
    return <div className={`report-workspace ${reading ? "report-reading-workspace" : ""}`}>
    {reading ? <div className="report-reading-heading"><h1>研究报告</h1><a href="/reports">返回报告库</a></div> : <div className="page-heading"><p className="eyebrow">REPORT LIBRARY</p><h1>报告</h1><p>全空间的已保存报告与准确版本。报告中的企业、期间和来源来自保存时的研究。新草稿需要明确生成和保存。</p></div>}
    <ReportHistory simulated={simulated} draftActive={!!selected || !!draft} onOpen={() => { serial.current++; controller.current?.abort(); setDraft(null); setBusy(false); setReading(true); setSelected(''); }} />
    <details className="surface report-draft-entry" open={!!selected}><summary>从已完成研究整理报告草稿</summary><section className="report-controls"><label>选择已完成研究<select value={selected} onChange={e => { const value = e.target.value; requestLeave(() => { serial.current++; controller.current?.abort(); setDraft(null); setBusy(false); setError(""); setReading(false); setSelected(value); }); }}><option value="">选择研究任务</option>{available.map(t => <option key={t.task_id} value={t.task_id}>{label(t)}</option>)}</select></label><button disabled={!available.some(t => t.task_id === selected) || busy} onClick={() => requestLeave(() => void generate())}>{busy ? "核验来源并生成中…" : "生成草稿"}</button><button onClick={() => requestLeave(() => { serial.current++; controller.current?.abort(); setDraft(null); setBusy(false); void list(); })}>刷新资格</button>{before && <button onClick={() => void list(before)}>加载更多研究</button>}{!available.length && <p>暂无当前有效的已完成研究。等待确认、失败、运行中和旧版任务不能生成报告。</p>}</section></details>
    {error && <p role="alert" className="operating-alert">{error}</p>}
    {draft && <><ReportContextHeader draft={draft} compact /><ReportSaveControls key={draft.task_id} draft={draft} simulated={simulated} onSaved={value => { assertSavedOwner(value, draft); window.location.assign(reportPath(value.report.report_id, value.report.revision)); }} /><ReportPaper draft={draft} onSourceInvalid={() => { setDraft(null); setError("草稿来源暂不可核验，请重新检查资料。"); }} /></>}

  </div>;
}
