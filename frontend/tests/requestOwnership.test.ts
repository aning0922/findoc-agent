import assert from 'node:assert/strict'
import test from 'node:test'

import {
  canChangeDocument,
  canStartRequest,
  createAgentHistoryRequestSnapshot,
  createRequestSnapshot,
  isCurrentAgentHistoryRequest,
  isCurrentRequest,
  isRequestDocumentReady,
  resolveActiveRequest,
  type RequestSnapshot,
} from '../src/requestOwnership.ts'

test('活动请求在 React 重渲染前也阻止重复提交', () => {
  const request = createRequestSnapshot(1, 'document-a', '查询2025年度营业收入')

  assert.equal(canStartRequest(null), true)
  assert.equal(canStartRequest(request), false)
})

test('pending 时文档切换同时受实际入口守卫保护', () => {
  const request = createRequestSnapshot(1, 'document-a', '查询2025年度营业收入')

  assert.equal(canChangeDocument(request), false)
  assert.equal(canChangeDocument(null), true)
})

test('RAG 或 Agent 任一 pending 都会占有共享入口', () => {
  const ragRequest = createRequestSnapshot(1, 'document-a', '自由问题')
  const agentRequest = createRequestSnapshot(2, 'document-a', '查询2025年度营业收入')

  assert.equal(canStartRequest(resolveActiveRequest(ragRequest, null)), false)
  assert.equal(canStartRequest(resolveActiveRequest(null, agentRequest)), false)
  assert.equal(canChangeDocument(resolveActiveRequest(null, agentRequest)), false)
  assert.equal(resolveActiveRequest(null, null), null)
  assert.throws(
    () => resolveActiveRequest(ragRequest, agentRequest),
    /只能有一个活动请求/,
  )
})

test('相同文档和问题的迟到请求仍按本地请求身份丢弃', () => {
  const oldRequest = createRequestSnapshot(1, 'document-a', '查询2025年度营业收入')
  const currentRequest = createRequestSnapshot(2, 'document-a', '查询2025年度营业收入')

  assert.equal(isCurrentRequest(currentRequest, oldRequest), false)
  assert.equal(isCurrentRequest(currentRequest, currentRequest), true)
})

test('文档消失或失去 ready 会使提交快照失效', () => {
  const request = createRequestSnapshot(1, 'document-a', '查询2025年度营业收入')

  assert.equal(isRequestDocumentReady([
    { document_id: 'document-a', status: 'ready' },
  ], request), true)
  assert.equal(isRequestDocumentReady([
    { document_id: 'document-a', status: 'indexing' },
  ], request), false)
  assert.equal(isRequestDocumentReady([
    { document_id: 'document-b', status: 'ready' },
  ], request), false)
})

test('旧 finally 不能清除新请求拥有的 pending', () => {
  const oldRequest = createRequestSnapshot(1, 'document-a', '查询2025年度营业收入')
  const newRequest = createRequestSnapshot(2, 'document-b', '查询2024年度净利润')
  let activeRequest: RequestSnapshot | null = newRequest

  if (isCurrentRequest(activeRequest, oldRequest)) {
    activeRequest = null
  }

  assert.equal(activeRequest, newRequest)
})

test('请求快照拒绝空身份和非法请求号', () => {
  assert.throws(
    () => createRequestSnapshot(0, 'document-a', '查询2025年度营业收入'),
    /请求号/,
  )
  assert.throws(
    () => createRequestSnapshot(1, '   ', '查询2025年度营业收入'),
    /文档 ID/,
  )
  assert.throws(
    () => createRequestSnapshot(1, 'document-a', '   '),
    /问题/,
  )
})

test('历史 GET 使用无 query 的独立 Run/document 身份并拒绝迟到响应', () => {
  const oldRequest = createAgentHistoryRequestSnapshot(1, 'run-1', 'document-a')
  const currentRequest = createAgentHistoryRequestSnapshot(2, 'run-2', 'document-b')

  assert.equal(Object.hasOwn(oldRequest, 'query'), false)
  assert.equal(isCurrentAgentHistoryRequest(currentRequest, oldRequest), false)
  assert.equal(isCurrentAgentHistoryRequest(currentRequest, currentRequest), true)
  assert.equal(canStartRequest(currentRequest), false)
})
