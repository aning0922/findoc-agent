import { useEffect, useState } from 'react';
import { ShowcaseReportsPanel } from './ShowcaseReportsPanel.tsx';

export function ShowcaseReportsEntry() {
  const [scope, setScope] = useState<string | null>(null);
  const [error, setError] = useState(false);
  useEffect(() => {
    const c = new AbortController();
    void fetch('/api/dashboard/overview', { signal: c.signal, cache: 'no-store' }).then(async r => {
      if (!r.ok) throw Error();
      const value = await r.json();
      if (value.schema_version !== 'dashboard-overview-v1' || !(value.lease_generation === null || Number.isSafeInteger(value.lease_generation))) throw Error();
      if (!c.signal.aborted) setScope(JSON.stringify(['demo', value.lease_generation, value.seed_version]));
    }).catch(() => { if (!c.signal.aborted) setError(true); });
    return () => c.abort();
  }, []);
  return scope ? <ShowcaseReportsPanel scopeKey={scope} /> : <p role={error ? 'alert' : 'status'}>{error ? '报告工作空间暂不可核验，请刷新页面重试。' : '正在核验报告工作空间…'}</p>;
}
