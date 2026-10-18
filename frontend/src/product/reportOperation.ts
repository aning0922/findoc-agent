const pendingKey = 'findoc-report-unknown-operation-v1';
export function storedOperation(): string { try { return sessionStorage.getItem(pendingKey) || ''; } catch { return ''; } }
export function rememberOperation(op: string) { try { if (op) sessionStorage.setItem(pendingKey, op); else sessionStorage.removeItem(pendingKey); } catch { /* mounted state still retains identity */ } }
