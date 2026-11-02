// Client ownership and recovery hints only; never a server execution/cancellation claim.
export interface ConversationOperation {
  operationId: string;
  conversationId: string | null;
  kind: 'create' | 'send' | 'delete';
}
const key = 'findoc:conversation-operations:v1';
const uuid = /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i;
export function validConversationOperation(v: unknown): v is ConversationOperation {
  if (!v || typeof v !== 'object') return false;
  const op = v as ConversationOperation;
  return uuid.test(op.operationId) && (op.kind === 'create' && op.conversationId === null
    || (op.kind === 'send' || op.kind === 'delete') && typeof op.conversationId === 'string' && uuid.test(op.conversationId));
}
export function readConversationOperations(storage: Pick<Storage, 'getItem'>): ConversationOperation[] {
  try {
    const value: unknown = JSON.parse(storage.getItem(key) || '[]');
    if (!Array.isArray(value) || !value.every(validConversationOperation)
      || new Set(value.map(v => v.operationId)).size !== value.length) throw new Error();
    return value;
  } catch { throw new Error('本机操作线索无法读取，请从服务端历史核对结果。'); }
}
export function rememberConversationOperation(storage: Pick<Storage, 'getItem' | 'setItem'>, operation: ConversationOperation): void {
  if (!validConversationOperation(operation)) throw new Error('操作身份不完整。');
  const operations = readConversationOperations(storage);
  const old = operations.find(v => v.operationId === operation.operationId);
  if (old && (old.conversationId !== operation.conversationId || old.kind !== operation.kind)) throw new Error('操作身份冲突。');
  if (!old) storage.setItem(key, JSON.stringify([...operations.map(v => ({ operationId: v.operationId, conversationId: v.conversationId, kind: v.kind })),
    { operationId: operation.operationId, conversationId: operation.conversationId, kind: operation.kind }]));
}
// Only call after a validated definitive receipt or the frozen pre-registration
// rejection of this exact POST, never after a transport error or GET 404.
export function resolveConversationOperation(storage: Pick<Storage, 'getItem' | 'setItem'>, operationId: string): void {
  storage.setItem(key, JSON.stringify(readConversationOperations(storage).filter(v => v.operationId !== operationId)
    .map(v => ({ operationId: v.operationId, conversationId: v.conversationId, kind: v.kind }))));
}
export function ownsConversationView(active: { conversationId: string | null; epoch: number }, candidate: { conversationId: string | null; epoch: number }): boolean {
  return active.conversationId === candidate.conversationId && active.epoch === candidate.epoch;
}
export interface ConversationScopeState<T> {
  facts: T[];
  chosenFacts: string[];
  factError: string;
  invalidPdf: string[];
}
// Preserve explicit choices on a read-only refresh of the same scope. They are
// never transferable to a newly created/recovered conversation, even in-place.
export function conversationScopeState<T>(previousId: string | null, nextId: string, current: ConversationScopeState<T>): ConversationScopeState<T> {
  return previousId === nextId ? current : { facts: [], chosenFacts: [], factError: '', invalidPdf: [] };
}
