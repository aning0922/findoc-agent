import assert from 'node:assert/strict'
import test from 'node:test'

import {
  AGENT_RUN_INDEX_KEY,
  AGENT_RUN_INDEX_LIMIT,
  clearAgentRunIndex,
  readAgentRunIndex,
  rememberAgentRun,
  removeAgentRun,
  type AgentRunIndexStorage,
} from '../src/agentRunIndex.ts'

function memoryStorage(initial: string | null = null): {
  storage: AgentRunIndexStorage
  values: Map<string, string>
} {
  const values = new Map<string, string>()
  if (initial !== null) {
    values.set(AGENT_RUN_INDEX_KEY, initial)
  }
  return {
    values,
    storage: {
      getItem: (key) => values.get(key) ?? null,
      setItem: (key, value) => { values.set(key, value) },
      removeItem: (key) => { values.delete(key) },
    },
  }
}

test('版本化索引按 Run 去重、保留最新在前并限制为 20 条', () => {
  const runs = Array.from({ length: AGENT_RUN_INDEX_LIMIT + 3 }, (_, index) => ({
    run_id: `run-${index}`,
    document_id: `document-${index}`,
  }))
  runs.splice(2, 0, { run_id: 'run-0', document_id: 'wrong-duplicate' })
  const { storage } = memoryStorage(JSON.stringify({ version: 1, runs }))

  const result = readAgentRunIndex(storage)

  assert.equal(result.issue, 'invalid')
  assert.equal(result.references.length, AGENT_RUN_INDEX_LIMIT)
  assert.deepEqual(result.references[0], { runId: 'run-0', documentId: 'document-0' })
  assert.equal(result.references.filter((item) => item.runId === 'run-0').length, 1)
})

test('损坏 JSON、未知版本和非法内容记录不会成为可恢复结果', () => {
  assert.deepEqual(readAgentRunIndex(memoryStorage('{broken').storage), {
    references: [],
    issue: 'invalid',
  })
  assert.deepEqual(readAgentRunIndex(memoryStorage(JSON.stringify({ version: 2, runs: [] })).storage), {
    references: [],
    issue: 'invalid',
  })

  const { storage } = memoryStorage(JSON.stringify({
    version: 1,
    runs: [
      { run_id: 'run-good', document_id: 'document-a' },
      { run_id: 'run-content', document_id: 'document-a', answer: '不应保留' },
      { run_id: '', document_id: 'document-a' },
    ],
  }))
  assert.deepEqual(readAgentRunIndex(storage), {
    references: [{ runId: 'run-good', documentId: 'document-a' }],
    issue: 'invalid',
  })
})

test('写入只持久化 Run/document 引用，按 Run 替换并裁剪上限', () => {
  const { storage, values } = memoryStorage()
  const current = Array.from({ length: AGENT_RUN_INDEX_LIMIT }, (_, index) => ({
    runId: `run-${index}`,
    documentId: `document-${index}`,
  }))
  const saved = rememberAgentRun(storage, current, {
    runId: 'run-2',
    documentId: 'document-reconfirmed',
  })

  assert.equal(saved.persisted, true)
  assert.equal(saved.references.length, AGENT_RUN_INDEX_LIMIT)
  assert.deepEqual(saved.references[0], {
    runId: 'run-2',
    documentId: 'document-reconfirmed',
  })
  const raw = values.get(AGENT_RUN_INDEX_KEY) ?? ''
  assert.equal(raw.includes('query'), false)
  assert.equal(raw.includes('answer'), false)
  assert.deepEqual(Object.keys(JSON.parse(raw).runs[0]).sort(), ['document_id', 'run_id'])
})

test('存储不可用不会抹掉内存中的已确认引用', () => {
  const throwingStorage: AgentRunIndexStorage = {
    getItem: () => { throw new Error('private mode') },
    setItem: () => { throw new Error('quota') },
    removeItem: () => { throw new Error('blocked') },
  }

  assert.deepEqual(readAgentRunIndex(throwingStorage), {
    references: [],
    issue: 'unavailable',
  })
  assert.deepEqual(rememberAgentRun(throwingStorage, [], {
    runId: 'run-1',
    documentId: 'document-a',
  }), {
    references: [{ runId: 'run-1', documentId: 'document-a' }],
    persisted: false,
  })
  assert.equal(clearAgentRunIndex(throwingStorage), false)
})

test('移除和清除只操作本应用索引键', () => {
  const { storage, values } = memoryStorage()
  values.set('other-app', 'keep-me')
  rememberAgentRun(storage, [], { runId: 'run-1', documentId: 'document-a' })

  const removed = removeAgentRun(storage, [
    { runId: 'run-1', documentId: 'document-a' },
    { runId: 'run-2', documentId: 'document-b' },
  ], 'run-1')
  assert.deepEqual(removed.references, [{ runId: 'run-2', documentId: 'document-b' }])
  assert.equal(clearAgentRunIndex(storage), true)
  assert.equal(values.has(AGENT_RUN_INDEX_KEY), false)
  assert.equal(values.get('other-app'), 'keep-me')
})
