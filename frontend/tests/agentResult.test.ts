import assert from 'node:assert/strict'
import test from 'node:test'

import {
  buildAgentPendingView,
  buildAgentRequestErrorView,
  buildAgentResultView,
  parseAgentRunResponse,
} from '../src/agentResult.ts'

const VALID_ANSWERED_RESPONSE = {
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

test('首次 POST 按提交文档取回非空 run_id，不预设服务端身份', () => {
  const response = parseAgentRunResponse(
    VALID_ANSWERED_RESPONSE,
    { documentId: 'document-a' },
  )

  assert.equal(response.run_id, 'run-1')
  assert.equal(response.document_id, 'document-a')
  assert.equal(response.user_result.status, 'answered')
})

test('GET 已知 Run 时同时核对文档和预期 run_id', () => {
  assert.deepEqual(
    parseAgentRunResponse(
      VALID_ANSWERED_RESPONSE,
      { documentId: 'document-a', runId: 'run-1' },
    ),
    VALID_ANSWERED_RESPONSE,
  )
  assert.throws(
    () => parseAgentRunResponse(
      VALID_ANSWERED_RESPONSE,
      { documentId: 'document-a', runId: 'run-2' },
    ),
    /Run 身份不匹配/,
  )
  assert.throws(
    () => parseAgentRunResponse(
      VALID_ANSWERED_RESPONSE,
      { documentId: 'document-b' },
    ),
    /文档身份不匹配/,
  )
})

test('Agent answered 要求非空正文和至少一条严格合法引用', () => {
  assert.throws(
    () => parseAgentRunResponse({
      ...VALID_ANSWERED_RESPONSE,
      user_result: {
        ...VALID_ANSWERED_RESPONSE.user_result,
        content: '   ',
      },
    }, { documentId: 'document-a' }),
    /content/,
  )
  assert.throws(
    () => parseAgentRunResponse({
      ...VALID_ANSWERED_RESPONSE,
      user_result: {
        ...VALID_ANSWERED_RESPONSE.user_result,
        citations: [],
      },
    }, { documentId: 'document-a' }),
    /至少一条引用/,
  )
  assert.throws(
    () => parseAgentRunResponse({
      ...VALID_ANSWERED_RESPONSE,
      user_result: {
        ...VALID_ANSWERED_RESPONSE.user_result,
        citations: [{
          number: 1,
          source_file: 'report.pdf',
          page: 0,
          chunk_id: 'chunk-1',
        }],
      },
    }, { documentId: 'document-a' }),
    /page/,
  )
})

test('Agent 顶层和三态拒绝额外字段或非法字段组合', () => {
  assert.throws(
    () => parseAgentRunResponse({
      ...VALID_ANSWERED_RESPONSE,
      workspace_id: 'private-workspace',
    }, { documentId: 'document-a' }),
    /字段组合非法/,
  )
  assert.throws(
    () => parseAgentRunResponse({
      run_id: 'run-2',
      document_id: 'document-a',
      user_result: {
        status: 'refusal',
        reason: 'empty_retrieval',
        message: '没有证据',
        content: '不允许残留的正文',
      },
    }, { documentId: 'document-a' }),
    /字段组合非法/,
  )
})

test('HTTP 201 的 refusal 与产品 system_error 不会变成 answered', () => {
  const refusal = buildAgentResultView(parseAgentRunResponse({
    run_id: 'run-refusal',
    document_id: 'document-a',
    user_result: {
      status: 'refusal',
      reason: 'capability_limit',
      message: '当前请求超出有限能力范围',
    },
  }, { documentId: 'document-a' }))
  const systemError = buildAgentResultView(parseAgentRunResponse({
    run_id: 'run-error',
    document_id: 'document-a',
    user_result: {
      status: 'system_error',
      error_code: 'provider_error',
      message: '本次执行未发布答案',
    },
  }, { documentId: 'document-a' }))

  assert.equal(refusal.status, 'refusal')
  assert.equal(Object.hasOwn(refusal, 'content'), false)
  assert.equal(Object.hasOwn(refusal, 'citations'), false)
  assert.equal(systemError.status, 'system_error')
  assert.equal(Object.hasOwn(systemError, 'content'), false)
  assert.equal(Object.hasOwn(systemError, 'citations'), false)
})

test('HTTP 或网络错误与 Agent 产品三态保持独立', () => {
  const pending = buildAgentPendingView(1, 'document-a')
  const requestError = buildAgentRequestErrorView('无法取得 Agent 结果')

  assert.deepEqual(pending, {
    status: 'pending',
    requestId: 1,
    documentId: 'document-a',
  })
  assert.deepEqual(requestError, {
    status: 'request_error',
    message: '无法取得 Agent 结果',
  })
  assert.equal(Object.hasOwn(requestError, 'runId'), false)
  assert.equal(Object.hasOwn(requestError, 'content'), false)
})

test('Agent 有限拒答和系统错误枚举拒绝未知值', () => {
  assert.throws(
    () => parseAgentRunResponse({
      run_id: 'run-refusal',
      document_id: 'document-a',
      user_result: {
        status: 'refusal',
        reason: 'model_said_no',
        message: '未知拒答',
      },
    }, { documentId: 'document-a' }),
    /reason 非法/,
  )
  assert.throws(
    () => parseAgentRunResponse({
      run_id: 'run-error',
      document_id: 'document-a',
      user_result: {
        status: 'system_error',
        error_code: 'raw_exception',
        message: '未知错误',
      },
    }, { documentId: 'document-a' }),
    /error_code 非法/,
  )
})
