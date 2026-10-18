import { validateHistory, type HistoryItem, type HistoryPage } from "./researchHistory.ts";
import { CompanySetup } from "./CompanySetup.tsx";
import { useEffect, useState } from "react";
import { json, productionAccess } from "./api.ts";
import { validateSource } from "../evidence/contracts.ts";
import type { Source } from "../evidence/contracts.ts";
import type { Company, DataAccess } from "./api.ts";
import {
  taskLabels,
  validateTask,
  sides,
  slotFacts,
} from "./operatingResearch.ts";
import type { Task } from "./operatingResearch.ts";
import { taskPath, nextAction } from "./researchJourney.ts";
import styles from "./ResearchJourney.module.css";

export function ResearchHome({
  companies,
  company,
  access = productionAccess,
}: {
  companies: Company[];
  company: string;
  access?: DataAccess;
}) {
  const [tasks, setTasks] = useState<Task[]>([]),
    [error, setError] = useState("");
  const [retry, setRetry] = useState(0),
    [loading, setLoading] = useState(true);
  useEffect(() => {
    const c = new AbortController();
    void (async () => {
      const rows: Task[] = [];
      let before: number | null = null;
      do {
        const v: {
          schema_version: string;
          items: Task[];
          next_before: number | null;
        } = await json(
          `/research/tasks?limit=50${before ? `&before=${before}` : ""}`,
          c.signal,
        );
        if (
          v.schema_version !== "template-task-history-v1" ||
          !Array.isArray(v.items) ||
          (v.next_before !== null &&
            (!Number.isSafeInteger(v.next_before) ||
              v.next_before < 1 ||
              (before !== null && v.next_before >= before)))
        )
          throw new Error("研究记录读取不完整。");
        rows.push(...v.items.map((t) => validateTask(t)));
        before = v.next_before;
      } while (
        before !== null &&
        (!rows.some(t => t.status === "completed" && (!company || sides.some(s => t.input[s].company_id === company))) || !rows.some(
          (t) =>
            (!company ||
              sides.some((s) => t.input[s].company_id === company)) &&
            !["completed", "failed", "refused"].includes(t.status),
        ))
      );
      if (!c.signal.aborted) {
        setTasks(rows);
        setError("");
        setLoading(false);
      }
    })().catch((e) => {
      if (!c.signal.aborted) {
        setError(e.message);
        setLoading(false);
      }
    });
    return () => c.abort();
  }, [retry, company]);
  const research = (mode: string) =>
    `/research?${new URLSearchParams({ company, mode, ...(mode === "operating" ? { new: "1" } : {}) })}`;
  const rows = tasks.filter(
    (t) =>
      !company ||
      ["first", "second"].some(
        (s) => t.input[s as "first"].company_id === company,
      ),
  );
  const title = (t: Task) => {
    const name = (id: string) =>
      companies.find((c) => c.company_id === id)?.name || "企业研究";
    return t.input.template === "company_period_change"
      ? `${name(t.input.first.company_id)} · ${t.input.first.period.year} / ${t.input.second.period.year}`
      : `${name(t.input.first.company_id)} × ${name(t.input.second.company_id)} · ${t.input.first.period.year} 年`;
  };
  const unfinished = rows.filter(
    (t) => !["completed", "failed", "refused"].includes(t.status),
  );
  const current = unfinished[0];
  const completed = rows.filter(t => t.status === "completed");
  const featured = completed[0];
  const [progress, setProgress] = useState<{
    task: string;
    text: string;
  } | null>(null);
  useEffect(() => {
    const c = new AbortController();
    if (current?.waiting_checkpoint)
      void (async () => {
        await Promise.all(
          current.input.reports.map((r) => {
            const id = sides.find((side) =>
              current.input[side].choices.some(
                (choice) => choice.document_id === r.document_id,
              ),
            )!;
            return json<Source>(
              `/documents/${encodeURIComponent(r.document_id)}/source?${new URLSearchParams({ company_id: current.input[id].company_id, source_revision: r.expected_source_revision })}`,
              c.signal,
            ).then((raw) =>
              validateSource(
                raw,
                current.input[id].company_id,
                r.document_id,
                r.expected_source_revision,
              ),
            );
          }),
        );
        const facts = (
          await Promise.all(
            [
              ...new Set(sides.map((side) => current.input[side].company_id)),
            ].map((id) => access.query(id, c.signal)),
          )
        ).flatMap((q) => q.facts);
        const count = sides
          .flatMap((side) =>
            current.active_input[side].choices.map(
              (choice) =>
                slotFacts(
                  current.active_input,
                  side,
                  choice,
                  facts,
                  access.eligible,
                ).length === 1,
            ),
          )
          .filter(Boolean).length;
        if (!c.signal.aborted)
          setProgress({
            task: current.task_id,
            text:
              count === 6
                ? "六项事实已入库且当前有效。进入任务复核后，明确继续研究。"
                : `已入库 ${count} / 6 项。还需完成 ${6 - count} 项财务核对与独立入库。`,
          });
      })().catch(() => {
        if (!c.signal.aborted)
          setProgress({
            task: current!.task_id,
            text: "当前来源或事实资格需重新核验。进入任务查看具体缺项。",
          });
      });
    return () => c.abort();
  }, [current, access]);
  return (
    <div className={styles.home}>
      <div className="home-heading"><div><p className="eyebrow">FINDOC ANALYST</p><h1>从企业年报到可信研究</h1><p>上传企业年报，获得可信财务变化、可追溯原文证据和版本研究报告。</p></div></div>
      <header className={styles.hero} aria-label="当前研究">
        <p className="eyebrow">FinDoc Analyst · 企业经营研究</p>
        {loading ? (
          <>
            <h2>正在读取你的研究</h2>
            <p role="status">读取当前任务与下一步…</p>
          </>
        ) : error ? (
          <>
            <h2>研究记录暂不可用</h2>
            <p role="alert">{error}</p>
            <button onClick={() => { setLoading(true); setRetry((n) => n + 1); }}>
              重新读取研究记录
            </button>
          </>
        ) : !companies.length ? (
          <>
            <h2>先建立要研究的企业</h2>
            <p>绑定企业与年报后，核对财务事实，再比较两期或两家企业。</p>
            <a className={styles.primary} href="#home-company-setup" onClick={() => requestAnimationFrame(() => document.querySelector<HTMLInputElement>('#home-company-setup input')?.focus())}>建立企业 →</a>
          </>
        ) : featured ? (
          <>
            <p className="eyebrow">已完成的历史研究</p><h2>{title(featured)}</h2>
            <p>阅读三项财务变化、原文证据与报告入口。模型解释仍需语义审阅。</p>
            <p className={styles.historyNotice}>历史结果读取 · 不会重新运行模型</p>
            <a className={styles.primary} href={taskPath(featured)}>阅读历史研究 →</a>
          </>
        ) : current ? (
          <>
            <p className="eyebrow">当前待办</p><h2>{title(current)}</h2>
            <p>
              <strong>{taskLabels[current.status]}</strong>
            </p>
            <p>
              {progress?.task === current.task_id
                ? progress.text
                : current.waiting_checkpoint
                  ? "六项财务事实等待核验。进入任务查看缺项，核对与入库后明确继续。"
                  : nextAction(current)}
            </p>
            <a className={styles.primary} href={taskPath(current)}>
              继续当前研究 →
            </a>
          </>
        ) : (
          <>
            <h2>开始企业经营研究</h2>
            <p>
              比较两期经营变化，或对照两家企业。准备财报后，逐项核对原文，再开展研究。
            </p>
            <a className={styles.primary} href={research("operating")}>
              选择企业与研究范围 →
            </a>
          </>
        )}
      </header>
      {!companies.length && <CompanySetup id="home-company-setup" expanded />}
      <section className={unfinished.length ? styles.card : styles.emptyTasks} aria-label="继续尚未完成的研究">
        <div className={styles.row}>
          <h2>{loading ? "正在读取研究待办" : error ? "研究待办暂不可用" : current ? "未完成研究" : "暂无研究待办"}{current ? ` · 本页 ${unfinished.length} 项` : ""}</h2>
          <button onClick={() => { setLoading(true); setRetry((n) => n + 1); }}>刷新记录</button>
        </div>
        {unfinished.map((t) => (
          <a className={styles.historyRow} key={t.task_id} href={taskPath(t)}>
            <div>
              <strong>{title(t)}</strong>
              <p>
                {taskLabels[t.status]} · {nextAction(t)}
              </p>
            </div>
            <span>继续研究 →</span>
          </a>
        ))}

      </section>
      <nav className={styles.entryGrid} aria-label="其他研究功能">
        {companies.length > 0 && <a href={research("operating")}><strong>新建企业经营研究 →</strong><p>选择企业、期间与财报</p></a>}
        <a href={research("qa")}>
          <strong>原文问答 →</strong>
          <p>从所选财报查找答案</p>
        </a>
        <a href={`/reports?${new URLSearchParams({ company })}`}>
          <strong>研究报告 →</strong>
          <p>阅读草稿与已保存版本</p>
        </a>
      </nav>
      <section className={styles.card} aria-label="最近完成的研究">
        <h2>历史研究 · 已完成结果</h2><p>历史结果读取，不会重新运行模型；进入后只读复验来源资格。</p>
        {rows
          .filter((t) => t.status === "completed")
          .map((t) => (
            <a className={styles.historyRow} key={t.task_id} href={taskPath(t)}>
              <strong>{title(t)}</strong>
              <span>读取历史结果与报告入口 →</span>
            </a>
          ))}
        {!loading && !error && !rows.some((t) => t.status === "completed") && (
          <p>完成研究后，结果会保留在这里。</p>
        )}
      </section>
      {rows.some((t) => ["failed", "refused"].includes(t.status)) && (
        <details className={styles.card}>
          <summary>未取得结果的研究</summary>
          {rows
            .filter((t) => ["failed", "refused"].includes(t.status))
            .map((t) => (
              <a
                className={styles.historyRow}
                key={t.task_id}
                href={taskPath(t)}
              >
                {title(t)} · {taskLabels[t.status]} →
              </a>
            ))}
        </details>
      )}
      <HomeQAHistory company={company} />
      {companies.length > 0 && <CompanySetup />}
    </div>
  );
}

function HomeQAHistory({ company }: { company: string }) {
  const [rows, setRows] = useState<HistoryItem[]>([]), [error, setError] = useState('');
  useEffect(() => {
    const c = new AbortController();
    const q = new URLSearchParams({ limit: '5', ...(company ? { company_id: company } : {}) });
    void json<HistoryPage>(`/research/runs?${q}`, c.signal).then(validateHistory).then(v => {
      if (!c.signal.aborted) setRows(v.items);
    }).catch(() => { if (!c.signal.aborted) setError('问答记录暂不可用，可进入原文问答只读刷新。'); });
    return () => c.abort();
  }, [company]);
  return <section className={styles.card} aria-label="最近原文问答"><h2>最近原文问答</h2><p>历史问答读取 · 不会重新运行模型。范围取自各次所选财报。</p>
    {error && <p>{error}</p>}
    {rows.map(r => <a className={styles.historyRow} key={r.run_id} href={`/research?${new URLSearchParams({ mode: 'qa', run: r.run_id })}`}>
      <strong>{r.query}</strong><span>原文问答 · {r.status === 'answered' ? '已保存回答' : r.status === 'refused' ? '已保存拒答' : r.status === 'running' ? '执行中' : '已保存失败'} →</span></a>)}
    {!rows.length && !error && <p>暂无已保存问答，直接选择财报即可提问。</p>}
    <a href={`/research?${new URLSearchParams({ mode: 'qa', ...(company ? { company } : {}) })}`}>进入原文问答 →</a>
  </section>;
}
