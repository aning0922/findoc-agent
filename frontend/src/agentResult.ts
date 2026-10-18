/** Agent 公开引用 DTO；只表示结构合法，不重新核证服务端证据来源。 */
export interface AgentCitation {
  number: number
  source_file: string
  page: number
  chunk_id: string
}

/** Agent 已回答产品结果；正文和至少一条合法引用必须同时存在。 */
export interface AgentAnsweredResult {
  status: 'answered'
  content: string
  citations: AgentCitation[]
}

/** Agent 正常拒答允许的有限公开原因。 */
export type AgentRefusalReason = 'empty_retrieval' | 'capability_limit'

/** Agent 正常拒答产品结果；该分支不含答案或引用。 */
export interface AgentRefusalResult {
  status: 'refusal'
  reason: AgentRefusalReason
  message: string
}

/** Agent 产品系统错误允许公开的有限稳定错误码。 */
export type AgentResultError =
  | 'protocol_error'
  | 'tool_error'
  | 'provider_error'
  | 'max_steps_reached'
  | 'output_validation_error'
  | 'evidence_validation_error'
  | 'citation_validation_error'
  | 'unverified_refusal'

/** Agent 已提交的产品系统错误；该分支不含候选正文或引用。 */
export interface AgentSystemErrorResult {
  status: 'system_error'
  error_code: AgentResultError
  message: string
}

/** Agent 公开产品结果三态；不能用 HTTP 201 或执行事件推导 answered。 */
export type AgentUserResult =
  | AgentAnsweredResult
  | AgentRefusalResult
  | AgentSystemErrorResult

/** Agent POST 和持久 GET 共用的严格公开响应 DTO。 */
export interface AgentRunResponse {
  run_id: string
  document_id: string
  user_result: AgentUserResult
}

/**
 * 当前请求阶段对 Agent 响应身份的预期。
 *
 * 输入：提交时的 documentId；GET 已知 Run 时额外传 runId。
 * 输出：供 parseAgentRunResponse 核对服务端响应身份。
 * 边界：首次 POST 前没有服务端 run_id，因此 runId 必须允许省略。
 */
export interface AgentResponseExpectation {
  documentId: string
  runId?: string
}

/**
 * 尚未接线的 Agent 页面最小独立状态。
 *
 * 输入：未来由本地请求守卫、严格 DTO 或 HTTP/网络失败分别构造。
 * 输出：确保 answered、refusal、产品错误和请求错误不与 RAG 状态混用。
 * 边界：拒答和错误分支在类型上没有 content/citations，不能残留旧答案。
 */
export type AgentViewState =
  | { status: 'idle' }
  | { status: 'pending'; requestId: number; documentId: string }
  | {
    status: 'answered'
    runId: string
    documentId: string
    content: string
    citations: AgentCitation[]
  }
  | {
    status: 'refusal'
    runId: string
    documentId: string
    reason: AgentRefusalReason
    message: string
  }
  | {
    status: 'system_error'
    runId: string
    documentId: string
    errorCode: AgentResultError
    message: string
  }
  | { status: 'request_error'; message: string }

/** POST 或 GET 严格解析后唯一可能产生的三种已提交终态。 */
export type AgentTerminalView = Extract<
  AgentViewState,
  { status: 'answered' | 'refusal' | 'system_error' }
>

/** Agent 页面尚未发起请求时的独立初始状态。 */
export const INITIAL_AGENT_VIEW: AgentViewState = { status: 'idle' }

const REFUSAL_REASONS = new Set<AgentRefusalReason>([
  'empty_retrieval',
  'capability_limit',
])

const RESULT_ERRORS = new Set<AgentResultError>([
  'protocol_error',
  'tool_error',
  'provider_error',
  'max_steps_reached',
  'output_validation_error',
  'evidence_validation_error',
  'citation_validation_error',
  'unverified_refusal',
])

/**
 * 建立一次 Agent 请求的独立 pending 展示状态。
 *
 * @param requestId - 已由前端请求守卫占有的正整数身份。
 * @param documentId - 提交快照中的文档 ID。
 * @returns 不借用 RAG streaming 的 Agent pending 状态。
 * @throws 请求号或文档身份非法时抛出 Error。
 */
export function buildAgentPendingView(
  requestId: number,
  documentId: string,
): AgentViewState {
  if (!Number.isSafeInteger(requestId) || requestId <= 0) {
    throw new Error('Agent pending 请求号必须是正安全整数')
  }
  return {
    status: 'pending',
    requestId,
    documentId: requireNonEmptyString(documentId, 'Agent pending documentId'),
  }
}

/**
 * 将未知 JSON 值收窄为可按键读取的对象。
 *
 * @param value - JSON.parse 后的未知值。
 * @param label - 结构错误时使用的安全字段说明。
 * @returns 可读取字符串键的对象。
 * @throws null、数组或非对象时抛出 Error。
 */
function requireObject(value: unknown, label: string): Record<string, unknown> {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    throw new Error(`${label} 必须是对象`)
  }
  return value as Record<string, unknown>
}

/**
 * 要求公开 DTO 对象只包含指定白名单字段。
 *
 * @param value - 已确认可读取的对象。
 * @param expectedKeys - 该状态唯一允许的字段名。
 * @param label - 结构错误时使用的安全字段说明。
 * @returns void；完全匹配时正常返回。
 * @throws 缺字段或含额外字段时抛出 Error。
 */
function requireExactKeys(
  value: Record<string, unknown>,
  expectedKeys: readonly string[],
  label: string,
): void {
  const actualKeys = Object.keys(value)
  if (
    actualKeys.length !== expectedKeys.length
    || expectedKeys.some((key) => !Object.hasOwn(value, key))
  ) {
    throw new Error(`${label} 字段组合非法`)
  }
}

/**
 * 读取严格非空字符串并保留服务端原值。
 *
 * @param value - 未经信任的字段值。
 * @param label - 结构错误时使用的安全字段说明。
 * @returns 不是纯空白的原字符串。
 * @throws 非字符串、空串或纯空白时抛出 Error。
 */
function requireNonEmptyString(value: unknown, label: string): string {
  if (typeof value !== 'string' || value.trim().length === 0) {
    throw new Error(`${label} 必须是非空字符串`)
  }
  return value
}

/**
 * 解析 Agent answered 的单条公开引用。
 *
 * @param value - citations 数组中的未知元素。
 * @returns 字段严格、正整数且非空的引用副本。
 * @throws 字段缺失、多余或值非法时抛出 Error。
 */
function parseAgentCitation(value: unknown): AgentCitation {
  const citation = requireObject(value, 'Agent citation')
  requireExactKeys(
    citation,
    ['number', 'source_file', 'page', 'chunk_id'],
    'Agent citation',
  )
  if (!Number.isSafeInteger(citation.number) || (citation.number as number) <= 0) {
    throw new Error('Agent citation number 必须是正整数')
  }
  if (!Number.isSafeInteger(citation.page) || (citation.page as number) <= 0) {
    throw new Error('Agent citation page 必须是正整数')
  }
  return {
    number: citation.number as number,
    source_file: requireNonEmptyString(citation.source_file, 'Agent citation source_file'),
    page: citation.page as number,
    chunk_id: requireNonEmptyString(citation.chunk_id, 'Agent citation chunk_id'),
  }
}

/**
 * 按 status 解析 Agent 公开产品结果三态。
 *
 * @param value - user_result 的未知 JSON 值。
 * @returns 严格白名单的 answered、refusal 或 system_error。
 * @throws 状态未知、有限枚举非法或混入其他状态字段时抛出 Error。
 */
function parseAgentUserResult(value: unknown): AgentUserResult {
  const result = requireObject(value, 'Agent user_result')
  const status = result.status

  if (status === 'answered') {
    requireExactKeys(result, ['status', 'content', 'citations'], 'Agent answered')
    if (!Array.isArray(result.citations) || result.citations.length === 0) {
      throw new Error('Agent answered 必须包含至少一条引用')
    }
    return {
      status,
      content: requireNonEmptyString(result.content, 'Agent answered content'),
      citations: result.citations.map(parseAgentCitation),
    }
  }

  if (status === 'refusal') {
    requireExactKeys(result, ['status', 'reason', 'message'], 'Agent refusal')
    if (typeof result.reason !== 'string' || !REFUSAL_REASONS.has(result.reason as AgentRefusalReason)) {
      throw new Error('Agent refusal reason 非法')
    }
    return {
      status,
      reason: result.reason as AgentRefusalReason,
      message: requireNonEmptyString(result.message, 'Agent refusal message'),
    }
  }

  if (status === 'system_error') {
    requireExactKeys(result, ['status', 'error_code', 'message'], 'Agent system_error')
    if (
      typeof result.error_code !== 'string'
      || !RESULT_ERRORS.has(result.error_code as AgentResultError)
    ) {
      throw new Error('Agent system_error error_code 非法')
    }
    return {
      status,
      error_code: result.error_code as AgentResultError,
      message: requireNonEmptyString(result.message, 'Agent system_error message'),
    }
  }

  throw new Error('Agent user_result status 非法')
}

/**
 * 解析并核对一次 Agent POST 或 GET 的公开响应。
 *
 * @param value - response.json() 得到的未知值。
 * @param expectation - 本地提交文档，以及 GET 阶段可选的已知 run_id。
 * @returns 只含 run_id、document_id 和严格 user_result 的新对象。
 * @throws 顶层/三态结构非法、文档不匹配或已知 Run 身份不匹配时抛出 Error。
 * @remarks 首次 POST 不预设 run_id，但仍要求响应给出非空 run_id。
 */
export function parseAgentRunResponse(
  value: unknown,
  expectation: AgentResponseExpectation,
): AgentRunResponse {
  const response = requireObject(value, 'Agent response')
  requireExactKeys(response, ['run_id', 'document_id', 'user_result'], 'Agent response')

  const runId = requireNonEmptyString(response.run_id, 'Agent run_id')
  const documentId = requireNonEmptyString(response.document_id, 'Agent document_id')
  if (expectation.documentId.trim().length === 0 || documentId !== expectation.documentId) {
    throw new Error('Agent 响应文档身份不匹配')
  }
  if (expectation.runId !== undefined) {
    if (expectation.runId.trim().length === 0 || runId !== expectation.runId) {
      throw new Error('Agent 响应 Run 身份不匹配')
    }
  }

  return {
    run_id: runId,
    document_id: documentId,
    user_result: parseAgentUserResult(response.user_result),
  }
}

/**
 * 将严格 Agent DTO 转为与 RAG 分离的产品展示状态。
 *
 * @param response - 已通过 parseAgentRunResponse 的公开响应。
 * @returns 按 user_result.status 区分的独立页面状态。
 * @remarks HTTP 201 本身不会调用 answered 分支；拒答和错误不会携带旧正文/引用。
 */
export function buildAgentResultView(response: AgentRunResponse): AgentTerminalView {
  const result = response.user_result
  if (result.status === 'answered') {
    return {
      status: 'answered',
      runId: response.run_id,
      documentId: response.document_id,
      content: result.content,
      citations: [...result.citations],
    }
  }
  if (result.status === 'refusal') {
    return {
      status: 'refusal',
      runId: response.run_id,
      documentId: response.document_id,
      reason: result.reason,
      message: result.message,
    }
  }
  return {
    status: 'system_error',
    runId: response.run_id,
    documentId: response.document_id,
    errorCode: result.error_code,
    message: result.message,
  }
}

/**
 * 建立 HTTP 或网络级失败的独立 Agent 页面状态。
 *
 * @param message - 前端选择公开的安全说明。
 * @returns 不含 run_id、正文或引用的 request_error 状态。
 * @throws 空或纯空白说明会被拒绝，避免展示无意义错误。
 */
export function buildAgentRequestErrorView(message: string): AgentViewState {
  return {
    status: 'request_error',
    message: requireNonEmptyString(message, 'Agent request_error message'),
  }
}
