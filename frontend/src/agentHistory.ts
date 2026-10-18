import {
  buildAgentResultView,
  parseAgentRunResponse,
  type AgentTerminalView,
} from './agentResult.ts'
import type { AgentFetch } from './agentRequest.ts'
import type { AgentRunReference } from './agentRunIndex.ts'

export type AgentExecutionEventType =
  | 'tool_requested'
  | 'tool_succeeded'
  | 'tool_failed'
  | 'run_succeeded'
  | 'run_failed'

export interface AgentHistoryEvent {
  sequence: number
  executionEventType: AgentExecutionEventType
  summary: string
}

export type AgentHistoryErrorKind =
  | 'not_ready'
  | 'not_stored'
  | 'not_found'
  | 'unavailable'
  | 'server_error'
  | 'unknown'

export class AgentHistoryRequestError extends Error {
  readonly kind: AgentHistoryErrorKind

  constructor(kind: AgentHistoryErrorKind) {
    super('Agent 历史读取失败')
    this.name = 'AgentHistoryRequestError'
    this.kind = kind
  }
}

const EVENT_TYPES = new Set<AgentExecutionEventType>([
  'tool_requested',
  'tool_succeeded',
  'tool_failed',
  'run_succeeded',
  'run_failed',
])

function requireObject(value: unknown): Record<string, unknown> {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    throw new AgentHistoryRequestError('unknown')
  }
  return value as Record<string, unknown>
}

function requireExactKeys(value: Record<string, unknown>, keys: readonly string[]): void {
  const actualKeys = Object.keys(value)
  if (
    actualKeys.length !== keys.length
    || keys.some((key) => !Object.hasOwn(value, key))
  ) {
    throw new AgentHistoryRequestError('unknown')
  }
}

async function readErrorCode(response: Awaited<ReturnType<AgentFetch>>): Promise<string | null> {
  try {
    const body = requireObject(await response.json())
    requireExactKeys(body, ['detail'])
    const detail = requireObject(body.detail)
    if (typeof detail.code !== 'string') {
      return null
    }
    return detail.code
  } catch {
    return null
  }
}

async function throwForFailedResponse(
  response: Awaited<ReturnType<AgentFetch>>,
): Promise<never> {
  const code = await readErrorCode(response)
  if (response.status === 409 && code === 'agent_result_not_ready') {
    throw new AgentHistoryRequestError('not_ready')
  }
  if (response.status === 409 && code === 'agent_result_not_stored') {
    throw new AgentHistoryRequestError('not_stored')
  }
  if (response.status === 404) {
    throw new AgentHistoryRequestError('not_found')
  }
  if (response.status === 503) {
    throw new AgentHistoryRequestError('unavailable')
  }
  if (response.status >= 500) {
    throw new AgentHistoryRequestError('server_error')
  }
  throw new AgentHistoryRequestError('unknown')
}

/**
 * 通过已知身份读取已保存产品结果，只发一次 GET。
 *
 * 不带 query/body，不重新执行；Run 与文档身份仍由共用 DTO 守卫核对。
 */
export async function readAgentRun(
  reference: AgentRunReference,
  signal: AbortSignal,
  fetchImpl: AgentFetch = fetch,
): Promise<AgentTerminalView> {
  const response = await fetchImpl(
    `/api/agent/runs/${encodeURIComponent(reference.runId)}`,
    { method: 'GET', headers: { Accept: 'application/json' }, signal },
  )
  if (!response.ok) {
    await throwForFailedResponse(response)
  }
  const parsed = parseAgentRunResponse(await response.json(), {
    runId: reference.runId,
    documentId: reference.documentId,
  })
  return buildAgentResultView(parsed)
}

function parseEvent(value: unknown): AgentHistoryEvent {
  const event = requireObject(value)
  requireExactKeys(event, ['sequence', 'execution_event_type', 'summary'])
  if (!Number.isSafeInteger(event.sequence) || (event.sequence as number) <= 0) {
    throw new AgentHistoryRequestError('unknown')
  }
  if (
    typeof event.execution_event_type !== 'string'
    || !EVENT_TYPES.has(event.execution_event_type as AgentExecutionEventType)
    || typeof event.summary !== 'string'
    || event.summary.trim().length === 0
  ) {
    throw new AgentHistoryRequestError('unknown')
  }
  return {
    sequence: event.sequence as number,
    executionEventType: event.execution_event_type as AgentExecutionEventType,
    summary: event.summary,
  }
}

/** 读取并验证安全历史投影；只消费三项白名单字段并按 sequence 排序。 */
export async function readAgentEvents(
  reference: AgentRunReference,
  signal: AbortSignal,
  fetchImpl: AgentFetch = fetch,
): Promise<AgentHistoryEvent[]> {
  const response = await fetchImpl(
    `/api/agent/runs/${encodeURIComponent(reference.runId)}/events`,
    { method: 'GET', headers: { Accept: 'application/json' }, signal },
  )
  if (!response.ok) {
    await throwForFailedResponse(response)
  }

  const body = requireObject(await response.json())
  requireExactKeys(body, ['run_id', 'projection', 'events'])
  if (
    body.run_id !== reference.runId
    || body.projection !== 'history'
    || !Array.isArray(body.events)
  ) {
    throw new AgentHistoryRequestError('unknown')
  }
  const events = body.events.map(parseEvent).sort((left, right) => left.sequence - right.sequence)
  if (new Set(events.map((event) => event.sequence)).size !== events.length) {
    throw new AgentHistoryRequestError('unknown')
  }
  return events
}

/** 把已知 HTTP 分类收窄为固定安全说明，不回显响应或异常正文。 */
export function describeAgentHistoryError(error: unknown): string {
  if (!(error instanceof AgentHistoryRequestError)) {
    return '无法确认已保存结果；不会自动重试或创建新 Run。'
  }
  switch (error.kind) {
    case 'not_ready':
      return '运行结果尚未提交；页面不会自动轮询或重新执行。'
    case 'not_stored':
      return '此旧版或离线 Run 未保存可展示结果，等待不会使它自动恢复。'
    case 'not_found':
      return '该 Run 不存在或当前服务范围无权读取。'
    case 'unavailable':
      return 'Agent 服务未启用，暂时无法读取已保存结果。'
    case 'server_error':
      return '运行结果暂时无法安全读取；不会自动重试。'
    case 'unknown':
      return '无法确认已保存结果；不会自动重试或创建新 Run。'
  }
}
