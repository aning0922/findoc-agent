export type SSEEventName =
  | 'status'
  | 'final_answer'
  | 'citation'
  | 'usage'
  | 'error'
  | 'done'

export interface ParsedSSEEvent {
  event: SSEEventName
  data: unknown
}

const SSE_EVENT_NAMES = new Set<string>([
  'status',
  'final_answer',
  'citation',
  'usage',
  'error',
  'done',
])

export interface ExtractedSSEFrames {
  // 这次可以安全解析的完整 SSE 帧
  frames: string[]

  // 还没有遇到结尾双换行的残余文本
  remainder: string
}

export type SSEEventHandler = (
  event: ParsedSSEEvent
) => void

/**
 * 从累计文本 buffer 中提取所有以双换行结束的完整 SSE 帧。
 *
 * @param buffer - 当前累计文本，可能包含零个、一个或多个完整帧。
 * @returns 完整帧数组以及必须保留到下一次读取的残余文本。
 * @remarks 只负责 framing，不解析 event 名或 JSON data。
 */
export function extractSSEFrames(
  buffer: string,
): ExtractedSSEFrames {
  const parts = buffer.split('\n\n')
  const remainder = parts.pop() ?? ''

  return {
    frames: parts,
    remainder,
  }
}

/**
 * 判断字符串是否属于今天允许的六种 SSE 事件名
 * @param value - 从 event 行提取来的未经信任字符串
 * @returns 属于白名单时返回 true，否则返回 false。
 * @remarks 只验证事件名，不验证对应 data 的字段
 */
function isSSEEventName(value: string): value is SSEEventName {
  return SSE_EVENT_NAMES.has(value)
}


/**
 * 把一个完整 SSE 帧解析为受限事件名和 JSON data。
 *
 * @param frame - 已由 extractSSEFrames 确认为完整的单个帧。
 * @returns 事件名以及 JSON.parse 后的 unknown 数据。
 * @throws event 缺失、data 缺失、事件名未知或 JSON 非法时抛出 Error。
 */
export function parseSSEFrame(
  frame: string,
): ParsedSSEEvent {
  const lines = frame.split('\n')
  const eventLine = lines.find((line) => line.startsWith('event:'))
  const dataLines = lines.filter((line) => line.startsWith('data:'))
  if (eventLine === undefined) {
    throw new Error('SSE 帧缺少 event 字段')
  }
  if (dataLines.length === 0) {
    throw new Error('SSE 帧缺少 data 字段')
  }

  const eventName = eventLine.slice('event:'.length).trim()
  if (!isSSEEventName(eventName)) {
    throw new Error('SSE 帧包含未知事件名')
  }

  const dataText = dataLines
    .map((line) => line.slice('data:'.length).trimStart())
    .join('\n')
  const data: unknown = JSON.parse(dataText)
  return {
    event: eventName,
    data,
  }
}

/**
 * 从浏览器字节流中持续恢复并发送 SSE 事件
 *
 * @param stream - fetch response.body提供的可读字节流
 * @param onEvent - 每恢复一个合法事件时调用的同步处理函数
 * @returns 流以唯一 done 正常结束时完成的 Promise
 * @throws 帧不完整，事件非法，done 缺失或 done 后仍有事件时抛出 Error
 */
export async function consumeSSEStream(
  stream: ReadableStream<Uint8Array>,
  onEvent: SSEEventHandler,
): Promise<void> {
  const reader = stream.getReader()
  const decoder = new TextDecoder()

  let buffer = ''
  let receivedDone = false
  try {
    while (true) {
      const { value, done } = await reader.read()
      if (done) {
        break
      }
      if (value === undefined) {
        continue
      }
      buffer += decoder.decode(value, { stream: true })

      const extracted = extractSSEFrames(buffer)
      buffer = extracted.remainder
      for (const frame of extracted.frames) {
        const parsed = parseSSEFrame(frame)
        if (receivedDone) {
          throw new Error('SSE done 后仍收到额外事件')
        }
        onEvent(parsed)
        if (parsed.event === 'done') {
          receivedDone = true
        }
      }
    }

    buffer += decoder.decode()
    if (buffer.length > 0) {
      throw new Error('SSE 响应以不完整帧结束')
    }
    if (!receivedDone) {
      throw new Error('SSE 响应缺少 done 事件')
    }

  } finally {
    reader.releaseLock()
  }
}
