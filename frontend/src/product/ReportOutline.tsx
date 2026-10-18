import { useEffect, useId, useRef, useState } from 'react';
export type ReportSection = { id: string; title: string };
export function ReportOutline({ sections }: { sections: ReportSection[] }) {
  const outlineId = useId();
  const [active, setActive] = useState(sections[0]?.id), [expanded, setExpanded] = useState(false);
  const jump = useRef<{ id: string; scrollY: number } | null>(null);
  useEffect(() => {
    let frame = 0;
    const update = (event?: Event) => {
      if (event?.type === 'resize') jump.current = null;
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        if (jump.current && Math.abs(window.scrollY - jump.current.scrollY) < 1) { setActive(jump.current.id); return; }
        jump.current = null;
        const current = sections.filter(s => (document.getElementById(s.id)?.getBoundingClientRect().top ?? Infinity) <= 180).at(-1);
        setActive(current?.id || sections[0]?.id);
      });
    };
    update(); window.addEventListener('scroll', update, { passive: true }); window.addEventListener('resize', update);
    return () => { cancelAnimationFrame(frame); window.removeEventListener('scroll', update); window.removeEventListener('resize', update); };
  }, [sections]);
  return <nav className="report-outline" aria-label="报告正文目录"><p className="eyebrow report-outline-heading">CONTENTS / 目录</p><button className="report-outline-toggle" aria-expanded={expanded} aria-controls={outlineId} onClick={() => setExpanded(v => !v)}>报告目录 · {sections.find(s => s.id === active)?.title || "执行摘要"}{expanded ? " · 收起" : " · 展开"}</button><ol id={outlineId} data-expanded={expanded}>{sections.map((s, i) => <li key={s.id}><button aria-current={active === s.id ? 'location' : undefined} onClick={() => {
    setExpanded(false);
    // On mobile, position the section after the expanded menu has collapsed.
    requestAnimationFrame(() => {
      const target = document.getElementById(s.id); target?.focus({ preventScroll: true }); target?.scrollIntoView({ block: 'start', behavior: 'instant' }); jump.current = { id: s.id, scrollY: window.scrollY }; setActive(s.id);
    });
  }}><span>{String(i + 1).padStart(2, '0')}</span>{s.title}</button></li>)}</ol></nav>;
}
