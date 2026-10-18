import type { ReactNode } from 'react';
import { statusPresentation, type UserStatus } from './userStatus.ts';

export function StatusNotice({ state, title, children, action }: {
  state: UserStatus; title?: string; children?: ReactNode; action?: ReactNode;
}) {
  const presentation = statusPresentation[state];
  return <div className={`status-notice status-${presentation.tone}`} data-user-state={state} role={state === 'failed' || state === 'invalidated' ? 'alert' : 'status'}>
    <strong>{title || presentation.title}</strong>
    <div>{children || presentation.consequence}</div>
    {action && <div className="status-notice-action">{action}</div>}
  </div>;
}
