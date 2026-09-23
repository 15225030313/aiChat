/**
 * 流式对话请求层（阶段一核心：Fetch ReadableStream + SSE 解析）
 *
 * 关键点（面试高频）：
 * 1. fetch + ReadableStream + getReader + TextDecoder 原生流式解析
 * 2. TextDecoder 必须 stream: true，否则多字节中文被切断时会乱码
 * 3. 网络分片和 SSE 事件边界不对齐，需要 buffer 缓冲区按 "\n\n" 切事件
 * 4. AbortController 实现停止生成
 * 5. TTFT（首字延迟）埋点：简历量化数据从这里来
 */

import type { SourceRef } from '../types'

export interface StreamCallbacks {
  /** RAG 模式：流开始时后端先推本次回答引用的知识库片段 */
  onSources?: (sources: SourceRef[]) => void
  /** 每收到一段增量文本 */
  onDelta?: (text: string) => void
  /** 首个 token 到达，参数为 TTFT 毫秒数 */
  onFirstToken?: (ttftMs: number) => void
  /** 上游/网络错误 */
  onError?: (message: string) => void
}

export async function streamChat(
  messages: { role: string; content: string }[],
  signal: AbortSignal,
  callbacks: StreamCallbacks,
  knowledgeBaseId?: number | null,
): Promise<void> {
  const startTime = performance.now()
  let firstTokenAt = 0

  const res = await fetch('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ messages, knowledge_base_id: knowledgeBaseId ?? null }),
    signal,
  })

  if (!res.ok || !res.body) {
    let detail = `请求失败（${res.status}）`
    try {
      const body = await res.json()
      if (body?.detail) detail = body.detail
    } catch {
      /* 忽略解析失败 */
    }
    callbacks.onError?.(detail)
    return
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    // stream: true 关键——中文等多字节字符被分片切断时不会产生乱码
    buffer += decoder.decode(value, { stream: true })

    // SSE 以空行分隔事件；最后一段可能不完整，留在 buffer 里等下一个分片
    const events = buffer.split('\n\n')
    buffer = events.pop() ?? ''

    for (const event of events) {
      for (const line of event.split('\n')) {
        if (!line.startsWith('data:')) continue
        const data = line.slice(5).trim()
        if (!data || data === '[DONE]') continue

        try {
          const parsed = JSON.parse(data)
          if (parsed.error) {
            callbacks.onError?.(parsed.error)
            return
          }
          // RAG 模式首个事件：引用来源元数据
          if (parsed.type === 'sources' && Array.isArray(parsed.sources)) {
            callbacks.onSources?.(parsed.sources)
            continue
          }
          const delta: string | undefined = parsed.choices?.[0]?.delta?.content
          if (delta) {
            if (!firstTokenAt) {
              firstTokenAt = performance.now()
              callbacks.onFirstToken?.(Math.round(firstTokenAt - startTime))
            }
            callbacks.onDelta?.(delta)
          }
        } catch {
          // 单个片段解析失败直接忽略，不能让整条流挂掉
        }
      }
    }
  }
}
