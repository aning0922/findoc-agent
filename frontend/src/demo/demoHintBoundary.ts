import { AGENT_RUN_INDEX_KEY } from "../agentRunIndex.ts";

// These are browser recovery/draft hints, never identity or authority. Keep this
// allowlist tied to the owning writers; do not remove unrelated origin storage.
const sessionExact = new Set([
  "findoc:conversation-operations:v1", // product/conversationState.ts
  "findoc:memory-operation:v1", // product/memoryApi.ts
  "findoc-report-unknown-operation-v1", // product/reportOperation.ts
]);
const sessionPrefixes = [
  "findoc:research-draft-v2:", // product/researchDraft.ts
  "findoc:task-reading:", // product/researchReading.ts
  "findoc:upload-intent:", // product/DocumentLibrary.tsx
  "findoc:pending-operation:", // product/ResearchRuns.tsx
  "financial-acceptance-pending-v1:", // evidence/FinancialSession.tsx, incl history
  "financial-facts-pending-v1:", // evidence/FinancialSession.tsx
  "embedded-review-session-v1:", // evidence/EvidenceWorkbench.tsx
];
const localPrefixes = [
  "findoc:source-intent:", // product/sourceIntent.ts
  "findoc:operating-identity:", // product/OperatingResearch.tsx
];
function removeMatching(storage: Storage, matches: (key: string) => boolean) {
  const keys: string[] = [];
  for (let i = 0; i < storage.length; i++) {
    const key = storage.key(i);
    if (key !== null && matches(key)) keys.push(key);
  }
  for (const key of keys) storage.removeItem(key);
}

/** Only call after a server Session has passed validation and freshness checks.
 * Failure propagates: do not mount a new workspace with stale recoverable hints.
 * No client identity marker is written; the caller keeps a per-Gate memory ref.
 */
export function clearDemoBusinessHints() {
  removeMatching(
    window.sessionStorage,
    (key) =>
      sessionExact.has(key) ||
      sessionPrefixes.some((prefix) => key.startsWith(prefix)),
  );
  removeMatching(
    window.localStorage,
    (key) =>
      key === AGENT_RUN_INDEX_KEY ||
      localPrefixes.some((prefix) => key.startsWith(prefix)),
  );
}
