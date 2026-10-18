import assert from 'node:assert/strict'
import test from 'node:test'

import {
  buildChatTerminalView,
  parseCitationView,
} from '../src/ragResult.ts'

const VALID_CITATION = {
  number: 1,
  source_file: 'report.pdf',
  page: 3,
  chunk_id: 'chunk-1',
}

test('RAG success 同时要求非空正文和至少一条合法引用', () => {
  const view = buildChatTerminalView({
    answer: '营业收入为 100 万元。[1]',
    citations: [VALID_CITATION],
    refusalReason: null,
    errorMessage: null,
    doneOutcome: 'success',
  })

  assert.equal(view.status, 'success')
  assert.equal(view.answer, '营业收入为 100 万元。[1]')
  assert.deepEqual(view.citations, [VALID_CITATION])
})

test('RAG success 拒绝空正文或空引用', () => {
  assert.throws(
    () => buildChatTerminalView({
      answer: '   ',
      citations: [VALID_CITATION],
      refusalReason: null,
      errorMessage: null,
      doneOutcome: 'success',
    }),
    /非空 final_answer/,
  )
  assert.throws(
    () => buildChatTerminalView({
      answer: '没有引用的正文',
      citations: [],
      refusalReason: null,
      errorMessage: null,
      doneOutcome: 'success',
    }),
    /合法引用/,
  )
})

test('RAG citation 要求正整数和非空来源字段', () => {
  assert.deepEqual(parseCitationView(VALID_CITATION), VALID_CITATION)
  assert.throws(
    () => parseCitationView({ ...VALID_CITATION, number: 0 }),
    /citation 字段非法/,
  )
  assert.throws(
    () => parseCitationView({ ...VALID_CITATION, page: 1.5 }),
    /citation 字段非法/,
  )
  assert.throws(
    () => parseCitationView({ ...VALID_CITATION, chunk_id: '   ' }),
    /citation 字段非法/,
  )
})

test('RAG refusal 和 error 终态不保留正文或引用', () => {
  const refusalView = buildChatTerminalView({
    answer: '不应进入拒答展示的旧正文',
    citations: [VALID_CITATION],
    refusalReason: 'empty_retrieval',
    errorMessage: null,
    doneOutcome: 'refusal',
  })
  const errorView = buildChatTerminalView({
    answer: '不应进入错误展示的旧正文',
    citations: [VALID_CITATION],
    refusalReason: null,
    errorMessage: '响应校验失败',
    doneOutcome: 'error',
  })

  assert.equal(refusalView.answer, null)
  assert.deepEqual(refusalView.citations, [])
  assert.equal(errorView.answer, null)
  assert.deepEqual(errorView.citations, [])
})

test('RAG 暂存内容与 done 不匹配时拒绝形成展示状态', () => {
  assert.throws(
    () => buildChatTerminalView({
      answer: null,
      citations: [],
      refusalReason: null,
      errorMessage: null,
      doneOutcome: 'refusal',
    }),
    /reason/,
  )
  assert.throws(
    () => buildChatTerminalView({
      answer: null,
      citations: [],
      refusalReason: null,
      errorMessage: null,
      doneOutcome: null,
    }),
    /终态与事件内容不匹配/,
  )
})
