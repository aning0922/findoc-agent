import { useLayoutEffect, useRef, type ReactNode } from 'react';
import styles from './ResearchQA.module.css';

/** Native modal owns background inertness; local keys keep focus in its visible controls. */
export function QADialog({ title, children, close, className = '' }: {
  title: string; children: ReactNode; close: () => void; className?: string;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useLayoutEffect(() => {
    const opener = document.activeElement as HTMLElement | null;
    const overflow = document.body.style.overflow;
    const dialog = ref.current!;
    dialog.showModal(); document.body.style.overflow = 'hidden';
    dialog.querySelector<HTMLButtonElement>('button')?.focus();
    return () => {
      dialog.close(); document.body.style.overflow = overflow;
      if (opener?.isConnected) opener.focus({ preventScroll: true });
    };
  }, []);
  return <dialog ref={ref} className={`${styles.dialog} ${className}`} aria-label={title}
    onCancel={e => { e.preventDefault(); close(); }} onKeyDown={e => {
      if (e.key !== 'Tab') return;
      const controls = [...ref.current!.querySelectorAll<HTMLElement>('button:not(:disabled), a[href], input:not(:disabled), select:not(:disabled), summary, [tabindex="0"]')]
        .filter(n => n.getClientRects().length && !n.closest('details:not([open]) > :not(summary)'));
      if (e.shiftKey && document.activeElement === controls[0]) { e.preventDefault(); controls.at(-1)?.focus(); }
      else if (!e.shiftKey && document.activeElement === controls.at(-1)) { e.preventDefault(); controls[0]?.focus(); }
    }}>
    <header className={styles.dialogHeader}><h2>{title}</h2><button onClick={close} aria-label={`关闭${title}`}>关闭</button></header>
    {children}
  </dialog>;
}
