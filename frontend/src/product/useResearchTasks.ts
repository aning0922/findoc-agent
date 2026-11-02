import { useEffect, useState } from 'react';
import { json } from './api.ts';
import { validateTask, type Task } from './operatingResearch.ts';

/** Read history without creating, resuming, or recomputing a research task. */
export function useResearchTasks() {
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
      } while (before !== null);
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
  }, [retry]);
  return { tasks, error, loading, refresh: () => { setLoading(true); setTasks([]); setError(""); setRetry(n => n + 1); } };
}
