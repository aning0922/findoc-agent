import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react';
import { QADialog } from './QADialog.tsx';
import { ReportNavigationContext, type EditorState } from './reportNavigationContext.ts';
/** Only untrusted editor text is protected; pending operation identity survives navigation. */
export function ReportNavigation({ children }: { children: ReactNode }) {
  const editor = useRef<EditorState>({ dirty: false, pending: false });
  const currentUrl = useRef(location.href);
  const [next, setNext] = useState<(() => void) | null>(null);
  const setEditorState = useCallback((state: EditorState) => { editor.current = state; currentUrl.current = location.href; }, []);
  const requestLeave = useCallback((action: () => void) => {
    if (editor.current.dirty && !editor.current.pending) setNext(() => action); else action();
  }, []);
  useEffect(() => {
    const block = () => editor.current.dirty && !editor.current.pending;
    const click = (e: MouseEvent) => {
      const anchor = (e.target as Element).closest?.('a[href]') as HTMLAnchorElement | null;
      if (!block() || !anchor || anchor.target === '_blank' || anchor.hasAttribute('download') || e.ctrlKey || e.metaKey || e.shiftKey || e.altKey || e.button !== 0) return;
      const target = new URL(anchor.href);
      if (target.origin === location.origin && target.pathname === location.pathname && target.search === location.search) return;
      e.preventDefault(); e.stopImmediatePropagation(); requestLeave(() => location.assign(anchor.href));
    };
    const unload = (e: BeforeUnloadEvent) => { if (block()) { e.preventDefault(); e.returnValue = ''; } };
    // Capture prevents the route owner's popstate effect from discarding unsaved text.
    const pop = (e: PopStateEvent) => {
      if (!block()) return;
      e.stopImmediatePropagation(); const destination = location.href;
      history.pushState(null, '', currentUrl.current);
      requestLeave(() => location.assign(destination));
    };
    document.addEventListener('click', click, true); window.addEventListener('beforeunload', unload); window.addEventListener('popstate', pop, true);
    return () => { document.removeEventListener('click', click, true); window.removeEventListener('beforeunload', unload); window.removeEventListener('popstate', pop, true); };
  }, [requestLeave]);
  return <ReportNavigationContext.Provider value={{ setEditorState, requestLeave }}>{children}{next && <QADialog title="修改尚未保存" close={() => setNext(null)}>
    <p>当前标题与用户结论尚未保存。离开会放弃这些修改。</p><div className="report-dialog-actions"><button className="primary-button" onClick={() => setNext(null)}>继续编辑</button><button onClick={() => { const action = next; editor.current = { dirty: false, pending: false }; setNext(null); action(); }}>放弃修改并离开</button></div>
  </QADialog>}</ReportNavigationContext.Provider>;
}
