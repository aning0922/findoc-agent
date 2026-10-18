import { useEffect, useState } from "react";
import { json } from "./api.ts";
import { validateTask } from "./operatingResearch.ts";
import type { Task } from "./operatingResearch.ts";

// A user chooses a known research record. The destination rereads both that
// frozen task and current qualified facts; this list never selects a source.
export function ResearchIntentRecovery({ company }: { company: string }) {
  const [tasks, setTasks] = useState<Task[]>([]),
    [error, setError] = useState("");
  useEffect(() => {
    const c = new AbortController();
    void json<{ schema_version: string; items: Task[] }>(
      "/research/tasks?limit=50",
      c.signal,
    )
      .then((value) => {
        if (
          value.schema_version !== "template-task-history-v1" ||
          !Array.isArray(value.items)
        )
          throw new Error("研究记录暂无法读取。");
        const rows = value.items
          .map((t) => validateTask(t))
          .filter(
            (t) =>
              t.status === "completed" &&
              t.input.template === "company_period_change" &&
              t.input.first.company_id === company &&
              t.publication_eligibility?.status !== "invalidated",
          );
        if (!c.signal.aborted) setTasks(rows);
      })
      .catch((e) => {
        if (!c.signal.aborted) setError(e.message);
      });
    return () => c.abort();
  }, [company]);
  return (
    <details>
      <summary>更换研究来源</summary>
      <p>沿用已完成研究中明确选定的来源</p>
      <p>
        选择原研究记录后，重新核验冻结披露与当前事实。多个研究不会替你选择。
      </p>
      {error && <p role="alert">{error}</p>}
      {tasks.map((task) => (
        <p key={task.task_id}>
          <a
            href={`/companies/${encodeURIComponent(company)}/analysis?${new URLSearchParams({ task: task.task_id })}`}
          >
            {task.input.first.period.year} / {task.input.second.period.year}{" "}
            年研究 · {new Date(task.created_at).toLocaleString("zh-CN")} →
          </a>
        </p>
      ))}
      {!error && !tasks.length && (
        <p>暂无可沿用的已完成研究。请明确选择下方来源。</p>
      )}
    </details>
  );
}
