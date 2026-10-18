import type { ReactNode } from 'react';

export function DiagnosticDetails({ label = '诊断详情与身份', fields, children }: {
  label?: string; fields?: Record<string, string | number | null | undefined>; children?: ReactNode;
}) {
  return <details className="diagnostic-details"><summary>{label}</summary>
    {fields && <dl>{Object.entries(fields).filter(([, value]) => value !== null && value !== undefined).map(([name, value]) =>
      <div key={name}><dt>{name}</dt><dd><code>{String(value)}</code></dd></div>)}</dl>}
    {children}
  </details>;
}
