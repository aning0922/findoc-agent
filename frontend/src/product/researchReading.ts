import { focusResearchTarget } from './researchChapters.ts';
// Browsing intent only. This stores no facts, source qualification or acceptances.
export function saveReadingPosition(taskId: string) {
  try { sessionStorage.setItem(`findoc:task-reading:${taskId}`, String(window.scrollY)); } catch { /* optional */ }
}
export function restoreReadingPosition(taskId: string) {
  requestAnimationFrame(() => {
    if (location.pathname !== "/research" || new URLSearchParams(location.search).get("task") !== taskId) return;
    if (focusResearchTarget()) return;
    try {
      const raw = sessionStorage.getItem(`findoc:task-reading:${taskId}`), y = Number(raw);
      if (raw !== null && Number.isFinite(y) && y >= 0 && y <= 100000) window.scrollTo({ top: y });
      else window.scrollTo({ top: 0 });
    } catch { /* browser default scroll restoration remains available */ }
  });
}
