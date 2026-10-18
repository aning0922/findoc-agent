/**
 * 保存一次前端请求的不可变提交快照。
 *
 * 输入：本地唯一请求号、提交时的文档身份和已清理问题。
 * 输出：供请求体、失效判断和迟到回调校验复用的快照。
 * 边界：requestId 只代表客户端请求身份，不等同于服务端 Agent run_id。
 */
export interface RequestIdentity {
  requestId: number
  documentId: string
}

export interface RequestSnapshot extends RequestIdentity {
  query: string
}

/**
 * 已知 Run 的历史读取身份；刻意不包含创建任务才有的 query。
 *
 * 输入：本地读取序号、已确认的 Run 与所属文档身份。
 * 输出：供 GET 结果、Events 和迟到回调共同核对的不可变快照。
 * 边界：它不是创建请求，不能拿当前表单问题补成一个假 query。
 */
export interface AgentHistoryRequestSnapshot extends RequestIdentity {
  runId: string
}

/**
 * 页面判断文档可否继续承载当前请求所需的最小字段。
 *
 * 输入：文档身份和当前状态。
 * 输出：由调用方组合成列表后判断请求文档是否仍 ready。
 * 边界：这里只判断前端当前列表，不替代服务端的文档范围与状态校验。
 */
export interface RequestDocumentState {
  document_id: string
  status: string
}

/**
 * 建立一次请求快照并拒绝非法本地身份或空提交字段。
 *
 * @param requestId - 前端单调生成的正整数请求号。
 * @param documentId - 提交时的文档 ID。
 * @param query - 提交时已经 trim 的问题。
 * @returns 可安全保存在活动请求引用中的不可变快照。
 * @throws 任一字段不符合最小请求身份合同时抛出 Error。
 */
export function createRequestSnapshot(
  requestId: number,
  documentId: string,
  query: string,
): RequestSnapshot {
  if (!Number.isSafeInteger(requestId) || requestId <= 0) {
    throw new Error('请求号必须是正安全整数')
  }
  if (documentId.trim().length === 0) {
    throw new Error('请求文档 ID 不能为空')
  }
  if (query.trim().length === 0) {
    throw new Error('请求问题不能为空')
  }
  return Object.freeze({ requestId, documentId, query })
}

/** 建立一次已知 Run GET 的独立身份；不要求文档仍在 ready 列表。 */
export function createAgentHistoryRequestSnapshot(
  requestId: number,
  runId: string,
  documentId: string,
): AgentHistoryRequestSnapshot {
  if (!Number.isSafeInteger(requestId) || requestId <= 0) {
    throw new Error('历史读取请求号必须是正安全整数')
  }
  if (runId.trim().length === 0 || documentId.trim().length === 0) {
    throw new Error('历史读取的 Run 和文档身份不能为空')
  }
  return Object.freeze({ requestId, runId, documentId })
}

/**
 * 判断提交入口能否占有新的活动请求。
 *
 * @param activeRequest - 同步引用中当前保存的请求快照。
 * @returns 没有活动请求时返回 true，否则拒绝重复提交。
 * @remarks 该入口判断立即生效，不能仅依赖下一次 React 渲染后的按钮禁用。
 */
export function canStartRequest(activeRequest: RequestIdentity | null): boolean {
  return activeRequest === null
}

/**
 * 判断文档选择入口能否切换到另一篇 ready 文档。
 *
 * @param activeRequest - 同步引用中当前保存的请求快照。
 * @returns 没有活动请求时返回 true，pending 时返回 false。
 * @remarks 单选框禁用只提供 UI 防线；事件入口仍必须调用本守卫。
 */
export function canChangeDocument(activeRequest: RequestIdentity | null): boolean {
  return activeRequest === null
}

/**
 * 合并两个产品模式的活动请求，形成共享入口唯一看到的请求身份。
 *
 * @param first - 第一个模式当前占有的请求，通常是 RAG。
 * @param second - 第二个模式当前占有的请求，通常是 Agent。
 * @returns 唯一活动请求；两个模式都空闲时返回 null。
 * @throws 两个模式同时有请求时抛出，暴露首版不允许的并发状态。
 */
export function resolveActiveRequest(
  ...requests: Array<RequestIdentity | null>
): RequestIdentity | null {
  const activeRequests = requests.filter(
    (request): request is RequestIdentity => request !== null,
  )
  if (activeRequests.length > 1) {
    throw new Error('首版同一时间只能有一个活动请求')
  }
  return activeRequests[0] ?? null
}

/**
 * 判断一个回调是否仍拥有当前活动请求。
 *
 * @param activeRequest - 页面此刻认可的活动请求，null 表示没有 pending。
 * @param candidate - 正在执行回调的原提交快照。
 * @returns 请求号和文档身份都匹配时返回 true。
 * @remarks 文档和问题相同也不能替代请求号；失效或组件清理后返回 false。
 */
export function isCurrentRequest(
  activeRequest: RequestSnapshot | null,
  candidate: RequestSnapshot,
): boolean {
  return activeRequest?.requestId === candidate.requestId
    && activeRequest.documentId === candidate.documentId
}

/**
 * 判断 GET/Events 回调是否仍属于当前历史读取。
 *
 * Run、文档和本地请求号均需一致，防止旧 Run 的事件附到新结果。
 */
export function isCurrentAgentHistoryRequest(
  activeRequest: AgentHistoryRequestSnapshot | null,
  candidate: AgentHistoryRequestSnapshot,
): boolean {
  return activeRequest?.requestId === candidate.requestId
    && activeRequest.runId === candidate.runId
    && activeRequest.documentId === candidate.documentId
}

/**
 * 判断提交快照中的文档在最新列表里是否仍可用。
 *
 * @param documents - 最新可信文档列表的最小状态投影。
 * @param request - 要核对的提交快照。
 * @returns 同一 document_id 仍存在且状态为 ready 时返回 true。
 * @remarks 文档消失、身份变化或非 ready 都会使本次请求失效。
 */
export function isRequestDocumentReady(
  documents: readonly RequestDocumentState[],
  request: RequestSnapshot,
): boolean {
  return documents.some(
    (document) =>
      document.document_id === request.documentId
      && document.status === 'ready',
  )
}
