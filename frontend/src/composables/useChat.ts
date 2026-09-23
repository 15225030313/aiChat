/**
 * useChat —— 通用对话 Hook（未来「vue-ai-chat」开源组件库的核心雏形）
 *
 * 职责：管理对话全部状态（消息列表、加载中、报错、TTFT），
 * 对外只暴露 sendMessage / stopGeneration / clearMessages。
 * 组件层不关心流式细节，只消费状态 —— 这是它以后能抽成独立库的前提。
 */

import { ref } from 'vue'
import type { ChatMessage } from '../types'
import { streamChat } from '../api/chat'

export function useChat() {
  const messages = ref<ChatMessage[]>([])
  const isLoading = ref(false)
  const error = ref('')
  /** 最近一次回答的首字延迟（ms），页面直接可展示 */
  const ttft = ref(0)

  let controller: AbortController | null = null

  async function sendMessage(content: string, knowledgeBaseId?: number | null) {
    const trimmed = content.trim()
    if (!trimmed || isLoading.value) return

    error.value = ''
    messages.value.push({ role: 'user', content: trimmed })

    // 预置一条空的 assistant 消息，流式增量直接往里追加
    const assistantMsg: ChatMessage = { role: 'assistant', content: '' }
    messages.value.push(assistantMsg)
    isLoading.value = true

    controller = new AbortController()

    // 发送给后端的历史：全部对话（不含空 assistant 占位）
    // RAG 模式下 system 提示词由后端检索后动态拼装，前端不用传
    const history = messages.value
      .filter((m) => m !== assistantMsg && !(m.role === 'assistant' && !m.content))
      .map((m) => ({ role: m.role, content: m.content }))

    try {
      await streamChat(
        history,
        controller.signal,
        {
          onSources(sources) {
            // 引用元数据先于正文到达，挂到本条回答上供溯源 UI 展示
            assistantMsg.sources = sources
          },
          onDelta(text) {
            assistantMsg.content += text
          },
          onFirstToken(ms) {
            ttft.value = ms
          },
          onError(message) {
            error.value = message
          },
        },
        knowledgeBaseId,
      )
    } catch (err) {
      // AbortError 是用户主动停止，不算异常
      if (err instanceof DOMException && err.name === 'AbortError') {
        assistantMsg.content += '\n\n（已停止生成）'
      } else {
        error.value = err instanceof Error ? err.message : '网络异常，请稍后重试'
      }
    } finally {
      isLoading.value = false
      controller = null
    }
  }

  function stopGeneration() {
    controller?.abort()
  }

  function clearMessages() {
    stopGeneration()
    messages.value = []
    error.value = ''
    ttft.value = 0
  }

  return { messages, isLoading, error, ttft, sendMessage, stopGeneration, clearMessages }
}
