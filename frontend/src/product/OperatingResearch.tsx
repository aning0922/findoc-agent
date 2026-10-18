import { focusResearchTarget } from './researchChapters.ts';
import { ResearchTaskHeader } from "./ResearchTaskHeader.tsx";
import { WaitingNotice } from "./WaitingNotice.tsx";
import type { Readiness } from "./ResearchTaskHeader.tsx";
import {
  saveReadingPosition,
  restoreReadingPosition,
} from "./researchReading.ts";
import { ResearchCreation } from "./ResearchCreation.tsx";
import type { Config } from "./ResearchCreation.tsx";
import { draftIdentity, readDraft, writeDraft, emptyConfig, changeDraftScope, changeDraftTemplate } from "./researchDraft.ts";
import { taskPath } from "./researchJourney.ts";
import styles from "./ResearchJourney.module.css";
import { readProductRoute } from './productRoutes.ts';
import { useCallback, useEffect, useRef, useState } from "react";
import type { Company, DataAccess, Fact, Report } from "./api.ts";
import { json, productionAccess } from "./api.ts";
import { TaskPanel } from "./OperatingTaskPanel.tsx";
import {
  acceptRevision,
  metrics,
  sides,
  readDisclosure,
  resumeFacts,
  taskLabels,
  taskRequest,
  validateInput,
  validateTask,
  queryFacts,
  TaskError,
} from "./operatingResearch.ts";
import type {
  Disclosure,
  Side,
  Task,
  Template,
  TemplateInput,
} from "./operatingResearch.ts";
import "./operatingResearch.css";
type Identity = {
  operation_id: string;
  task_id?: string;
  revision?: number;
  unknown: boolean;
};
function storageKey(company: string) {
  return `findoc:operating-identity:${company}`;
}
function savedIdentity(company: string): Identity | null {
  try {
    const v = JSON.parse(localStorage.getItem(storageKey(company)) || "null");
    return v && /^[a-f0-9-]{36}$/.test(v.operation_id) ? v : null;
  } catch {
    return null;
  }
}
function remember(company: string, v: Identity | null) {
  try {
    if (v) localStorage.setItem(storageKey(company), JSON.stringify(v));
    else localStorage.removeItem(storageKey(company));
  } catch {
    /* GET history remains authoritative */
  }
}
export function OperatingResearch(props: { company: string; companies: Company[]; access?: DataAccess; chooseCompany: (id: string) => void }) {
  return <Session key={props.company} company={props.company} companies={props.companies} access={props.access || productionAccess} />;
}
function Session({
  company,
  companies,
  access,
}: {
  company: string;
  companies: Company[];
  access: DataAccess;
}) {
  const [draftId] = useState(draftIdentity);
  const [draft] = useState(() => readDraft(draftId));
  const [stage, setStage] = useState(draft?.stage || 1);
  const [scopeNotice, setScopeNotice] = useState<string[]>(draft?.notice || []);
  const section = readProductRoute(new URL(location.href)).section;
  const [template, setTemplate] = useState<Template>(
    draft?.template || "company_period_change",
  );
  const [catalogRevision, setCatalogRevision] = useState(0);
  const [showConfig, setShowConfig] = useState(false);
  const [readiness, setReadiness] = useState<Readiness | null>(null);
  const readingTask = useRef("");
  const readReady = useCallback((value: Readiness) => {
    setReadiness((old) =>
      JSON.stringify(old) === JSON.stringify(value) ? old : value,
    );
    if (value.checked && readingTask.current !== value.taskId) {
      readingTask.current = value.taskId;
      restoreReadingPosition(value.taskId);
    }
  }, []);
  const refreshCatalog = useCallback(() => {
    setPrepared({ first: null, second: null });
    setCatalogBusy(true);
    setCatalogError("");
    setCatalogRevision((n) => n + 1);
  }, []);
  const [direction, setDirection] =
    useState<TemplateInput["direction"]>("business_overview");
  const [config, setConfig] = useState<Record<Side, Config>>({
    first: draft?.config.first || emptyConfig(company),
    second: draft?.config.second || emptyConfig(company),
  });
  const [reports, setReports] = useState<
    (Report & { selectable: boolean; reason: string | null })[]
  >([]);
  const [catalogError, setCatalogError] = useState("");
  const [catalogBusy, setCatalogBusy] = useState(true);
  const [prepared, setPrepared] = useState<
    Record<Side, { key: string; disclosure: Disclosure; facts: Fact[] } | null>
  >({ first: null, second: null });
  const [prepareError, setPrepareError] = useState<Record<Side, string>>({
    first: "",
    second: "",
  });
  const [task, setTask] = useState<Task | null>(null);
  const [taskReadUnavailable, setTaskReadUnavailable] = useState(false);
  useEffect(() => {
    const focus = () => requestAnimationFrame(() => focusResearchTarget());
    focus();
    window.addEventListener('hashchange', focus);
    return () => window.removeEventListener('hashchange', focus);
  }, [task?.task_id, section]);
  const [initialSelection, setInitialSelection] = useState<{
    taskId: string;
    selected: Record<string, string>;
  } | null>(null);
  const currentTask = useRef<Task | null>(null);
  useEffect(() => {
    const scroll = () => {
      if (
        currentTask.current &&
        readingTask.current === currentTask.current.task_id
      )
        saveReadingPosition(currentTask.current.task_id);
    };
    window.addEventListener("scroll", scroll, { passive: true });
    return () => {
      scroll();
      window.removeEventListener("scroll", scroll);
    };
  }, []);
  const [identity, setIdentity] = useState<Identity | null>(() =>
    savedIdentity(company),
  );
  const [busy, setBusy] = useState(false);
  const [waitingFor, setWaitingFor] = useState<"read" | "create" | "resume">("read");
  const [waitingIdentity, setWaitingIdentity] = useState(0);
  const [message, setMessage] = useState("");
  const [missing, setMissing] = useState(false);
  const [history, setHistory] = useState<Task[]>([]);
  const [before, setBefore] = useState<number | null>(null);
  const [historyError, setHistoryError] = useState("");
  const [listBusy, setListBusy] = useState(false);
  const active = useRef<AbortController | null>(null),
    listing = useRef<AbortController | null>(null),
    epoch = useRef(0);
  const updateIdentity = (v: Identity | null) => {
    remember(company, v);
    setIdentity(v);
  };
  function revoke() {
    epoch.current++;
    active.current?.abort();
    active.current = null;
    currentTask.current = null;
    setTask(null);
    setBusy(false);
    setMessage("");
    setMissing(false);
  }
  useEffect(
    () => () => {
      epoch.current++;
      active.current?.abort();
      active.current = null;
      listing.current?.abort();
      listing.current = null;
    },
    [],
  );
  useEffect(() => {
    const c = new AbortController();
    json<{ schema_version: string; documents: typeof reports }>(
      "/research/sources",
      c.signal,
    )
      .then((v) => {
        if (
          v.schema_version !== "research-source-options-v1" ||
          !Array.isArray(v.documents)
        )
          throw new Error("资料合同不完整");
        if (!c.signal.aborted) {
          setReports(v.documents.filter((d) => d.report_type === "annual"));
          setCatalogBusy(false);
        }
      })
      .catch((e) => {
        if (!c.signal.aborted) {
          setCatalogError(e.message);
          setCatalogBusy(false);
        }
      });
    return () => c.abort();
  }, [catalogRevision]);
  const loadHistory = useCallback(
    async (next: number | null = null) => {
      listing.current?.abort();
      const c = new AbortController();
      listing.current = c;
      setListBusy(true);
      setHistoryError("");
      try {
        const v = await json<{
          schema_version: string;
          items: Task[];
          next_before: number | null;
        }>(`/research/tasks?limit=5${next ? `&before=${next}` : ""}`, c.signal);
        if (
          v.schema_version !== "template-task-history-v1" ||
          !Array.isArray(v.items) ||
          (v.next_before !== null &&
            (!Number.isSafeInteger(v.next_before) ||
              v.next_before < 1 ||
              (next !== null && v.next_before >= next)))
        )
          throw new Error("历史分页合同无效");
        const rows = v.items
          .map((t) => validateTask(t))
          .filter(
            (t) =>
              !company || sides.some((s) => t.input[s].company_id === company),
          );
        if (c.signal.aborted) return;
        setHistory((old) =>
          next
            ? [
                ...old,
                ...rows.filter(
                  (t) => !old.some((o) => o.task_id === t.task_id),
                ),
              ]
            : rows,
        );
        setBefore(v.next_before);
      } catch (e) {
        if (!c.signal.aborted) setHistoryError((e as Error).message);
      } finally {
        if (!c.signal.aborted) setListBusy(false);
      }
    },
    [company],
  );
  useEffect(() => {
    void loadHistory();
    return () => listing.current?.abort();
  }, [loadHistory]);
  useEffect(() => {
    if (!new URLSearchParams(location.search).has('task')) writeDraft({ id: draftId, template, config, stage, notice: scopeNotice });
  }, [draftId, template, config, stage, scopeNotice]);
  const configKey = JSON.stringify(
    sides.map((s) => [config[s].company, config[s].year, config[s].document]),
  );
  useEffect(() => {
    const c = new AbortController();
    const results: typeof prepared = { first: null, second: null },
      errors = { first: "", second: "" };
    void Promise.allSettled(
      sides.map(async (side) => {
        const chosen = config[side],
          report = reports.find(
            (r) =>
              r.document_id === chosen.document &&
              r.company_id === chosen.company,
          );
        if (!report) return;
        try {
          const [disclosure, q] = await Promise.all([
            readDisclosure(report, c.signal),
            access === productionAccess
              ? queryFacts(chosen.company, c.signal)
              : access.query(chosen.company, c.signal),
          ]);
          results[side] = {
            key: `${chosen.company}:${chosen.document}`,
            disclosure,
            facts: q.facts,
          };
        } catch (e) {
          errors[side] = (e as Error).message;
        }
      }),
    ).then(() => {
      if (!c.signal.aborted) {
        setPrepared(results);
        setPrepareError(errors);
      }
    });
    return () => c.abort();
    // The key owns source requests; all config changes revoke task display synchronously.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [configKey, reports, access]);
  function change(side: Side, update: Partial<Config>) {
    revoke();
    setConfig(old => changeDraftScope(old, template, side, update));
  }
  function publish(v: Task) {
    if (!acceptRevision(currentTask.current, v)) return;
    const completedNow =
      currentTask.current &&
      currentTask.current.status !== "completed" &&
      v.status === "completed";
    currentTask.current = v;
    setTask(v);
    setTaskReadUnavailable(false);
    window.dispatchEvent(new Event('findoc:fixed-context'));
    if (completedNow) {
      readingTask.current = "";
      try {
        sessionStorage.removeItem(`findoc:task-reading:${v.task_id}`);
      } catch {
        /* optional */
      }
    }
    setShowConfig(false);
    if (location.pathname === "/research")
      window.history.replaceState(
        null,
        "",
        taskPath(v) + (new URLSearchParams(location.search).has('section') ? `&section=${section}` : '') +
          (new URLSearchParams(location.search).get("task") === v.task_id &&
          !completedNow
            ? location.hash
            : ""),
      );
  }
  async function open(id: string, byOperation = false, keep = false) {
    setWaitingFor("read");
    setWaitingIdentity(value => value + 1);
    if (active.current) return;
    if (!keep) revoke();
    const own = epoch.current,
      c = new AbortController();
    active.current = c;
    setBusy(true);
    setMessage("");
    try {
      const v = await taskRequest(
        `/${byOperation ? "by-operation/" : ""}${encodeURIComponent(id)}`,
        c.signal,
      );
      if (c.signal.aborted || own !== epoch.current) return;
      if (!byOperation && v.task_id !== id) throw new Error("任务身份不一致");
      const known = savedIdentity(company);
      if (
        byOperation &&
        known?.task_id &&
        known.operation_id === id &&
        known.task_id !== v.task_id
      )
        throw new TaskError("operation_request_conflict", 409);
      if (
        known?.task_id === v.task_id &&
        known.revision &&
        v.revision < known.revision
      )
        throw new TaskError("late_task_response", 409);
      if (
        keep &&
        currentTask.current &&
        !acceptRevision(currentTask.current, v)
      )
        return;
      publish(v);
      if (
        !known?.unknown ||
        byOperation ||
        known.operation_id === v.operation_id
      )
        updateIdentity({
          operation_id: byOperation
            ? id
            : known?.task_id === v.task_id
              ? known.operation_id
              : v.operation_id,
          task_id: v.task_id,
          revision: v.revision,
          unknown: v.execution_status === "running",
        });
    } catch (e) {
      if (!c.signal.aborted && own === epoch.current) {
        if (keep && currentTask.current) setTaskReadUnavailable(true);
        else {
          currentTask.current = null;
          setTask(null);
        }
        setMessage(
          e instanceof TaskError
            ? e.message
            : "网络响应未知或任务读取失败，请只读查询。",
        );
        if (e instanceof TaskError && e.status === 404) setMissing(true);
      }
    } finally {
      if (!c.signal.aborted && own === epoch.current) {
        setBusy(false);
        active.current = null;
      }
    }
  }
  // The keyed company owns restoration; the latest callback is read once per mount.
  const restore = useRef(open);
  restore.current = open;
  useEffect(() => {
    const v = savedIdentity(company);
    const query = new URLSearchParams(location.search),
      id = query.get("task");
    if (id) {
      void restore.current(id);
      return;
    }
    if (v && (v.unknown || (query.get("new") !== "1" && !query.has("draft"))))
      void restore.current(
        v.unknown || !v.task_id ? v.operation_id : v.task_id,
        v.unknown || !v.task_id,
      );
  }, [company]); // identity only; server GET restores content
  function buildInput(): TemplateInput {
    const researchSides = {} as Pick<TemplateInput, Side>;
    for (const side of sides) {
      const s = config[side],
        p = prepared[side];
      if (!p || p.key !== `${s.company}:${s.document}` || !s.year)
        throw new Error("请明确选择企业、期间和可用年报");
      const year = Number(s.year),
        prefix = String(year).padStart(4, "0");
      researchSides[side] = {
        company_id: s.company,
        period: {
          year,
          start: `${prefix}-01-01`,
          end: `${prefix}-12-31`,
          period_type: "annual",
        },
        choices: metrics.map((metric) => {
          const version = s.versions[metric];
          if (!p.disclosure.disclosure_versions.includes(version))
            throw new Error("请逐项明确选择可信披露版本");
          const f = p.facts.find(
            (f) =>
              f.fact_id === s.facts[metric] &&
              access.eligible(f) &&
              f.document_id === s.document &&
              f.period === year &&
              f.metric_key === metric &&
              f.disclosure_version === version &&
              f.source_revision === p.disclosure.source.source_revision,
          );
          return {
            metric_key: metric,
            document_id: s.document,
            disclosure_version: version,
            fact_set_id: f?.fact_set_id || null,
            fact_id: f?.fact_id || null,
          };
        }),
      };
    }
    const documents = [...new Set(sides.map((s) => config[s].document))];
    return validateInput({
      schema_version: "operating-research-input-v1",
      template,
      direction,
      ...researchSides,
      reports: documents.map((document_id) => ({
        document_id,
        expected_source_revision: sides
          .map((s) => prepared[s])
          .find((p) => p?.disclosure.source.document_id === document_id)!
          .disclosure.source.source_revision,
      })),
    });
  }
  let input: TemplateInput | null = null;
  try {
    input = buildInput();
  } catch {
    /* incomplete configuration is visible */
  }
  async function start(parentTaskId?: string) {
    if (active.current || !input || identity?.unknown) return;
    setWaitingFor("create");
    setWaitingIdentity(value => value + 1);
    const frozenInput = structuredClone(input);
    const chosenFacts = Object.fromEntries(
      sides.flatMap((side) =>
        input![side].choices
          .filter((choice) => choice.fact_id)
          .map((choice) => [`${side}:${choice.metric_key}`, choice.fact_id!]),
      ),
    );
    // Creation checks sources and waits. Only the later explicit resume supplies the six qualified IDs.
    for (const side of sides)
      for (const choice of frozenInput[side].choices) {
        choice.fact_id = null;
        choice.fact_set_id = null;
      }
    revoke();
    const own = epoch.current,
      c = new AbortController();
    active.current = c;
    setBusy(true);
    const op = crypto.randomUUID();
    updateIdentity({ operation_id: op, unknown: true });
    try {
      const v = await taskRequest("", c.signal, {
        operation_id: op,
        input: frozenInput,
        run_version: "d21-operating-graph-v2",
        ...(parentTaskId ? { parent_task_id: parentTaskId } : {}),
      });
      if (c.signal.aborted || own !== epoch.current) return;
      if (
        v.operation_id !== op ||
        JSON.stringify(v.input) !== JSON.stringify(frozenInput)
      ) {
        // Server canonical ordering can differ. Compare canonical JSON below.
        if (
          v.operation_id !== op ||
          canonical(v.input) !== canonical(frozenInput)
        )
          throw new Error("创建任务请求身份不一致");
      }
      setInitialSelection({ taskId: v.task_id, selected: chosenFacts });
      publish(v);
      updateIdentity({
        operation_id: op,
        task_id: v.task_id,
        revision: v.revision,
        unknown: v.execution_status === "running",
      });
      void loadHistory();
    } catch (e) {
      if (!c.signal.aborted && own === epoch.current)
        setMessage(
          e instanceof TaskError
            ? e.message
            : "网络响应未知。请查询最新执行结果（只读）；没有再次提交。",
        );
    } finally {
      if (!c.signal.aborted && own === epoch.current) {
        active.current = null;
        setBusy(false);
      }
    }
  }
  async function resume(selected: Record<string, string>) {
    if (active.current || !task || identity?.unknown) return;
    setWaitingFor("resume");
    setWaitingIdentity(value => value + 1);
    const viewed = task,
      own = epoch.current,
      c = new AbortController();
    active.current = c;
    setBusy(true);
    setMessage("");
    try {
      const fresh = await taskRequest(`/${viewed.task_id}`, c.signal);
      validateTask(fresh, viewed.task_id);
      if (c.signal.aborted || own !== epoch.current) return;
      if (!acceptRevision(viewed, fresh))
        throw new Error("旧响应已拒绝，等待刷新当前任务");
      publish(fresh);
      if (
        fresh.revision !== viewed.revision ||
        !fresh.waiting_checkpoint ||
        fresh.execution_status !== "idle"
      )
        throw new Error(
          "任务版本或等待状态已变化。已读回最新 revision，请核对后再恢复。",
        );
      const facts = (
        await Promise.all(
          [...new Set(sides.map((s) => fresh.input[s].company_id))].map((id) =>
            access.query(id, c.signal),
          ),
        )
      ).flatMap((q) => q.facts);
      const refs = resumeFacts(
        fresh.active_input,
        facts,
        selected,
        access.eligible,
      );
      if (c.signal.aborted || own !== epoch.current) return;
      const op = crypto.randomUUID();
      updateIdentity({
        operation_id: op,
        task_id: fresh.task_id,
        revision: fresh.revision,
        unknown: true,
      });
      const v = await taskRequest(`/${fresh.task_id}/resume`, c.signal, {
        operation_id: op,
        expected_revision: fresh.revision,
        facts: refs,
      });
      if (c.signal.aborted || own !== epoch.current) return;
      validateTask(v, fresh.task_id);
      publish(v);
      updateIdentity({
        operation_id: op,
        task_id: v.task_id,
        revision: v.revision,
        unknown: v.execution_status === "running",
      });
      void loadHistory();
    } catch (e) {
      if (!c.signal.aborted && own === epoch.current) {
        setMessage(
          e instanceof TaskError
            ? e.message
            : savedIdentity(company)?.unknown
              ? "网络响应未知，恢复可能已执行。请查询最新执行结果（只读）；没有重复提交。"
              : (e as Error).message || "恢复结果未知，请只读查询。",
        );
        currentTask.current = null;
        setTask(null);
      }
    } finally {
      if (!c.signal.aborted && own === epoch.current) {
        active.current = null;
        setBusy(false);
      }
    }
  }
  return (
    <div className={`operating-workbench ${styles.journey}`}>
      {busy && <WaitingNotice key={waitingIdentity} title={waitingFor === 'resume' ? '正在执行经营研究' : waitingFor === 'create' ? '正在建立研究任务' : '正在只读查证研究状态'} message={waitingFor === "resume"
        ? "正在等待经营研究结果，服务端将复验已接受事实、执行财务分析并收集经营解释。"
        : waitingFor === "create" ? "正在核验所选年报并建立研究任务，财务接受与入库需要之后独立完成。"
        : "正在只读查询已保存的任务与执行状态。"} stop={() => {
          revoke(); setMessage("已停止本页等待，已提交的服务端任务可能仍在执行。原操作身份与任务编号已保留，请查询最新执行结果（只读）。");
        }} />}
      {task && (
        <ResearchTaskHeader
          task={task}
          section={section}
          companies={companies}
          unknown={!busy && (!!identity?.unknown || task.execution_outcome === 'interrupted/unknown')}
          executing={busy && waitingFor === 'resume'}
          busy={busy}
          readiness={readiness}
          taskReadState={busy && waitingFor === 'read' ? 'checking' : taskReadUnavailable ? 'unavailable' : null}
          refresh={() => {
            if (task) void open(task.task_id, false, true);
          }}
          resume={() => {
            if (readiness) void resume(readiness.selected);
          }}
          newTask={() => {
            revoke();
            setShowConfig(true);
            window.history.replaceState(
              null,
              "",
              `/research?${new URLSearchParams({ company, mode: "operating", new: "1" })}`,
            );
          }}
        />
      )}
      <div className="operating-grid">
        <div className="operating-main">
          {(!task || showConfig) && !identity?.unknown && (
            <ResearchCreation
              stage={stage}
              setStage={setStage}
              companies={companies}
              scopeNotice={scopeNotice}
              setScopeNotice={setScopeNotice}
              template={template}
              config={config}
              prepared={prepared}
              reports={reports}
              access={access}
              errors={prepareError}
              catalogBusy={catalogBusy}
              catalogError={catalogError}
              busy={busy || !!identity?.unknown}
              ready={!!input}
              change={change}
              recheck={refreshCatalog}
              selectTemplate={(value) => {
                revoke();
                setTemplate(value);
                setConfig(old => changeDraftTemplate(old, value));
              }}
              direction={direction}
              setDirection={(value) => {
                revoke();
                setDirection(value);
              }}
              create={() => void start()}
            />
          )}
          {message && (
            <p className="operating-alert" role="alert">
              {message}
            </p>
          )}
          {!busy && identity && (!task || identity.unknown || task.execution_outcome === 'interrupted/unknown') && (
            <details
              id="research-recovery"
              tabIndex={-1}
              className="operating-card"
              open={identity.unknown || task?.execution_outcome === 'interrupted/unknown'}
            >
              <summary>
                {identity.unknown || task?.execution_outcome === 'interrupted/unknown'
                  ? "网络响应未知 · 请查证刚才的结果"
                  : "执行详情与只读查询"}
              </summary>
              <p>
                浏览器关闭不代表服务器任务取消。只读查询不会再次执行模型或消费预算。
              </p>
              <details>
                <summary>操作身份</summary>
                <code>{identity.operation_id}</code>
              </details>
              <div className="operating-actions">
                <button
                  disabled={busy}
                  onClick={() => void open(identity.operation_id, true)}
                >
                  查证刚才的结果（只读）
                </button>
                {missing && (
                  <button
                    onClick={() => {
                      updateIdentity(null);
                      setMissing(false);
                      setMessage("已结束身份查询。可以明确创建新任务。");
                    }}
                  >
                    结束查询，允许显式新建
                  </button>
                )}
              </div>
            </details>
          )}
          {(task?.schema_version === "persistent-template-task-v1" ||
            task?.snapshot?.schema_version ===
              "operating-research-plan-v1") && (
            <section className="operating-card">
              <p>
                旧计划继续保留原预算与检查点。当前选择可显式创建关联的 D21
                新研究。
              </p>
              <button
                disabled={busy || !input || !!identity?.unknown}
                onClick={() => void start(task.task_id)}
              >
                按当前选择创建 D21 新研究
              </button>
            </section>
          )}
          {task ? (
            <TaskPanel
              key={task.task_id}
              task={task}
              section={section}
              taskReadState={busy && waitingFor === 'read' ? 'checking' : taskReadUnavailable ? 'unavailable' : null}
              companies={companies}
              access={access}
              busy={busy || !!identity?.unknown}
              resume={resume}
              readiness={readReady}
              initialSelection={
                initialSelection?.taskId === task.task_id
                  ? initialSelection.selected
                  : undefined
              }
            />
          ) : null}
        </div>
        <details className="operating-card">
          <summary>研究记录</summary>
          <aside
            className="operating-history"
            id="research-history"
            tabIndex={-1}
            aria-label="经营研究历史"
          >
            <div className="operating-heading">
              <h2>研究记录</h2>
              <button disabled={listBusy} onClick={() => void loadHistory()}>
                刷新
              </button>
            </div>
            <p className="muted">
              {company ? "当前企业参与的任务" : "请选择企业，或查看空间任务"} ·
              按创建时间展示
            </p>
            {historyError && <p role="alert">{historyError}</p>}
            {!history.length && <p>本页暂无该企业任务。可继续读取下一页。</p>}
            {history.map((t) => (
              <a
                href={taskPath(t)}
                key={t.task_id}
                className={`operating-history-item ${task?.task_id === t.task_id ? "active" : ""}`}
              >
                <strong>
                  {t.input.template === "company_period_change"
                    ? "两期间变化"
                    : "两企业比较"}
                </strong>
                <span>
                  {
                    companies.find(
                      (c) => c.company_id === t.input.first.company_id,
                    )?.name
                  }{" "}
                  · {t.input.first.period.year}
                  {t.input.template === "company_period_change"
                    ? ` / ${t.input.second.period.year}`
                    : ` · ${companies.find((c) => c.company_id === t.input.second.company_id)?.name}`}
                </span>
                <small>
                  {t.execution_status === "running"
                    ? "执行中 / 结果待读回"
                    : taskLabels[t.status]}{" "}
                  · 服务端已读回
                </small>
                <time>{new Date(t.created_at).toLocaleString("zh-CN")}</time>
              </a>
            ))}
            {before && (
              <button
                disabled={listBusy}
                onClick={() => void loadHistory(before)}
              >
                读取下一页历史
              </button>
            )}
          </aside>
        </details>
      </div>
    </div>
  );
}
function canonical(v: unknown): string {
  if (Array.isArray(v)) return `[${v.map(canonical).join(",")}]`;
  if (v && typeof v === "object")
    return `{${Object.entries(v)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([k, x]) => `${JSON.stringify(k)}:${canonical(x)}`)
      .join(",")}}`;
  return JSON.stringify(v);
}
