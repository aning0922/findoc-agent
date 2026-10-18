/** 浏览器本机只保存已确认 Run 的非内容引用，不保存任务或结果。 */
export interface AgentRunReference {
  runId: string
  documentId: string
}

/** 便于测试替换的最小 Web Storage 边界。 */
export interface AgentRunIndexStorage {
  getItem(key: string): string | null
  setItem(key: string, value: string): void
  removeItem(key: string): void
}

export const AGENT_RUN_INDEX_KEY = 'findoc.agent-run-index'
export const AGENT_RUN_INDEX_VERSION = 1
export const AGENT_RUN_INDEX_LIMIT = 20

export type AgentRunIndexIssue = 'none' | 'invalid' | 'unavailable'

export interface AgentRunIndexReadResult {
  references: AgentRunReference[]
  issue: AgentRunIndexIssue
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function hasExactKeys(value: Record<string, unknown>, keys: readonly string[]): boolean {
  const actualKeys = Object.keys(value)
  return actualKeys.length === keys.length
    && keys.every((key) => Object.hasOwn(value, key))
}

function parseReference(value: unknown): AgentRunReference | null {
  if (!isRecord(value) || !hasExactKeys(value, ['run_id', 'document_id'])) {
    return null
  }
  if (
    typeof value.run_id !== 'string'
    || value.run_id.trim().length === 0
    || typeof value.document_id !== 'string'
    || value.document_id.trim().length === 0
  ) {
    return null
  }
  return { runId: value.run_id, documentId: value.document_id }
}

function normalizeReferences(
  references: readonly AgentRunReference[],
): AgentRunReference[] {
  const seenRunIds = new Set<string>()
  const normalized: AgentRunReference[] = []
  for (const reference of references) {
    if (seenRunIds.has(reference.runId)) {
      continue
    }
    seenRunIds.add(reference.runId)
    normalized.push({ ...reference })
    if (normalized.length === AGENT_RUN_INDEX_LIMIT) {
      break
    }
  }
  return normalized
}

/**
 * 读取版本化本机索引。
 *
 * 输入：localStorage 或测试替身。
 * 输出：最新在前、按 Run 去重且最多 20 条的非内容引用。
 * 边界：损坏 JSON、未知版本和非法记录不会被当成可信结果。
 */
export function readAgentRunIndex(
  storage: AgentRunIndexStorage | null,
): AgentRunIndexReadResult {
  if (storage === null) {
    return { references: [], issue: 'unavailable' }
  }

  let raw: string | null
  try {
    raw = storage.getItem(AGENT_RUN_INDEX_KEY)
  } catch {
    return { references: [], issue: 'unavailable' }
  }
  if (raw === null) {
    return { references: [], issue: 'none' }
  }

  try {
    const parsed: unknown = JSON.parse(raw)
    if (
      !isRecord(parsed)
      || !hasExactKeys(parsed, ['version', 'runs'])
      || parsed.version !== AGENT_RUN_INDEX_VERSION
      || !Array.isArray(parsed.runs)
    ) {
      return { references: [], issue: 'invalid' }
    }

    const validReferences: AgentRunReference[] = []
    let hadInvalidRecord = parsed.runs.length > AGENT_RUN_INDEX_LIMIT
    for (const value of parsed.runs) {
      const reference = parseReference(value)
      if (reference === null) {
        hadInvalidRecord = true
        continue
      }
      validReferences.push(reference)
    }
    const references = normalizeReferences(validReferences)
    if (references.length !== validReferences.length) {
      hadInvalidRecord = true
    }
    return {
      references,
      issue: hadInvalidRecord ? 'invalid' : 'none',
    }
  } catch {
    return { references: [], issue: 'invalid' }
  }
}

function serializeReferences(references: readonly AgentRunReference[]): string {
  return JSON.stringify({
    version: AGENT_RUN_INDEX_VERSION,
    runs: normalizeReferences(references).map((reference) => ({
      run_id: reference.runId,
      document_id: reference.documentId,
    })),
  })
}

/**
 * 把已验证 Run 放到索引首位。
 *
 * 存储失败时仍返回新的内存引用，调用方不得因此抹掉已取得的结果。
 */
export function rememberAgentRun(
  storage: AgentRunIndexStorage | null,
  current: readonly AgentRunReference[],
  reference: AgentRunReference,
): { references: AgentRunReference[]; persisted: boolean } {
  const next = normalizeReferences([reference, ...current])
  if (storage === null) {
    return { references: next, persisted: false }
  }
  try {
    storage.setItem(AGENT_RUN_INDEX_KEY, serializeReferences(next))
    return { references: next, persisted: true }
  } catch {
    return { references: next, persisted: false }
  }
}

/** 从本应用索引移除一条引用；不删除服务端 Run。 */
export function removeAgentRun(
  storage: AgentRunIndexStorage | null,
  current: readonly AgentRunReference[],
  runId: string,
): { references: AgentRunReference[]; persisted: boolean } {
  const next = normalizeReferences(current.filter((item) => item.runId !== runId))
  if (storage === null) {
    return { references: next, persisted: false }
  }
  try {
    storage.setItem(AGENT_RUN_INDEX_KEY, serializeReferences(next))
    return { references: next, persisted: true }
  } catch {
    return { references: next, persisted: false }
  }
}

/** 只清除此应用的索引键；不调用 localStorage.clear。 */
export function clearAgentRunIndex(storage: AgentRunIndexStorage | null): boolean {
  if (storage === null) {
    return false
  }
  try {
    storage.removeItem(AGENT_RUN_INDEX_KEY)
    return true
  } catch {
    return false
  }
}
