import { useEffect, useRef, useState } from "react";
import "./showcaseResearch.css";
type Mode = "quick" | "synthesis" | "deep";
type Link = { intent_id: string; task_id: string | null; state: string };
type Links = { conversation_id: string; items: Link[] };
const uuid = /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i;
type Props = {
  conversationId: string;
  onModeChange?: (mode: Mode) => void;
  initialQuestion?: string;
  initialJobId?: string;
};
export function ShowcaseResearchPanel(props: Props) {
  return <ResearchContent key={props.conversationId} {...props} />;
}
function ResearchContent({
  conversationId,
  onModeChange,
  initialQuestion = "",
  initialJobId,
}: Props) {
  const [mode, setMode] = useState<Mode>("quick"),
    [question, setQuestion] = useState(initialQuestion),
    [links, setLinks] = useState<Link[]>([]),
    [state, setState] = useState(""),
    [reload, setReload] = useState(0),
    [loading, setLoading] = useState(true);
  const epoch = useRef(0);
  const modeCallback = useRef(onModeChange);
  useEffect(() => {
    modeCallback.current = onModeChange;
  }, [onModeChange]);
  useEffect(() => {
    modeCallback.current?.("quick");
  }, []);
  useEffect(() => {
    const n = ++epoch.current,
      c = new AbortController();
    setLinks([]);
    setState("");
    setLoading(true);
    if (!uuid.test(conversationId)) {
      setLoading(false);
      setState("请选择已保存的研究会话。");
      return () => c.abort();
    }
    void fetch(
      `/api/research/conversations/${encodeURIComponent(conversationId)}/links`,
      { signal: c.signal, cache: "no-store", credentials: "same-origin" },
    )
      .then(async (r) => {
        if (!r.ok) throw Error("研究记录暂不可用。");
        const x = (await r.json()) as Links;
        if (
          x.conversation_id !== conversationId ||
          !Array.isArray(x.items) ||
          !x.items.every(
            (v) =>
              uuid.test(v.intent_id) &&
              (!v.task_id || uuid.test(v.task_id)) &&
              typeof v.state === "string",
          )
        )
          throw Error("研究记录身份无法核验。");
        if (n === epoch.current) {
          setLinks(x.items);
          setLoading(false);
        }
      })
      .catch((e) => {
        if (n === epoch.current && !c.signal.aborted) {
          setState((e as Error).message);
          setLoading(false);
        }
      });
    return () => {
      epoch.current++;
      c.abort();
    };
  }, [conversationId, reload]);
  function select(next: Mode) {
    setMode(next);
    onModeChange?.(next);
  }
  return (
    <section className="showcase-research">
      <div className="sr-heading">
        <div>
          <span>研究工作区</span>
          <h2>从问题到研究</h2>
          <p>根据问题选择合适的研究方式，研究结果仍须核对来源。</p>
        </div>
      </div>
      <div className="sr-modes" role="group" aria-label="研究模式">
        {(
          [
            {
              key: "quick",
              title: "快速问答",
              description: "围绕已选资料直接提问",
            },
            {
              key: "synthesis",
              title: "综合研究",
              description: "梳理资料与待核实问题",
            },
            {
              key: "deep",
              title: "深度研究",
              description: "先确认计划，再展开研究",
            },
          ] as const
        ).map((x) => (
          <button
            type="button"
            className={mode === x.key ? "selected" : ""}
            key={x.key}
            aria-pressed={mode === x.key}
            onClick={() => select(x.key)}
          >
            <b>{x.title}</b>
            <small>{x.description}</small>
          </button>
        ))}
      </div>
      {mode === "quick" ? (
        <div className="sr-card">
          <h3>快速问答</h3>
          <p>请使用当前会话的问答输入框，选择资料并提出问题。</p>
        </div>
      ) : (
        <div className="sr-card">
          <h3>{mode === "synthesis" ? "综合研究" : "深度研究"}</h3>
          <p>先准备研究问题。意图解析、计划确认和执行需要服务端接口就绪。</p>
          <label>
            研究问题
            <textarea
              maxLength={2000}
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="例如：梳理企业近年的经营变化与风险"
            />
          </label>
          <button type="button" disabled>
            意图解析暂不可用
          </button>
          <p className="sr-note">
            当前不能发起研究；已保存的会话和任务仍可阅读。
          </p>
        </div>
      )}
      {initialJobId && (
        <p className="sr-note">当前任务链接待研究接口支持后读取。</p>
      )}
      <div className="sr-history">
        <div>
          <h3>关联研究任务</h3>
          <button type="button" onClick={() => setReload((x) => x + 1)}>
            只读刷新
          </button>
        </div>
        {state && <p role="status">{state}</p>}
        {loading ? (
          <p role="status">正在读取关联任务…</p>
        ) : links.length ? (
          links.map((x) => (
            <article key={x.intent_id}>
              <div>
                <b>
                  {x.state === "completed" ? "已关联任务" : "任务状态待核对"}
                </b>
                <small>需要财务核对时，请由真人在任务中明确操作。</small>
              </div>
              {x.task_id && (
                <a
                  href={`/research?${new URLSearchParams({ task: x.task_id, mode: "operating" })}`}
                >
                  查看研究 →
                </a>
              )}
            </article>
          ))
        ) : !state ? (
          <p>当前会话暂无可读取的关联任务。</p>
        ) : null}
      </div>
    </section>
  );
}
