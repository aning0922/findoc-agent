import {
  buildAgentResultView,
  parseAgentRunResponse,
  type AgentTerminalView,
} from './agentResult.ts'

/** Agent 首版允许选择的三个固定指标。 */
export const AGENT_METRICS = [
  '营业收入',
  '净利润',
  '员工平均年龄',
] as const

export type AgentMetric = typeof AGENT_METRICS[number]

/** 可为测试注入的最小 fetch 边界；生产默认仍调用浏览器 fetch。 */
export type AgentFetch = (
  input: string,
  init: RequestInit,
) => Promise<Pick<Response, 'ok' | 'status' | 'json'>>

/**
 * 将受控年份和指标拼成后端当前支持的完整任务文本。
 *
 * @param year - 用户输入的四位 ASCII 年份。
 * @param metric - 固定指标选项之一。
 * @returns 与服务端完整匹配合同一致、不含额外空格的任务文本。
 * @throws 年份或指标越出首版范围时抛出 Error，不发送请求。
 */
export function buildAgentQuery(year: string, metric: AgentMetric): string {
  if (!/^[0-9]{4}$/.test(year)) {
    throw new Error('年份必须是四位数字')
  }
  if (!AGENT_METRICS.includes(metric)) {
    throw new Error('指标不在当前支持范围内')
  }
  return `查询${year}年度${metric}`
}

/**
 * 创建一次 Agent Run，并把受控 JSON 收窄为已有独立页面三态。
 *
 * @param documentId - 当前提交快照中的 ready 文档身份。
 * @param query - 已由 buildAgentQuery 生成的有限任务文本。
 * @param signal - 仅停止客户端等待的取消信号，不证明后端任务取消。
 * @param fetchImpl - 默认浏览器 fetch；测试可注入一次性受控响应。
 * @returns answered、refusal 或 system_error 的独立 Agent 视图。
 * @throws HTTP、网络、JSON 或 DTO/身份校验失败时抛出，且不会自动重发。
 */
export async function createAgentRun(
  documentId: string,
  query: string,
  signal: AbortSignal,
  fetchImpl: AgentFetch = fetch,
): Promise<AgentTerminalView> {
  const response = await fetchImpl('/api/agent/runs', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    signal,
    body: JSON.stringify({
      document_id: documentId,
      query,
    }),
  })
  if (!response.ok) {
    throw new Error('Agent Run 请求失败')
  }

  const parsed = parseAgentRunResponse(await response.json(), { documentId })
  return buildAgentResultView(parsed)
}
