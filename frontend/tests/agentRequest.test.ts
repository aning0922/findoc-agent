import assert from 'node:assert/strict'
import test from 'node:test'
import {
  AGENT_METRICS,
  buildAgentQuery,
  createAgentRun,
  type AgentFetch,
} from '../src/agentRequest.ts'

test('受控年份和固定指标生成无空格的完整任务文本', () => {
  assert.equal(buildAgentQuery('2025', '营业收入'), '查询2025年度营业收入')
  assert.equal(buildAgentQuery('2024', '净利润'), '查询2024年度净利润')
  assert.equal(buildAgentQuery('2023', '员工平均年龄'), '查询2023年度员工平均年龄')
  assert.deepEqual(AGENT_METRICS, ['营业收入', '净利润', '员工平均年龄'])
})

test('年份必须是四位 ASCII 数字', () => {
  for (const year of ['25', '20255', '２０２５', '20 25', '+2025']) {
    assert.throws(() => buildAgentQuery(year, '营业收入'), /四位数字/)
  }
})

test('POST 只发送一次固定 URL 和 document_id/query 两字段', async () => {
  const calls: Array<{ input: string; init: RequestInit }> = []
  const fetchImpl: AgentFetch = async (input, init) => {
    calls.push({ input, init })
    return {
      ok: true,
      status: 201,
      json: async () => ({
        run_id: 'run-2025-revenue',
        document_id: 'document-a',
        user_result: {
          status: 'answered',
          content: '2025 年营业收入为 100 万元。[1]',
          citations: [{
            number: 1,
            source_file: 'annual-report.pdf',
            page: 8,
            chunk_id: 'chunk-8',
          }],
        },
      }),
    }
  }

  const view = await createAgentRun(
    'document-a',
    buildAgentQuery('2025', '营业收入'),
    new AbortController().signal,
    fetchImpl,
  )

  assert.equal(calls.length, 1)
  assert.equal(calls[0]?.input, '/api/agent/runs')
  assert.equal(calls[0]?.init.method, 'POST')
  assert.deepEqual(JSON.parse(String(calls[0]?.init.body)), {
    document_id: 'document-a',
    query: '查询2025年度营业收入',
  })
  assert.deepEqual(view, {
    status: 'answered',
    runId: 'run-2025-revenue',
    documentId: 'document-a',
    content: '2025 年营业收入为 100 万元。[1]',
    citations: [{
      number: 1,
      source_file: 'annual-report.pdf',
      page: 8,
      chunk_id: 'chunk-8',
    }],
  })
})

test('受控响应仍由已有 DTO 身份守卫拒绝错文档', async () => {
  let callCount = 0
  const fetchImpl: AgentFetch = async () => {
    callCount += 1
    return {
      ok: true,
      status: 201,
      json: async () => ({
        run_id: 'run-wrong-document',
        document_id: 'document-b',
        user_result: {
          status: 'refusal',
          reason: 'empty_retrieval',
          message: '没有找到足够证据。',
        },
      }),
    }
  }

  await assert.rejects(
    createAgentRun(
      'document-a',
      buildAgentQuery('2025', '营业收入'),
      new AbortController().signal,
      fetchImpl,
    ),
    /文档身份不匹配/,
  )
  assert.equal(callCount, 1)
})

test('HTTP 失败只请求一次并交给页面显示 request_error', async () => {
  let callCount = 0
  const fetchImpl: AgentFetch = async () => {
    callCount += 1
    return { ok: false, status: 500, json: async () => ({}) }
  }

  await assert.rejects(
    createAgentRun(
      'document-a',
      buildAgentQuery('2025', '营业收入'),
      new AbortController().signal,
      fetchImpl,
    ),
    /请求失败/,
  )
  assert.equal(callCount, 1)
})
