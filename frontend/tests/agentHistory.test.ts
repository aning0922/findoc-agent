import assert from 'node:assert/strict'
import test from 'node:test'

import {
  AgentHistoryRequestError,
  describeAgentHistoryError,
  readAgentEvents,
  readAgentRun,
} from '../src/agentHistory.ts'
import type { AgentFetch } from '../src/agentRequest.ts'

const REFERENCE = { runId: 'run-1', documentId: 'document-a' }
const ANSWER = {
  run_id: 'run-1',
  document_id: 'document-a',
  user_result: {
    status: 'answered',
    content: '营业收入为 100 万元。[1]',
    citations: [{
      number: 1,
      source_file: 'report.pdf',
      page: 3,
      chunk_id: 'chunk-1',
    }],
  },
}

test('已知 Run 恢复只发一次无 body GET，并核对 Run/document 身份', async () => {
  const calls: Array<{ input: string; init: RequestInit }> = []
  const fetchImpl: AgentFetch = async (input, init) => {
    calls.push({ input, init })
    return { ok: true, status: 200, json: async () => ANSWER }
  }

  const result = await readAgentRun(
    REFERENCE,
    new AbortController().signal,
    fetchImpl,
  )

  assert.equal(result.status, 'answered')
  assert.equal(calls.length, 1)
  assert.equal(calls[0]?.input, '/api/agent/runs/run-1')
  assert.equal(calls[0]?.init.method, 'GET')
  assert.equal(calls[0]?.init.body, undefined)

  const wrongIdentityFetch: AgentFetch = async () => ({
    ok: true,
    status: 200,
    json: async () => ({ ...ANSWER, document_id: 'document-b' }),
  })
  await assert.rejects(
    readAgentRun(REFERENCE, new AbortController().signal, wrongIdentityFetch),
    /文档身份不匹配/,
  )
})

test('Run URL 身份被安全编码', async () => {
  let requestedUrl = ''
  const fetchImpl: AgentFetch = async (input) => {
    requestedUrl = input
    return {
      ok: true,
      status: 200,
      json: async () => ({ ...ANSWER, run_id: 'run/a b' }),
    }
  }
  await readAgentRun(
    { runId: 'run/a b', documentId: 'document-a' },
    new AbortController().signal,
    fetchImpl,
  )
  assert.equal(requestedUrl, '/api/agent/runs/run%2Fa%20b')
})

test('两类 409 使用不同安全说明，且每次只请求一次不轮询', async () => {
  for (const [code, expected] of [
    ['agent_result_not_ready', '不会自动轮询'],
    ['agent_result_not_stored', '等待不会使它自动恢复'],
  ] as const) {
    let calls = 0
    const fetchImpl: AgentFetch = async () => {
      calls += 1
      return {
        ok: false,
        status: 409,
        json: async () => ({ detail: { code, message: 'server text' } }),
      }
    }
    const error = await readAgentRun(
      REFERENCE,
      new AbortController().signal,
      fetchImpl,
    ).catch((caught: unknown) => caught)
    assert.equal(calls, 1)
    assert.match(describeAgentHistoryError(error), new RegExp(expected))
  }
})

test('404、500、503 和未知异常只产生固定安全说明', async () => {
  const cases = [
    { status: 404, expected: '不存在或当前服务范围无权读取' },
    { status: 500, expected: '暂时无法安全读取' },
    { status: 503, expected: '服务未启用' },
  ]
  for (const item of cases) {
    const fetchImpl: AgentFetch = async () => ({
      ok: false,
      status: item.status,
      json: async () => ({ detail: { code: 'raw_code', message: '/private/path' } }),
    })
    const error = await readAgentRun(
      REFERENCE,
      new AbortController().signal,
      fetchImpl,
    ).catch((caught: unknown) => caught)
    const message = describeAgentHistoryError(error)
    assert.match(message, new RegExp(item.expected))
    assert.equal(message.includes('/private/path'), false)
  }
  assert.equal(
    describeAgentHistoryError(new Error('secret database path')),
    '无法确认已保存结果；不会自动重试或创建新 Run。',
  )
})

test('Events 只接受有限白名单字段、核对 Run 并按 sequence 排序', async () => {
  const fetchImpl: AgentFetch = async () => ({
    ok: true,
    status: 200,
    json: async () => ({
      run_id: 'run-1',
      projection: 'history',
      events: [
        { sequence: 2, execution_event_type: 'run_succeeded', summary: '循环结束，结果另看接口。' },
        { sequence: 1, execution_event_type: 'tool_requested', summary: '记录工具申请。' },
      ],
    }),
  })
  const events = await readAgentEvents(
    REFERENCE,
    new AbortController().signal,
    fetchImpl,
  )
  assert.deepEqual(events.map((event) => event.sequence), [1, 2])
  assert.equal(events[1]?.executionEventType, 'run_succeeded')
  assert.equal(Object.hasOwn(events[0] ?? {}, 'payload'), false)

  for (const body of [
    { run_id: 'run-2', projection: 'history', events: [] },
    { run_id: 'run-1', projection: 'realtime', events: [] },
    {
      run_id: 'run-1',
      projection: 'history',
      events: [{ sequence: 1, execution_event_type: 'thought', summary: 'hidden' }],
    },
    {
      run_id: 'run-1',
      projection: 'history',
      events: [{
        sequence: 1,
        execution_event_type: 'tool_requested',
        summary: 'safe',
        payload: { private: true },
      }],
    },
  ]) {
    const invalidFetch: AgentFetch = async () => ({
      ok: true,
      status: 200,
      json: async () => body,
    })
    await assert.rejects(
      readAgentEvents(REFERENCE, new AbortController().signal, invalidFetch),
      AgentHistoryRequestError,
    )
  }
})

test('结果读取成功与 Events 失败是两条独立边界', async () => {
  const resultFetch: AgentFetch = async () => ({
    ok: true,
    status: 200,
    json: async () => ANSWER,
  })
  const eventsFetch: AgentFetch = async () => ({
    ok: false,
    status: 500,
    json: async () => ({ detail: { code: 'agent_storage_error', message: 'safe' } }),
  })

  const result = await readAgentRun(REFERENCE, new AbortController().signal, resultFetch)
  await assert.rejects(
    readAgentEvents(REFERENCE, new AbortController().signal, eventsFetch),
    AgentHistoryRequestError,
  )
  assert.equal(result.status, 'answered')
  assert.equal(result.runId, 'run-1')
})
