import { consumeSSEStream } from './sse'
import {
  buildChatTerminalView,
  INITIAL_CHAT_VIEW,
  parseCitationView,
  type ChatViewState,
  type CitationView,
  type RagDoneOutcome,
} from './ragResult'
import {
  canChangeDocument,
  canStartRequest,
  createAgentHistoryRequestSnapshot,
  createRequestSnapshot,
  isCurrentAgentHistoryRequest,
  isCurrentRequest,
  isRequestDocumentReady,
  resolveActiveRequest,
  type AgentHistoryRequestSnapshot,
  type RequestIdentity,
  type RequestSnapshot,
} from './requestOwnership'
import {
  buildAgentPendingView,
  buildAgentRequestErrorView,
  INITIAL_AGENT_VIEW,
  type AgentViewState,
} from './agentResult'
import {
  AGENT_METRICS,
  buildAgentQuery,
  createAgentRun,
  type AgentMetric,
} from './agentRequest'
import {
  describeAgentHistoryError,
  readAgentEvents,
  readAgentRun,
  type AgentHistoryEvent,
} from './agentHistory.ts'
import {
  clearAgentRunIndex,
  readAgentRunIndex,
  rememberAgentRun,
  removeAgentRun,
  type AgentRunIndexStorage,
  type AgentRunReference,
} from './agentRunIndex.ts'
import type { ChangeEvent } from 'react'
import { useEffect, useRef, useState } from 'react'

type DocumentStatus =
  | 'queued'
  | 'parsing'
  | 'indexing'
  | 'ready'
  | 'failed'

type FailureStage = 'queued' | 'parsing' | 'indexing'

interface DocumentRecord {
  document_id: string
  source_file: string
  status: DocumentStatus
  failed_stage: FailureStage | null
  error_code: string | null
  safe_error_message: string | null
  created_at: string
  updated_at: string
}

/**
 * 保存当前 RAG 请求的快照和客户端取消手柄。
 *
 * 输入：提交入口同步创建的 RequestSnapshot 与 AbortController。
 * 输出：供入口、列表失效、回调和组件清理核对同一次请求。
 * 边界：abort 只停止客户端等待，不证明后端执行已经取消。
 */
interface ActiveChatRequest {
  snapshot: RequestSnapshot
  controller: AbortController
}

/** Agent 请求使用独立活动身份；结构共享但不会写入 RAG 展示状态。 */
interface ActiveAgentRequest {
  snapshot: RequestSnapshot
  controller: AbortController
}

/** 已知 Run GET 使用不带 query 的独立活动身份，不受当前 ready 选择冒充授权。 */
interface ActiveAgentHistoryRequest {
  snapshot: AgentHistoryRequestSnapshot
  controller: AbortController
}

type AgentResultOrigin = 'created' | 'history'

type AgentHistoryReadState =
  | { status: 'idle' }
  | { status: 'loading'; reference: AgentRunReference }
  | { status: 'ready'; reference: AgentRunReference }
  | { status: 'error'; reference: AgentRunReference; message: string }

type AgentEventsViewState =
  | { status: 'idle' }
  | { status: 'loading'; runId: string }
  | { status: 'ready'; runId: string; events: AgentHistoryEvent[] }
  | { status: 'error'; runId: string; message: string }

type WorkbenchMode = 'rag' | 'agent'

/** 访问 localStorage 可能被浏览器策略拒绝；失败时历史功能降级但结果仍可显示。 */
function getAgentRunStorage(): AgentRunIndexStorage | null {
  try {
    return window.localStorage
  } catch {
    return null
  }
}

/**
 * 确认 SSE data 是可以按字段读取的普通 JSON 对象。
 *
 * @param data - JSON.parse 返回的未经信任数据。
 * @returns 可以通过字符串键读取的普通对象。
 * @throws data 不是对象、为 null 或为数组时抛出 Error。
 */
function requireDataObject(data: unknown): Record<string, unknown> {
  if (typeof data !== "object" || data === null || Array.isArray(data)) {
    throw new Error('SSE data 必须是 JSON 对象')
  }
  return data as Record<string, unknown>
}

/**
 * 展示 PDF 上传、共享文档选择、RAG 问答和有限 Agent 任务的单页工作台。
 *
 * @returns 包含两种独立请求模式、可信终态、引用和安全错误的 React 页面。
 * @remarks RAG 消费 SSE；Agent 等待同步 JSON，二者共享文档但不混用展示状态。
 */
function App({ embedded = false }: { embedded?: boolean }) {
  const Container = embedded ? 'section' : 'main'
  // 保存后端返回的文档列表
  const [documents, setDocuments] = useState<DocumentRecord[]>([])
  // 同步保存最新列表，供异步回调在 React 重渲染之外判断文档是否仍 ready
  const documentsRef = useRef<DocumentRecord[]>([])
  // 表示文档列表请求是否仍在进行，用于控制加载提示和按钮
  const [isLoadingDocuments, setIsLoadingDocuments] = useState(true)
  // 保存可以展示给用户的安全错误消息，null 表示当前没有错误
  const [documentError, setDocumentError] = useState<string | null>(null)
  // 保存用户当前选择的 ready 文档身份；null 表示尚未选择
  const [selectedDocumentId, setSelectedDocumentId] = useState<string | null>(null)
  // 同步保存当前选择，供列表响应立即清理已经失效的文档归属
  const selectedDocumentIdRef = useRef<string | null>(null)
  // 保存用户从文件选择框中选中的 PDF；null 表示尚未选中
  const [selectedFile, setSelectedFile] = useState<File | null>(null)

  // 表示 PDF 上传请求是否正在进行，用于防止重复提交
  const [isUploading, setIsUploading] = useState(false)
  // 保存可以展示给用户的安全上传错误；null 表示当前没有错误
  const [uploadError, setUploadError] = useState<string | null>(null)
  // 保存上传请求成功后的业务提示；null 表示当前没有提示
  const [uploadMessage, setUploadMessage] = useState<string | null>(null)
  // 保存用户针对当前 ready 文档输入的问题；空字符串表示尚未输入
  const [query, setQuery] = useState('')
  // 保存一次聊天请求当前可展示的可信页面状态
  const [chatView, setChatView] = useState<ChatViewState>(INITIAL_CHAT_VIEW)
  // 同步保存唯一活动请求，防止重渲染前重复提交并拒绝所有迟到回调
  const activeChatRequestRef = useRef<ActiveChatRequest | null>(null)
  // 为每次 RAG 提交分配本地唯一身份；不使用后端不存在的 run_id
  const nextChatRequestIdRef = useRef(1)
  // 保存当前工作区入口；任一请求 pending 时不允许跨模式切换
  const [workbenchMode, setWorkbenchMode] = useState<WorkbenchMode>('rag')
  // 保存 Agent 的四位 ASCII 年份输入；合法性在提交前完整核对
  const [agentYear, setAgentYear] = useState('2025')
  // 保存 Agent 首版三个固定指标之一
  const [agentMetric, setAgentMetric] = useState<AgentMetric>('营业收入')
  // 保存独立 Agent 页面状态，绝不借用 RAG 的 streaming/success 状态
  const [agentView, setAgentView] = useState<AgentViewState>(INITIAL_AGENT_VIEW)
  // 同步保存唯一 Agent 请求，供入口和迟到回调立即核对
  const activeAgentRequestRef = useRef<ActiveAgentRequest | null>(null)
  // 为 Agent POST 分配本地请求身份；它与服务端 run_id 不同
  const nextAgentRequestIdRef = useRef(1)
  // 保存最近一次实际提交的有限任务，避免结果被后续表单编辑改写含义
  const [submittedAgentQuery, setSubmittedAgentQuery] = useState<string | null>(null)
  // 区分当前结果来自创建还是历史 GET，避免文档列表刷新误撤下历史结果
  const agentResultOriginRef = useRef<AgentResultOrigin | null>(null)
  // 保存 GET/Events 的独立活动身份和取消手柄，不制造假 query
  const activeAgentHistoryRequestRef = useRef<ActiveAgentHistoryRequest | null>(null)
  const nextAgentHistoryRequestIdRef = useRef(1)
  const [agentHistoryRead, setAgentHistoryRead] = useState<AgentHistoryReadState>({ status: 'idle' })
  const [agentEventsView, setAgentEventsView] = useState<AgentEventsViewState>({ status: 'idle' })
  const [runIndexState, setRunIndexState] = useState(() => readAgentRunIndex(getAgentRunStorage()))
  const runReferencesRef = useRef<AgentRunReference[]>(runIndexState.references)
  const [runIndexNotice, setRunIndexNotice] = useState<string | null>(() => {
    if (runIndexState.issue === 'invalid') {
      return '已忽略本机索引中损坏、超限或不支持的记录。'
    }
    if (runIndexState.issue === 'unavailable') {
      return '本机历史索引不可用；已取得的结果仍可在当前页面查看。'
    }
    return null
  })

  /** 返回当前任一模式占有的请求快照，供共享入口阻止并发。 */
  function getActiveRequestSnapshot(): RequestIdentity | null {
    return resolveActiveRequest(
      activeChatRequestRef.current?.snapshot ?? null,
      activeAgentRequestRef.current?.snapshot ?? null,
      activeAgentHistoryRequestRef.current?.snapshot ?? null,
    )
  }

  /** 把已验证 Run 置于本机索引首位；写入失败不撤下页面结果。 */
  function rememberConfirmedRun(reference: AgentRunReference): void {
    const saved = rememberAgentRun(
      getAgentRunStorage(),
      runReferencesRef.current,
      reference,
    )
    runReferencesRef.current = saved.references
    setRunIndexState({ references: saved.references, issue: saved.persisted ? 'none' : 'unavailable' })
    if (!saved.persisted) {
      setRunIndexNotice('本机历史索引写入失败；已验证结果仍然保留。')
    }
  }

  /**
   * 应用最新文档列表并立即作废已经失去 ready 的页面归属。
   *
   * @param nextDocuments - 文档接口刚返回的最新列表。
   * @returns void；同步引用和 React 状态一起更新。
   * @remarks 文档失效会先撤销客户端等待；迟到回调因请求身份不匹配而静默丢弃。
   */
  function applyDocumentList(nextDocuments: DocumentRecord[]): void {
    documentsRef.current = nextDocuments
    setDocuments(nextDocuments)

    const activeRequest = activeChatRequestRef.current
    const activeRequestInvalid = activeRequest !== null
      && !isRequestDocumentReady(nextDocuments, activeRequest.snapshot)
    if (activeRequestInvalid) {
      activeChatRequestRef.current = null
      activeRequest.controller.abort()
      setChatView({
        status: 'error',
        answer: null,
        citations: [],
        refusalReason: null,
        errorMessage: '所选文档已不可用，请重新选择后提问',
      })
    }

    const activeAgentRequest = activeAgentRequestRef.current
    const activeAgentRequestInvalid = activeAgentRequest !== null
      && !isRequestDocumentReady(nextDocuments, activeAgentRequest.snapshot)
    if (activeAgentRequestInvalid) {
      activeAgentRequestRef.current = null
      activeAgentRequest.controller.abort()
      setAgentView(buildAgentRequestErrorView(
        '所选文档已不可用，本次 Agent 结果已撤下，请重新选择后提交',
      ))
    }

    const selectedId = selectedDocumentIdRef.current
    const selectedDocumentStillReady = selectedId !== null
      && nextDocuments.some(
        (document) =>
          document.document_id === selectedId && document.status === 'ready',
      )
    if (selectedId !== null && !selectedDocumentStillReady) {
      selectedDocumentIdRef.current = null
      setSelectedDocumentId(null)
      if (!activeRequestInvalid) {
        setChatView(INITIAL_CHAT_VIEW)
      }
      if (!activeAgentRequestInvalid && agentResultOriginRef.current !== 'history') {
        agentResultOriginRef.current = null
        setAgentView(INITIAL_AGENT_VIEW)
        setSubmittedAgentQuery(null)
        setAgentEventsView({ status: 'idle' })
      }
    }
  }

  /**
   * 从后端加载固定 workspace 的文档列表
   *
   * 输入：无
   * 输出：Promise<void>，数据通过 React 状态保存，不直接返回
   * 失败：网络异常或非 2xx 响应时保存安全错误信息
   */
  async function loadDocuments(): Promise<void> {
    try {
      const response = await fetch(`/api/documents`)
      if (!response.ok) {
        throw new Error('Failed to load documents')
      }
      const data = (await response.json()) as DocumentRecord[]
      setDocumentError(null)
      applyDocumentList(data)
    }
    catch {
      setDocumentError('无法加载文档，请稍后重试')
    } finally {
      setIsLoadingDocuments(false)
    }
  }
  /**
   * 响应用户的重新加载操作，并恢复请求前的页面状态
   *
   * 输入：无
   * 输出：void 请求由 loadDocuments 异步执行
   * 失败：具体失败状态由 loadDocuments 统一处理
   */
  function handleReloadDocuments(): void {
    setIsLoadingDocuments(true)
    setDocumentError(null)
    void loadDocuments()
  }

  /**
   * 读取文件输入框当前选中的第一个文件并保存到 React 状态
   *
   * @param event - 文件输入框产生的 change 事件
   * @returns void 选中的 File 通过 React 保存
   * 边界：用户取消选择或文件列表为空时保存 null
   */
  function handleFileChange(event: ChangeEvent<HTMLInputElement>): void {
    const file = event.currentTarget.files?.[0] ?? null
    setSelectedFile(file)
  }

  /**
   * 把用户选中的 PDF 作为 multipart/form-data 请求提交到后端
   *
   * 输入：无，文件从 selectedFile 状态读取
   * 输出：Promise<void>，成功后刷新文档列表并更新可见提示
   * 失败：未选择文件，网络异常或非 2xx 响应时保存安全错误
   */
  async function uploadSelectedDocument(): Promise<void> {
    if (selectedFile === null) {
      setUploadError("请先选择 PDF 文件")
      return
    }

    setIsUploading(true)
    setUploadError(null)
    setUploadMessage(null)

    try {
      const formData = new FormData()
      formData.append('file', selectedFile)
      const response = await fetch('/api/documents', {
        method: 'POST',
        body: formData
      })
      if (!response.ok) {
        throw new Error('Failed to upload document')
      }
      setUploadMessage('上传已提交，等待处理')
      await loadDocuments()
    }
    catch {
      setUploadError('上传失败，请稍后重试')
    } finally {
      setIsUploading(false)
    }
  }


  /**
   * 把聊天文本框的最新内容保存到 React 状态
   *
   * @param event - textarea 产生的 change 事件
   * 输出：void，问题文本通过 React 状态保存
   * 边界：允许用户编辑为空字符串，提交时再禁止空问题
   */
  function handleQueryChange(event: ChangeEvent<HTMLTextAreaElement>): void {
    setQuery(event.currentTarget.value)
  }

  /**
   * 在没有活动请求时切换 ready 文档并撤下前一文档结果。
   *
   * @param documentId - 用户尝试选择的文档 ID。
   * @returns void；合法选择写入同步引用和 React 状态。
   * @remarks pending 或最新列表中非 ready 的选择会在处理入口直接拒绝。
   */
  function handleDocumentSelection(documentId: string): void {
    if (!canChangeDocument(getActiveRequestSnapshot())) {
      return
    }
    const documentIsReady = documentsRef.current.some(
      (document) =>
        document.document_id === documentId && document.status === 'ready',
    )
    if (!documentIsReady) {
      return
    }

    selectedDocumentIdRef.current = documentId
    setSelectedDocumentId(documentId)
    setChatView(INITIAL_CHAT_VIEW)
    setAgentView(INITIAL_AGENT_VIEW)
    agentResultOriginRef.current = null
    setSubmittedAgentQuery(null)
    setAgentHistoryRead({ status: 'idle' })
    setAgentEventsView({ status: 'idle' })
  }


  useEffect(() => {
    // 初次挂载需要同步外部文档服务；状态只会在等待网络响应后更新
    // oxlint-disable-next-line react/set-state-in-effect
    void loadDocuments()
    return () => {
      const activeRequest = activeChatRequestRef.current
      activeChatRequestRef.current = null
      activeRequest?.controller.abort()
      const activeAgentRequest = activeAgentRequestRef.current
      activeAgentRequestRef.current = null
      activeAgentRequest?.controller.abort()
      const activeHistoryRequest = activeAgentHistoryRequestRef.current
      activeAgentHistoryRequestRef.current = null
      activeHistoryRequest?.controller.abort()
    }
  }, [])

  useEffect(() => {
    // 只有存在处理中且列表请求正常的文档时，才安排下一次刷新
    const hasProcessingDocuments = documents.some(
      (document) =>
        document.status === 'queued' ||
        document.status === 'parsing' ||
        document.status === 'indexing',
    )

    if (!hasProcessingDocuments || documentError !== null) {
      return
    }

    // 使用一次性定时器，避免上一轮请求未完成时启动下一轮
    const timerId = window.setTimeout(() => {
      void loadDocuments()
    }, 1500)

    return () => {
      window.clearTimeout(timerId)
    }
  }, [documents, documentError])

  const selectedReadyDocument =
    documents.find(
      (document) =>
        document.document_id === selectedDocumentId && document.status === 'ready'
    ) ?? null
  const requestIsPending = chatView.status === 'streaming'
    || agentView.status === 'pending'
    || agentHistoryRead.status === 'loading'
    || agentEventsView.status === 'loading'
  const agentYearIsValid = /^[0-9]{4}$/.test(agentYear)
  const agentQueryPreview = agentYearIsValid
    ? buildAgentQuery(agentYear, agentMetric)
    : null
  const agentViewDocumentId = agentView.status === 'pending'
    || agentView.status === 'answered'
    || agentView.status === 'refusal'
    || agentView.status === 'system_error'
    ? agentView.documentId
    : null
  const agentViewDocumentName = agentViewDocumentId === null
    ? null
    : documents.find((document) => document.document_id === agentViewDocumentId)?.source_file
      ?? agentViewDocumentId
  const displayedAgentRunId = agentView.status === 'answered'
    || agentView.status === 'refusal'
    || agentView.status === 'system_error'
    ? agentView.runId
    : null

  /**
   * 在没有活动请求时切换 RAG 或 Agent 工作区。
   *
   * @param mode - 用户选择的工作区入口。
   * @returns void；pending 时入口守卫拒绝跨模式绕过并发限制。
   */
  function handleWorkbenchMode(mode: WorkbenchMode): void {
    if (!canChangeDocument(getActiveRequestSnapshot())) {
      return
    }
    setWorkbenchMode(mode)
  }

  /** 保存 Agent 年份原始输入；提交按钮只在四位 ASCII 数字时可用。 */
  function handleAgentYearChange(event: ChangeEvent<HTMLInputElement>): void {
    setAgentYear(event.currentTarget.value)
  }

  /** 保存固定指标选择；DOM 选项之外的值不会进入任务构造。 */
  function handleAgentMetricChange(event: ChangeEvent<HTMLSelectElement>): void {
    const metric = event.currentTarget.value as AgentMetric
    if (AGENT_METRICS.includes(metric)) {
      setAgentMetric(metric)
    }
  }

  /**
   * 用已确认的 Run/document 身份读取服务端结果与安全历史。
   *
   * 结果 GET 成功后才展示；Events 失败只影响历史区域，且全程不会发送 POST。
   */
  async function loadKnownAgentRun(reference: AgentRunReference): Promise<void> {
    if (!canStartRequest(getActiveRequestSnapshot())) {
      return
    }

    const snapshot = createAgentHistoryRequestSnapshot(
      nextAgentHistoryRequestIdRef.current,
      reference.runId,
      reference.documentId,
    )
    nextAgentHistoryRequestIdRef.current += 1
    const controller = new AbortController()
    activeAgentHistoryRequestRef.current = { snapshot, controller }
    agentResultOriginRef.current = 'history'
    setWorkbenchMode('agent')
    setSubmittedAgentQuery(null)
    setAgentView(INITIAL_AGENT_VIEW)
    setAgentHistoryRead({ status: 'loading', reference })
    setAgentEventsView({ status: 'idle' })

    try {
      const terminalView = await readAgentRun(reference, controller.signal)
      if (!isCurrentAgentHistoryRequest(activeAgentHistoryRequestRef.current?.snapshot ?? null, snapshot)) {
        return
      }
      setAgentView(terminalView)
      setAgentHistoryRead({ status: 'ready', reference })
      rememberConfirmedRun(reference)

      setAgentEventsView({ status: 'loading', runId: reference.runId })
      try {
        const events = await readAgentEvents(reference, controller.signal)
        if (!isCurrentAgentHistoryRequest(activeAgentHistoryRequestRef.current?.snapshot ?? null, snapshot)) {
          return
        }
        setAgentEventsView({ status: 'ready', runId: reference.runId, events })
      } catch {
        if (!isCurrentAgentHistoryRequest(activeAgentHistoryRequestRef.current?.snapshot ?? null, snapshot)) {
          return
        }
        setAgentEventsView({
          status: 'error',
          runId: reference.runId,
          message: '历史事件暂时无法读取；已验证结果仍然保留。',
        })
      }
    } catch (error) {
      if (!isCurrentAgentHistoryRequest(activeAgentHistoryRequestRef.current?.snapshot ?? null, snapshot)) {
        return
      }
      agentResultOriginRef.current = null
      setAgentView(INITIAL_AGENT_VIEW)
      setAgentHistoryRead({
        status: 'error',
        reference,
        message: describeAgentHistoryError(error),
      })
    } finally {
      if (isCurrentAgentHistoryRequest(activeAgentHistoryRequestRef.current?.snapshot ?? null, snapshot)) {
        activeAgentHistoryRequestRef.current = null
      }
    }
  }

  useEffect(() => {
    const mostRecentRun = runReferencesRef.current[0]
    if (mostRecentRun !== undefined) {
      // oxlint-disable-next-line react/set-state-in-effect -- 刷新恢复必须在挂载后启动外部 GET。
      void loadKnownAgentRun(mostRecentRun)
    }
  }, [])

  /** 移除一条本机查找引用；服务端 Run 和当前已验证结果都不会被删除。 */
  function handleRemoveRunReference(runId: string): void {
    if (!canStartRequest(getActiveRequestSnapshot())) {
      return
    }
    const saved = removeAgentRun(getAgentRunStorage(), runReferencesRef.current, runId)
    runReferencesRef.current = saved.references
    setRunIndexState({ references: saved.references, issue: saved.persisted ? 'none' : 'unavailable' })
    setRunIndexNotice(saved.persisted
      ? '已移除本机引用；服务端 Run 和当前显示结果未被删除。'
      : '本机索引更新失败；服务端 Run 和当前显示结果未被删除。')
  }

  /** 清除本应用唯一索引键，不清空同源其他应用数据或删除服务端 Run。 */
  function handleClearRunIndex(): void {
    if (!canStartRequest(getActiveRequestSnapshot())) {
      return
    }
    const cleared = clearAgentRunIndex(getAgentRunStorage())
    runReferencesRef.current = []
    setRunIndexState({ references: [], issue: cleared ? 'none' : 'unavailable' })
    setRunIndexNotice(cleared
      ? '已清除此浏览器中的 FinDoc Run 引用；服务端 Run 未被删除。'
      : '无法清除本机索引；服务端 Run 和当前显示结果未受影响。')
  }

  /**
   * 向当前 ready 文档提交问题并消费可信 SSE 终态
   *
   * 输入：同步文档选择、最新文档列表、query 和活动请求引用
   * 输出：Promise<void>，最终结果通过 chatView 展示
   * 失败：HTTP 错误，流中断，字段非法或终态不匹配时显示安全错误
   */
  async function submitQuestion(): Promise<void> {
    if (!canStartRequest(getActiveRequestSnapshot())) {
      return
    }

    const trimmedQuery = query.trim()
    const selectedId = selectedDocumentIdRef.current
    if (
      selectedId === null
      || trimmedQuery.length === 0
      || !documentsRef.current.some(
        (document) =>
          document.document_id === selectedId && document.status === 'ready',
      )
    ) {
      return
    }

    const requestSnapshot = createRequestSnapshot(
      nextChatRequestIdRef.current,
      selectedId,
      trimmedQuery,
    )
    nextChatRequestIdRef.current += 1
    const controller = new AbortController()
    activeChatRequestRef.current = { snapshot: requestSnapshot, controller }
    setChatView({ ...INITIAL_CHAT_VIEW, status: 'streaming' })

    let streamedAnswer: string | null = null
    const streamedCitations: CitationView[] = []
    let refusalReason: string | null = null
    let safeErrorMessage: string | null = null
    let doneOutcome: RagDoneOutcome | null = null

    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        signal: controller.signal,
        body: JSON.stringify({
          document_id: requestSnapshot.documentId,
          query: requestSnapshot.query,
        })
      })
      if (!response.ok) {
        throw new Error('无法开始聊天请求')
      }
      if (response.body === null) {
        throw new Error('聊天响应缺少可读流')
      }

      await consumeSSEStream(response.body, (event) => {
        const data = requireDataObject(event.data)

        switch (event.event) {
          case 'status':
            // 读取 refused 的 reason
            if (data.phase === 'refused') {
              if (typeof data.reason !== 'string') {
                throw new Error('refused 状态缺少 reason')
              }
              refusalReason = data.reason
            }
            break

          case 'final_answer':
            // 验证并保存 content
            if (typeof data.content !== 'string') {
              throw new Error('final_answer 缺少 content')
            }
            streamedAnswer = data.content
            break

          case 'citation':
            // 正整数与非空来源字段不合法时立即使本次流失败
            streamedCitations.push(parseCitationView(data))
            break

          case 'usage':
            // 当前没有真实 usage 展示需求
            break

          case 'error':
            // 验证并保存安全 message 不存在 raw_error 字段
            if (typeof data.code !== 'string' || typeof data.message !== 'string') {
              throw new Error('error 事件字段非法')
            }
            safeErrorMessage = data.message
            break

          case 'done':
            //验证并保存 success/refusal/error outcome
            if (data.outcome !== 'success' && data.outcome !== 'refusal' && data.outcome !== 'error') {
              throw new Error('done outcome 非法')
            }
            doneOutcome = data.outcome
            break
        }
      })
      const terminalView = buildChatTerminalView({
        answer: streamedAnswer,
        citations: streamedCitations,
        refusalReason,
        errorMessage: safeErrorMessage,
        doneOutcome,
      })
      if (!isCurrentRequest(activeChatRequestRef.current?.snapshot ?? null, requestSnapshot)) {
        return
      }
      if (!isRequestDocumentReady(documentsRef.current, requestSnapshot)) {
        activeChatRequestRef.current = null
        controller.abort()
        setChatView({
          status: 'error',
          answer: null,
          citations: [],
          refusalReason: null,
          errorMessage: '所选文档已不可用，请重新选择后提问',
        })
        return
      }
      setChatView(terminalView)
    } catch {
      if (!isCurrentRequest(activeChatRequestRef.current?.snapshot ?? null, requestSnapshot)) {
        return
      }
      setChatView({
        status: 'error',
        answer: null,
        citations: [],
        refusalReason: null,
        errorMessage: '问答失败或响应流未完整结束',
      })
    } finally {
      if (isCurrentRequest(activeChatRequestRef.current?.snapshot ?? null, requestSnapshot)) {
        activeChatRequestRef.current = null
      }
    }
  }

  /**
   * 用当前 ready 文档和受控表单创建一个同步 Agent Run。
   *
   * 输入：共享文档选择、四位年份、固定指标和独立活动请求引用。
   * 输出：严格 DTO 转换后的 Agent 三态通过 agentView 展示。
   * 失败：HTTP、断网或响应不可信时只显示 request_error，不自动重发 POST。
   */
  async function submitAgentTask(): Promise<void> {
    if (!canStartRequest(getActiveRequestSnapshot())) {
      return
    }

    const selectedId = selectedDocumentIdRef.current
    if (
      selectedId === null
      || !documentsRef.current.some(
        (document) =>
          document.document_id === selectedId && document.status === 'ready',
      )
    ) {
      return
    }

    let taskQuery: string
    try {
      taskQuery = buildAgentQuery(agentYear, agentMetric)
    } catch {
      setAgentView(buildAgentRequestErrorView(
        '年份必须是四位数字，指标必须来自当前三个固定选项',
      ))
      return
    }

    const requestSnapshot = createRequestSnapshot(
      nextAgentRequestIdRef.current,
      selectedId,
      taskQuery,
    )
    nextAgentRequestIdRef.current += 1
    const controller = new AbortController()
    activeAgentRequestRef.current = { snapshot: requestSnapshot, controller }
    agentResultOriginRef.current = 'created'
    setSubmittedAgentQuery(taskQuery)
    setAgentView(buildAgentPendingView(requestSnapshot.requestId, selectedId))
    setAgentHistoryRead({ status: 'idle' })
    setAgentEventsView({ status: 'idle' })

    try {
      const terminalView = await createAgentRun(
        requestSnapshot.documentId,
        requestSnapshot.query,
        controller.signal,
      )
      if (!isCurrentRequest(activeAgentRequestRef.current?.snapshot ?? null, requestSnapshot)) {
        return
      }
      if (!isRequestDocumentReady(documentsRef.current, requestSnapshot)) {
        activeAgentRequestRef.current = null
        controller.abort()
        setAgentView(buildAgentRequestErrorView(
          '所选文档已不可用，本次 Agent 结果已撤下，请重新选择后提交',
        ))
        return
      }
      setAgentView(terminalView)
      const confirmedReference = {
        runId: terminalView.runId,
        documentId: terminalView.documentId,
      }
      rememberConfirmedRun(confirmedReference)
      setAgentEventsView({ status: 'loading', runId: confirmedReference.runId })
      try {
        const events = await readAgentEvents(confirmedReference, controller.signal)
        if (!isCurrentRequest(activeAgentRequestRef.current?.snapshot ?? null, requestSnapshot)) {
          return
        }
        setAgentEventsView({
          status: 'ready',
          runId: confirmedReference.runId,
          events,
        })
      } catch {
        if (!isCurrentRequest(activeAgentRequestRef.current?.snapshot ?? null, requestSnapshot)) {
          return
        }
        setAgentEventsView({
          status: 'error',
          runId: confirmedReference.runId,
          message: '历史事件暂时无法读取；已验证结果仍然保留。',
        })
      }
    } catch {
      if (!isCurrentRequest(activeAgentRequestRef.current?.snapshot ?? null, requestSnapshot)) {
        return
      }
      setAgentView(buildAgentRequestErrorView(
        'Agent 请求失败或响应无法确认；不会自动重试，且当前没有已确认的 Run 身份',
      ))
    } finally {
      if (isCurrentRequest(activeAgentRequestRef.current?.snapshot ?? null, requestSnapshot)) {
        activeAgentRequestRef.current = null
      }
    }
  }

  return (
    <Container className="app-shell">
      <header className="app-header">
        <p className="eyebrow">FinDoc · 本地可信文档助手</p>
        <a href="/evidence">打开 PDF 证据工作台</a>
        <h1>从资料到可核对的结果</h1>
        <p>先选择一篇处理完成的文档，再使用自由问答或有限 Agent 任务。</p>
      </header>

      <section className="card upload-panel">
        <h2>上传 PDF</h2>
        <p className="section-description">当前只接收文本型 PDF，上传后会出现在资料列表中。</p>

        <label htmlFor="pdf-file">选择文本型 PDF</label>
        <input
          id="pdf-file"
          type="file"
          accept="application/pdf"
          onChange={handleFileChange}
        />

        {selectedFile !== null && (
          <p>已选择：{selectedFile.name}</p>
        )}

        <button
          type="button"
          disabled={selectedFile === null || isUploading}
          onClick={() => void uploadSelectedDocument()}
        >
          {isUploading ? '正在上传……' : '上传 PDF'}
        </button>
        {uploadError !== null && (
          <p role="alert">{uploadError}</p>
        )}
        {uploadMessage !== null && (
          <p role="status">{uploadMessage}</p>
        )}
      </section>

      <section className="card documents-panel" aria-labelledby="documents-title">
      <div className="section-heading-row">
        <div>
          <h2 id="documents-title">1. 选择资料</h2>
          <p className="section-description">当前共有 {documents.length} 篇；只有 ready 文档可以选择。</p>
        </div>
      </div>
      {/* 请求尚未结束时，只显示加载提示 */}
      {isLoadingDocuments && (<p>正在加载文档……</p>)}

      {/* 请求结束并且存在错误时，显示安全错误消息和重试按钮 */}
      {!isLoadingDocuments && documentError !== null && (
        <section>
          <p role="alert">{documentError}</p>
          <button type="button"
            onClick={handleReloadDocuments}
          >
            重新加载
          </button>
        </section>
      )}
      {/* 请求成功但没有文档时，显示空状态 */}
      {!isLoadingDocuments && documentError === null && documents.length === 0 && (<p>还没有上传文档</p>)}

      {/* 请求成功且存在文档时，把每条记录转换为一个列表项 */}
      {!isLoadingDocuments && documentError === null && documents.length > 0 && (
        <ul className="document-list">
          {documents.map((document) => (
            <li key={document.document_id}>
              <label className="document-option">
                <input
                  type="radio"
                  name="selected-document"
                  value={document.document_id}
                  checked={selectedDocumentId === document.document_id}
                  disabled={document.status !== 'ready' || requestIsPending}
                  onChange={() => handleDocumentSelection(document.document_id)}
                />
                <span className="document-name">{document.source_file}</span>
                <span className={`status-badge status-${document.status}`}>{document.status}</span>
              </label>
              {document.status === 'failed' && document.safe_error_message !== null && (
                <p className="message error" role="alert">处理失败：{document.safe_error_message}</p>
              )}
            </li>
          ))}
        </ul>
      )}
      {selectedDocumentId !== null && (
        <p className="selected-document">已选择文档：<code>{selectedDocumentId}</code></p>
      )}
      </section>

      <section className="card workbench-panel" aria-labelledby="workbench-title">
        <h2 id="workbench-title">2. 构造任务并查看结果</h2>
        <p className="section-description">RAG 接收自由问题；Agent 只接收页面提供的年份和指标。</p>
        <div className="mode-switch" aria-label="选择工作区">
          <button
            className="mode-button"
            type="button"
            aria-pressed={workbenchMode === 'rag'}
            disabled={requestIsPending}
            onClick={() => handleWorkbenchMode('rag')}
          >
            RAG 自由问答
          </button>
          <button
            className="mode-button"
            type="button"
            aria-pressed={workbenchMode === 'agent'}
            disabled={requestIsPending}
            onClick={() => handleWorkbenchMode('agent')}
          >
            Agent 有限任务
          </button>
        </div>

      {workbenchMode === 'rag' && (
      <section className="workbench-content" aria-labelledby="rag-title">
        <div className="section-heading-row">
          <div>
            <h3 id="rag-title">向当前资料自由提问</h3>
            <p className="section-description">该入口消费六事件 SSE；它不是 Agent Run。</p>
          </div>
          <span className="mode-label">RAG · SSE</span>
        </div>

        {selectedReadyDocument === null && (
          <p className="message neutral">请先选择一篇 ready 文档</p>
        )}

        <label htmlFor="chat-query">问题</label>
        <textarea
          id="chat-query"
          value={query}
          onChange={handleQueryChange}
          disabled={selectedReadyDocument === null || requestIsPending}
          rows={4}
        />
        <button
          type="button"
          disabled={
            selectedReadyDocument === null || query.trim().length === 0 || requestIsPending
          }
          onClick={() => void submitQuestion()}
        >
          {chatView.status === 'streaming' ? '正在查询……' : '发送问题'}
        </button>

        {chatView.status === 'streaming' && (
          <p className="message neutral" role="status">正在查询并验证答案……</p>
        )}

        {chatView.status === 'success' && chatView.answer !== null && (
          <section className="result-card">
            <h3>答案</h3>
            <p className="answer-copy">{chatView.answer}</p>

            <h3>引用</h3>
            {chatView.citations.length === 0 ? (
              <p>没有引用</p>
            ) : (
              <ol className="citation-list">
                {chatView.citations.map((citation) => (
                  <li key={citation.number}>
                    {citation.source_file}，第 {citation.page} 页，chunk：{citation.chunk_id}
                  </li>
                ))}
              </ol>
            )}
          </section>
        )}

        {chatView.status === 'refusal' && (
          <p className="message warning" role="status">正常拒答：无法基于当前文档回答（{chatView.refusalReason}）</p>
        )}

        {chatView.status === 'error' && (
          <p className="message error" role="alert">问答错误：{chatView.errorMessage}</p>
        )}
      </section>
      )}

      {workbenchMode === 'agent' && (
        <section className="workbench-content" aria-labelledby="agent-title">
          <div className="section-heading-row">
            <div>
              <h3 id="agent-title">创建有限 Agent 任务</h3>
              <p className="section-description">
                支持任务不代表资料一定有答案，也不表示已经支持财务计算。
              </p>
            </div>
            <span className="mode-label">Agent · JSON</span>
          </div>

          <section className="run-history-panel" aria-labelledby="run-history-title">
            <div className="section-heading-row">
              <div>
                <h4 id="run-history-title">本机已知 Run</h4>
                <p className="section-description">
                  这里只保存 Run 与文档身份，作为服务器查找线索；不是答案缓存或读取授权。
                </p>
              </div>
              {(runIndexState.references.length > 0 || runIndexState.issue === 'invalid') && (
                <button
                  className="secondary-button compact-button"
                  type="button"
                  disabled={requestIsPending}
                  onClick={handleClearRunIndex}
                >
                  清除本机索引
                </button>
              )}
            </div>
            {runIndexNotice !== null && (
              <p className="message neutral" role="status">{runIndexNotice}</p>
            )}
            {runIndexState.references.length === 0
              ? <p className="empty-state">此浏览器还没有已确认的 Run 引用。</p>
              : (
                <ul className="run-reference-list">
                  {runIndexState.references.map((reference, index) => (
                    <li key={reference.runId}>
                      <div>
                        <strong>{index === 0 ? '最近查看' : '已知 Run'}</strong>
                        <span><code>{reference.runId}</code></span>
                        <span>文档：<code>{reference.documentId}</code></span>
                      </div>
                      <div className="run-reference-actions">
                        <button
                          className="secondary-button compact-button"
                          type="button"
                          disabled={requestIsPending}
                          onClick={() => void loadKnownAgentRun(reference)}
                        >
                          GET 读取
                        </button>
                        <button
                          className="text-button compact-button"
                          type="button"
                          disabled={requestIsPending}
                          onClick={() => handleRemoveRunReference(reference.runId)}
                        >
                          移除本机引用
                        </button>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            <p className="history-boundary">
              本机记录不跨浏览器或设备；移除引用不会删除服务器上的 Run。
            </p>
          </section>

          {selectedReadyDocument === null && (
            <p className="message neutral">创建新任务前，请先选择一篇 ready 文档。</p>
          )}

          <div className="agent-form">
            <label className="field-group" htmlFor="agent-year">
              <span>年份</span>
              <input
                id="agent-year"
                type="text"
                inputMode="numeric"
                autoComplete="off"
                maxLength={4}
                pattern="[0-9]{4}"
                value={agentYear}
                disabled={requestIsPending}
                aria-describedby="agent-year-help"
                onChange={handleAgentYearChange}
              />
              <small id="agent-year-help">四位 ASCII 数字，例如 2025</small>
            </label>
            <label className="field-group" htmlFor="agent-metric">
              <span>指标</span>
              <select
                id="agent-metric"
                value={agentMetric}
                disabled={requestIsPending}
                onChange={handleAgentMetricChange}
              >
                {AGENT_METRICS.map((metric) => (
                  <option key={metric} value={metric}>{metric}</option>
                ))}
              </select>
              <small>首版仅支持这三个固定指标</small>
            </label>
          </div>

          <div className="task-preview">
            <span>将提交的准确任务</span>
            {agentQueryPreview === null
              ? <strong>请输入四位数字年份</strong>
              : <code>{agentQueryPreview}</code>}
          </div>
          <button
            className="primary-button"
            type="button"
            disabled={selectedReadyDocument === null || !agentYearIsValid || requestIsPending}
            onClick={() => void submitAgentTask()}
          >
            {agentView.status === 'pending'
              ? '正在处理任务……'
              : agentView.status === 'request_error'
                ? '再次创建 Agent Run（可能产生新 Run）'
                : '创建并执行 Agent Run'}
          </button>

          {agentHistoryRead.status === 'loading' && (
            <section className="message neutral" role="status" aria-live="polite">
              <strong>正在读取已保存结果</strong>
              <p>Run：{agentHistoryRead.reference.runId}</p>
              <p>本次只发送 GET，不重新执行任务。</p>
            </section>
          )}
          {agentHistoryRead.status === 'error' && (
            <section className="message error" role="alert">
              <strong>无法恢复已知 Run</strong>
              <p>{agentHistoryRead.message}</p>
              <p>Run：{agentHistoryRead.reference.runId}</p>
            </section>
          )}
          {agentView.status === 'idle'
            && agentHistoryRead.status !== 'loading'
            && agentHistoryRead.status !== 'error' && (
            <p className="empty-state">提交后将在这里显示回答、正常拒答或错误。</p>
          )}
          {agentView.status === 'pending' && (
            <section className="message neutral" role="status" aria-live="polite">
              <strong>任务正在执行、验证并保存</strong>
              <p>已提交：{submittedAgentQuery}</p>
              <p>资料：{agentViewDocumentName}</p>
              <p>这是同步等待状态，不是 SSE 实时进度。</p>
            </section>
          )}
          {agentView.status === 'answered' && (
            <section className="result-card">
              <div className="section-heading-row">
                <div><p className="eyebrow">已回答</p><h3>Agent 结果</h3></div>
                <span className="result-status answered">answered</span>
              </div>
              <dl className="result-identity">
                <div><dt>资料</dt><dd>{agentViewDocumentName}</dd></div>
                <div><dt>Run ID</dt><dd><code>{agentView.runId}</code></dd></div>
                <div>
                  <dt>任务</dt>
                  <dd>{submittedAgentQuery ?? '历史 Run（未保存任务文本）'}</dd>
                </div>
              </dl>
              <p className="answer-copy">{agentView.content}</p>
              <h4>引用</h4>
              <ol className="citation-list">
                {agentView.citations.map((citation) => (
                  <li key={`${citation.number}-${citation.chunk_id}`}>
                    <strong>[{citation.number}] {citation.source_file}</strong>
                    <span>第 {citation.page} 页 · chunk {citation.chunk_id}</span>
                  </li>
                ))}
              </ol>
            </section>
          )}
          {agentView.status === 'refusal' && (
            <section className="message warning" role="status">
              <strong>正常拒答</strong>
              <p>{agentView.message}</p>
              <p>原因：{agentView.reason}</p>
              <p>资料：{agentViewDocumentName} · Run ID：{agentView.runId}</p>
              <p>任务：{submittedAgentQuery ?? '历史 Run（未保存任务文本）'}</p>
            </section>
          )}
          {agentView.status === 'system_error' && (
            <section className="message error" role="alert">
              <strong>已提交的产品错误</strong>
              <p>{agentView.message}</p>
              <p>错误码：{agentView.errorCode}</p>
              <p>资料：{agentViewDocumentName} · Run ID：{agentView.runId}</p>
              <p>任务：{submittedAgentQuery ?? '历史 Run（未保存任务文本）'}</p>
            </section>
          )}
          {agentView.status === 'request_error' && (
            <section className="message error" role="alert">
              <strong>请求错误</strong>
              <p>{agentView.message}</p>
              {submittedAgentQuery !== null && <p>提交任务：{submittedAgentQuery}</p>}
            </section>
          )}

          {displayedAgentRunId !== null && (
            <section className="event-history" aria-labelledby="event-history-title">
              <div className="section-heading-row">
                <div>
                  <p className="eyebrow">history projection</p>
                  <h4 id="event-history-title">安全历史事件</h4>
                </div>
                <span className="mode-label">不是实时进度</span>
              </div>
              <p className="section-description">
                事件只说明执行后留下的有限摘要；不表示思维链、精确耗时或崩溃恢复。
              </p>
              {agentEventsView.status === 'loading'
                && agentEventsView.runId === displayedAgentRunId && (
                <p className="message neutral" role="status">正在读取历史事件……</p>
              )}
              {agentEventsView.status === 'error'
                && agentEventsView.runId === displayedAgentRunId && (
                <p className="message warning" role="status">{agentEventsView.message}</p>
              )}
              {agentEventsView.status === 'ready'
                && agentEventsView.runId === displayedAgentRunId
                && (agentEventsView.events.length === 0
                  ? <p className="empty-state">该 Run 没有可展示的安全历史事件。</p>
                  : (
                    <ol className="event-list">
                      {agentEventsView.events.map((event) => (
                        <li key={event.sequence}>
                          <span className="event-sequence">{event.sequence}</span>
                          <div>
                            <strong>{event.executionEventType}</strong>
                            <p>{event.summary}</p>
                          </div>
                        </li>
                      ))}
                    </ol>
                  ))}
            </section>
          )}
        </section>
      )}
      </section>
    </Container>
  )
}

export default App
