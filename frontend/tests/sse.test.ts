import assert from 'node:assert/strict'
import test from 'node:test'

import {
  consumeSSEStream,
  extractSSEFrames,
  parseSSEFrame,
  type ParsedSSEEvent,
} from '../src/sse.ts'

/**
 * 把指定文本块转换成可由 consumeSSEStream 读取的字节流。
 *
 * @param chunks - 用来模拟网络分块的文本数组。
 * @returns 按数组顺序发送并最终关闭的 UTF-8 字节流。
 * @remarks 只供测试使用，不模拟网络延迟或取消。
 */
function createByteStream(
  chunks: string[],
): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder()

  return new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) {
        controller.enqueue(encoder.encode(chunk))
      }

      controller.close()
    },
  })
}

test('跨网络 chunk 保留残余并恢复完整 SSE 帧', () => {
  const firstChunk =
    'event: status\ndata: {"phase":"ans'

  const firstResult = extractSSEFrames(firstChunk)

  assert.deepEqual(firstResult.frames, [])
  assert.equal(firstResult.remainder, firstChunk)

  const secondChunk =
    'wering"}\n\nevent: done\ndata: {"outcome":"success"}\n\n'

  const secondResult = extractSSEFrames(firstResult.remainder + secondChunk)

  assert.deepEqual(secondResult.frames, [
    'event: status\ndata: {"phase":"answering"}',
    'event: done\ndata: {"outcome":"success"}',
  ])
  assert.equal(secondResult.remainder, '')
})

// 验证完整 citation 帧会解析为受限事件名和 JSON 数据
test('解析合法 citation SSE 帧', () => {
  const result = parseSSEFrame(
    'event: citation\ndata: {"number":1,"source_file":"report.pdf","page":3,"chunk_id":"chunk-1"}',
  )

  assert.equal(result.event, 'citation')
  assert.deepEqual(result.data, {
    number: 1,
    source_file: 'report.pdf',
    page: 3,
    chunk_id: 'chunk-1',
  })
})

// 验证未冻结的 token 事件不能进入前端可信事件处理层。
test('拒绝未知 SSE 事件名', () => {
  assert.throws(
    () =>
      parseSSEFrame(
        'event: token\ndata: {"text":"未经验证的模型原始输出"}',
      ),
    /未知事件名/,
  )
})


// 验证跨 chunk 的正常事件流只有收到 done 后才成功结束。
test('消费跨 chunk SSE 流并在 done 后正常完成', async () => {
  const stream = createByteStream([
    'event: status\ndata: {"phase":"ans',
    'wering"}\n\nevent: final_answer\ndata: {"content":"已验证答案"}\n\n',
    'event: done\ndata: {"outcome":"success"}\n\n',
  ])

  const eventNames: string[] = []

  await consumeSSEStream(stream, (event) => {
    eventNames.push(event.event)
  })

  assert.deepEqual(eventNames, [
    'status',
    'final_answer',
    'done',
  ])
})

// 验证网络连接关闭不能代替业务 done，缺少 done 必须拒绝正常完成。
test('拒绝缺少 done 的 SSE 流', async () => {
  const stream = createByteStream([
    'event: status\ndata: {"phase":"answering"}\n\n',
    'event: final_answer\ndata: {"content":"不能标记完成"}\n\n',
  ])

  await assert.rejects(
    consumeSSEStream(stream, () => {
      // 测试只关心最终失败，不需要收集中间事件。
    }),
    /缺少 done/,
  )
})

/**
 * 模拟浏览器先收到 status 和 final_answer，下一次读取再发生网络异常。
 *
 * 输入：第一批是两个完整SSE帧，第二次读取抛出socket reset。
 * 输出：消费Promise失败，暂存答案不能被视为正常完成。
 * 失败边界：若函数正常返回，说明缺少done的中断流被错误接受。
 */
test('读取异常发生在 final_answer 后仍拒绝正常完成', async () => {

  let pullCount = 0
  const receivedEvents: ParsedSSEEvent[] = []
  const encoder = new TextEncoder()
  const stream = new ReadableStream<Uint8Array>({
    pull(controller) {
      // 根据调用次数决定 enqueue 第一批字节，还是 controller.error(...)
      if (pullCount === 0) {
        pullCount++
        controller.enqueue(encoder.encode('event: status\ndata: {"phase":"answering"}\n\n'))
        controller.enqueue(encoder.encode('event: final_answer\ndata: {"content":"不能标记完成"}\n\n'))
      } else if (pullCount === 1) {
        pullCount++
        controller.error(new Error('socket reset'))
      }
    },
  })
  await assert.rejects(
    consumeSSEStream(stream, (event) => {
      receivedEvents.push(event)
    }),
    /socket reset/
  )
  assert.deepEqual(receivedEvents, [
    { event: 'status', data: { phase: 'answering' } },
    { event: 'final_answer', data: { content: '不能标记完成' } },
  ])
})