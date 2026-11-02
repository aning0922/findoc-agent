import { conversationJSON } from './conversationApi.ts';
import type { MemoryKey } from './conversationTypes.ts';
export const preferenceValues: Record<MemoryKey, Record<string, string>> = {
  analysis_focus: { cash_flow: '现金流', revenue: '营业收入', profitability: '盈利能力', balanced: '均衡研究' },
  display_unit: { CNY_YUAN: '元', CNY_TEN_THOUSAND: '万元', CNY_HUNDRED_MILLION: '亿元' },
  research_habit: { evidence_first: '先看证据', compare_periods_first: '先比较期间' },
};
export const preferenceKeys: Record<MemoryKey, string> = { analysis_focus: '分析侧重', display_unit: '展示单位', research_habit: '研究习惯' };
export interface MemoryItem { schema_version: 'memory-item-v1'; memory_id: string; type: 'research_preference'; key: MemoryKey; value: string; source_turn_id: string | null; revision: number; confirmed_at: string; created_at: string; updated_at: string }
export interface MemoryList { schema_version: 'memory-list-v1'; items: MemoryItem[]; generation: number }
export interface MemoryOperation { schema_version: 'memory-operation-v1'; operation_id: string; memory_id: string; kind: 'create_memory' | 'update_memory' | 'delete_memory'; status: 'completed'; revision: number; resource_deleted: boolean; created_at: string }
export interface PendingMemory { operationId: string; kind: MemoryOperation['kind']; memoryId: string | null }
const uuid = /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/;
export function validPreference(key: string, value: string): key is MemoryKey { return Object.hasOwn(preferenceValues, key) && Object.hasOwn(preferenceValues[key as MemoryKey], value); }
export function validateMemoryItem(v: MemoryItem): MemoryItem {
  if (!v || v.schema_version !== 'memory-item-v1' || !uuid.test(v.memory_id) || v.type !== 'research_preference'
    || !validPreference(v.key, v.value) || !Number.isSafeInteger(v.revision) || v.revision < 1
    || !(v.source_turn_id === null || uuid.test(v.source_turn_id))
    || [v.confirmed_at, v.created_at, v.updated_at].some(t => !t || !Number.isFinite(Date.parse(t)))) throw new Error('研究偏好响应不完整。');
  return v;
}
export async function listMemories(signal: AbortSignal): Promise<MemoryList> {
  const v = await conversationJSON<MemoryList>('/memories', signal);
  if (!v || v.schema_version !== 'memory-list-v1' || !Array.isArray(v.items) || !Number.isSafeInteger(v.generation)
    || v.generation < 0 || new Set(v.items.map(i => i.key)).size !== v.items.length) throw new Error('研究偏好列表不完整。');
  v.items.forEach(validateMemoryItem); return v;
}
export async function readMemoryOperation(pending: PendingMemory, signal: AbortSignal): Promise<MemoryOperation> {
  const v = await conversationJSON<MemoryOperation>(`/memory-operations/${encodeURIComponent(pending.operationId)}`, signal);
  return validateMemoryOperation(v, pending);
}
export function validateMemoryOperation(v: MemoryOperation, pending: PendingMemory): MemoryOperation {
  if (!v || v.schema_version !== 'memory-operation-v1' || v.operation_id !== pending.operationId || v.kind !== pending.kind
    || !uuid.test(v.memory_id) || pending.memoryId !== null && pending.memoryId !== v.memory_id
    || v.status !== 'completed' || !Number.isSafeInteger(v.revision) || v.revision < 1
    || v.resource_deleted !== (pending.kind === 'delete_memory') || !Number.isFinite(Date.parse(v.created_at))) throw new Error('研究偏好操作回执不一致。');
  return v;
}
export function readPendingMemory(storage: Pick<Storage, 'getItem'>): PendingMemory | null {
  const raw = storage.getItem('findoc:memory-operation:v1');
  if (!raw) return null;
  const v = JSON.parse(raw) as PendingMemory;
  if (!v || !uuid.test(v.operationId) || !['create_memory', 'update_memory', 'delete_memory'].includes(v.kind)
    || !(v.memoryId === null && v.kind === 'create_memory' || typeof v.memoryId === 'string' && uuid.test(v.memoryId))) throw new Error('偏好操作线索损坏，请核对历史。');
  return v;
}
export function storePendingMemory(storage: Pick<Storage, 'setItem' | 'removeItem'>, pending: PendingMemory | null): void {
  if (pending) storage.setItem('findoc:memory-operation:v1', JSON.stringify({ operationId: pending.operationId, memoryId: pending.memoryId, kind: pending.kind }));
  else storage.removeItem('findoc:memory-operation:v1');
}
