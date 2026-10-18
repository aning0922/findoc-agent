import { taskRequest, type Task } from "./operatingResearch.ts";
import { taskPath } from "./researchJourney.ts";
import { CompanySetup } from "./CompanySetup.tsx";
import { useEffect, useState } from "react";
import type { Company, DataAccess } from "./api.ts";
import { OperatingResearch } from "./OperatingResearch.tsx";
import { ResearchSourceSelection } from "./ResearchSourceSelection.tsx";
export function ResearchWorkbench({
  company,
  companies,
  access,
  chooseCompany,
}: {
  company: string;
  companies: Company[];
  access: DataAccess;
  chooseCompany: (id: string) => void;
}) {
  const [mode, setMode] = useState(() =>
    new URLSearchParams(location.search).get("mode") === "qa"
      ? "qa"
      : "operating",
  );
  const [returnTask, setReturnTask] = useState<Task | null>(null);
  const returnId = mode === 'qa' ? new URLSearchParams(location.search).get('return_task') : null;
  useEffect(() => {
    const c = new AbortController();
    if (returnId) void taskRequest(`/${encodeURIComponent(returnId)}`, c.signal).then(t => {
      if (!c.signal.aborted && t.task_id === returnId) setReturnTask(t);
    }).catch(() => {});
    return () => c.abort();
  }, [returnId]);
  function choose(value: string) {
    if (value === mode) return;
    setMode(value);
    const q = new URLSearchParams(location.search);
    q.set("mode", value);
    q.delete("task");
    q.delete("new");
    q.delete("run");
    q.delete("section");
    q.delete("return_task");
    window.location.assign(`/research?${q}`);
  }
  return (
    <div className={`research-workspace ${mode === "qa" ? "qa-workspace" : ""}`}>
      <div className="page-heading">
        {mode === "operating" && <p className="eyebrow">RESEARCH WORKSPACE</p>}
        <h1>{mode === "operating" ? "企业经营研究" : "原文问答"}</h1>
        {mode === "qa" && <p>直接选择财报提问，无需先创建经营研究。每次问答独立保存。</p>}
      </div>
      <div className="research-modes" role="tablist" aria-label="工作台模式">
        <button
          role="tab"
          aria-selected={mode === "qa"}
          onClick={() => choose("qa")}
        >
          原文问答
        </button>
        <button
          role="tab"
          aria-selected={mode === "operating"}
          onClick={() => choose("operating")}
        >
          经营研究
        </button>
      </div>
      <div role="tabpanel" aria-label={mode === "qa" ? "原文问答" : "经营研究"}>
        {mode === "operating" ? (
          <OperatingResearch
            company={company}
            companies={companies}
            access={access}
            chooseCompany={chooseCompany}
          />
        ) : (
          <>
            {returnId && <aside className="qa-return"><p>从经营研究进入的独立问答，所选资料需在此页明确选择。</p>{returnTask ? <a href={taskPath(returnTask)}>返回来源研究 →</a> : <p>正在只读核验返回的研究身份。</p>}</aside>}
            <ResearchSourceSelection company={company} companies={companies} />
            <details>
              <summary>兼容工具：原有单文档工作台</summary>
              <a href="/legacy">打开原有单文档 RAG / Agent / 上传工作台</a>
            </details>
          </>
        )}
      </div>
      <CompanySetup />
    </div>
  );
}
