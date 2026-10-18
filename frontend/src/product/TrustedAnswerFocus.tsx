import { useEffect, useState } from 'react';
import type { ResearchRun } from './researchHistory.ts';
import type { AnswerFocus, FocusProjection } from './answerFocus.ts';
import { validateAnswerFocus } from './answerFocus.ts';

export function useAnswerFocus(run: ResearchRun): { focus: AnswerFocus | null; verified: boolean; invalidated: boolean } {
  const [reading, setReading] = useState<{ owner: ResearchRun; projection: FocusProjection } | null>(null);
  const [failure, setFailure] = useState<{ owner: ResearchRun; invalidated: boolean } | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    const timer = window.setTimeout(() => controller.abort(), 15000);
    void (async () => {
      const response = await fetch(`/api/research/runs/${encodeURIComponent(run.run_id)}/focus`, { signal: controller.signal, cache: 'no-store' });
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        if (!controller.signal.aborted) setFailure({ owner: run, invalidated: response.status < 500
          && ['source_changed', 'selection_changed'].includes(body.detail) });
        throw new Error('焦点暂不可核验');
      }
      const value = await validateAnswerFocus(await response.json(), run);
      if (!controller.signal.aborted) setReading({ owner: run, projection: value });
    })().catch(() => { if (!controller.signal.aborted) setReading(null); })
      .finally(() => clearTimeout(timer));
    return () => { controller.abort(); clearTimeout(timer); };
  }, [run]);
  return { focus: reading?.owner === run ? reading.projection.focus : null,
    verified: reading?.owner === run, invalidated: failure?.owner === run && failure.invalidated };
}
