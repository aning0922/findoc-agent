/** RAG 六事件流最终可展示的有限页面状态。 */
export type ChatViewStatus =
  | 'idle'
  | 'streaming'
  | 'success'
  | 'refusal'
  | 'error'

/** RAG 成功展示允许保留的引用字段。 */
export interface CitationView {
  number: number
  source_file: string
  page: number
  chunk_id: string
}

/**
 * RAG 页面的一次可信展示状态。
 *
 * 输入：由流事件暂存值经 buildChatTerminalView 校验后构造。
 * 输出：供 React 区分等待、成功、拒答和错误。
 * 边界：非 success 状态必须清空答案和引用，避免旧结果残留。
 */
export interface ChatViewState {
  status: ChatViewStatus
  answer: string | null
  citations: CitationView[]
  refusalReason: string | null
  errorMessage: string | null
}

/** RAG 页面没有活动结果时使用的初始状态。 */
export const INITIAL_CHAT_VIEW: ChatViewState = {
  status: 'idle',
  answer: null,
  citations: [],
  refusalReason: null,
  errorMessage: null,
}

/** RAG done 事件允许的三种既有终态。 */
export type RagDoneOutcome = 'success' | 'refusal' | 'error'

/**
 * 六事件流完成后用于一次性判断终态的暂存输入。
 *
 * 输入：同一请求消费 SSE 时收集的答案、引用、拒答、错误和 done。
 * 输出：传给 buildChatTerminalView 的纯数据。
 * 边界：暂存字段存在不表示可以展示，必须与唯一 done 终态匹配。
 */
export interface RagTerminalParts {
  answer: string | null
  citations: readonly CitationView[]
  refusalReason: string | null
  errorMessage: string | null
  doneOutcome: RagDoneOutcome | null
}

/**
 * 验证并复制单条 RAG 引用的公开字段。
 *
 * @param value - 从 citation SSE 事件读取的未经信任对象。
 * @returns number/page 为正整数且字符串字段非空的引用。
 * @throws 字段类型或值非法时抛出 Error，阻止流进入 success。
 */
export function parseCitationView(value: Record<string, unknown>): CitationView {
  if (
    !Number.isSafeInteger(value.number)
    || (value.number as number) <= 0
    || typeof value.source_file !== 'string'
    || value.source_file.trim().length === 0
    || !Number.isSafeInteger(value.page)
    || (value.page as number) <= 0
    || typeof value.chunk_id !== 'string'
    || value.chunk_id.trim().length === 0
  ) {
    throw new Error('citation 字段非法')
  }

  return {
    number: value.number as number,
    source_file: value.source_file,
    page: value.page as number,
    chunk_id: value.chunk_id,
  }
}

/**
 * 将同一 RAG 请求的流暂存值提交为唯一可信页面终态。
 *
 * @param parts - 流消费完成后的本地暂存值。
 * @returns 与 done 匹配且清除了其他分支字段的页面状态。
 * @throws 成功缺正文/合法引用或任一终态内容不匹配时抛出 Error。
 */
export function buildChatTerminalView(parts: RagTerminalParts): ChatViewState {
  if (parts.doneOutcome === 'success') {
    if (parts.answer === null || parts.answer.trim().length === 0) {
      throw new Error('成功终态缺少非空 final_answer')
    }
    if (parts.citations.length === 0) {
      throw new Error('成功终态缺少合法引用')
    }
    return {
      status: 'success',
      answer: parts.answer,
      citations: [...parts.citations],
      refusalReason: null,
      errorMessage: null,
    }
  }

  if (parts.doneOutcome === 'refusal') {
    if (parts.refusalReason === null || parts.refusalReason.trim().length === 0) {
      throw new Error('拒答终态缺少非空 reason')
    }
    return {
      status: 'refusal',
      answer: null,
      citations: [],
      refusalReason: parts.refusalReason,
      errorMessage: null,
    }
  }

  if (parts.doneOutcome === 'error') {
    if (parts.errorMessage === null || parts.errorMessage.trim().length === 0) {
      throw new Error('错误终态缺少非空安全消息')
    }
    return {
      status: 'error',
      answer: null,
      citations: [],
      refusalReason: null,
      errorMessage: parts.errorMessage,
    }
  }

  throw new Error('SSE 终态与事件内容不匹配')
}
