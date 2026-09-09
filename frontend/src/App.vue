<script setup lang="ts">
/**
 * 阶段一对话界面（最小可用版）
 * 说明：Markdown 流式渲染、代码高亮、防闪烁是第2-3周的任务，
 * 当前先用 pre-wrap 纯文本渲染，跑通「发送→逐字输出→停止」闭环。
 */
import { ref, nextTick, watch } from 'vue'
import { useChat } from './composables/useChat'
import { renderMarkdown } from './utils/markdown'

const { messages, isLoading, error, ttft, sendMessage, stopGeneration, clearMessages } = useChat()

const input = ref('')
const listRef = ref<HTMLElement>()

async function handleSend() {
  const content = input.value
  input.value = ''
  await sendMessage(content)
}

function handleKeydown(e: KeyboardEvent) {
  // Enter 发送，Shift+Enter 换行
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    handleSend()
  }
}

// 新消息时自动滚动到底部
watch(
  () => messages.value[messages.value.length - 1]?.content,
  async () => {
    await nextTick()
    listRef.value?.scrollTo({ top: listRef.value.scrollHeight })
  },
)
</script>

<template>
  <div class="chat-page">
    <header class="chat-header">
      <h1>企业知识库AI问答系统</h1>
      <span v-if="ttft" class="ttft">首字延迟 {{ ttft }}ms</span>
      <button class="ghost-btn" :disabled="!messages.length" @click="clearMessages">清空对话</button>
    </header>

    <main ref="listRef" class="chat-list">
      <div v-if="!messages.length" class="empty-tip">
        <p>流式对话 Demo 已就绪</p>
        <p class="sub">输入问题开始对话（需先在 backend/.env 配置 API Key）</p>
      </div>

      <div
        v-for="(msg, i) in messages"
        :key="i"
        class="msg-row"
        :class="msg.role"
      >
        <div class="bubble">
          <!-- 用户消息纯文本；AI 回答走 Markdown 流式渲染 -->
          <pre v-if="msg.role === 'user'" class="content">{{ msg.content }}</pre>
          <div
            v-else
            class="content markdown-body"
            v-html="renderMarkdown(msg.content)"
          />
        </div>
      </div>

      <div v-if="error" class="error-tip">{{ error }}</div>
    </main>

    <footer class="chat-input">
      <textarea
        v-model="input"
        :disabled="isLoading"
        rows="3"
        placeholder="输入问题，Enter 发送 / Shift+Enter 换行"
        @keydown="handleKeydown"
      />
      <button v-if="isLoading" class="stop-btn" @click="stopGeneration">停止生成</button>
      <button v-else class="send-btn" :disabled="!input.trim()" @click="handleSend">发送</button>
    </footer>
  </div>
</template>

<style scoped>
.chat-page {
  display: flex;
  flex-direction: column;
  height: 100%;
  max-width: 860px;
  margin: 0 auto;
  padding: 16px;
}

.chat-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 4px;
}

.chat-header h1 {
  font-size: 18px;
  font-weight: 500;
  flex: 1;
}

.ttft {
  font-size: 12px;
  color: #16b8a6;
}

.ghost-btn {
  border: 1px solid #dcdfe6;
  background: #fff;
  color: #606266;
  border-radius: 6px;
  padding: 6px 12px;
  font-size: 13px;
  cursor: pointer;
}

.ghost-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.chat-list {
  flex: 1;
  overflow-y: auto;
  padding: 12px 4px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.empty-tip {
  margin: auto;
  text-align: center;
  color: #909399;
}

.empty-tip .sub {
  font-size: 13px;
  margin-top: 8px;
}

.msg-row {
  display: flex;
}

.msg-row.user {
  justify-content: flex-end;
}

.bubble {
  max-width: 78%;
  border-radius: 10px;
  padding: 10px 14px;
  line-height: 1.6;
}

.msg-row.user .bubble {
  background: #16b8a6;
  color: #fff;
}

.msg-row.assistant .bubble {
  background: #fff;
  border: 1px solid #e4e7ed;
}

.content {
  font-family: inherit;
  white-space: pre-wrap;
  word-break: break-word;
}

/* Markdown 渲染区不做 pre-wrap，交给 markdown 解析 */
.markdown-body {
  white-space: normal;
  font-size: 14px;
}

.markdown-body :deep(p) {
  margin: 6px 0;
}

.markdown-body :deep(p:first-child) {
  margin-top: 0;
}

.markdown-body :deep(p:last-child) {
  margin-bottom: 0;
}

.markdown-body :deep(ul),
.markdown-body :deep(ol) {
  padding-left: 20px;
  margin: 6px 0;
}

.markdown-body :deep(table) {
  border-collapse: collapse;
  margin: 8px 0;
}

.markdown-body :deep(th),
.markdown-body :deep(td) {
  border: 1px solid #e4e7ed;
  padding: 4px 10px;
  font-size: 13px;
}

.markdown-body :deep(blockquote) {
  border-left: 3px solid #16b8a6;
  padding-left: 10px;
  color: #606266;
  margin: 8px 0;
}

.markdown-body :deep(.code-block) {
  margin: 8px 0;
  border-radius: 8px;
  overflow: hidden;
  background: #f6f8fa;
}

.markdown-body :deep(.code-lang) {
  font-size: 12px;
  color: #909399;
  padding: 4px 12px;
  border-bottom: 1px solid #e4e7ed;
}

.markdown-body :deep(.code-block pre) {
  margin: 0;
  padding: 10px 12px;
  overflow-x: auto;
}

.markdown-body :deep(code) {
  font-family: Consolas, Monaco, 'Courier New', monospace;
  font-size: 13px;
}

.error-tip {
  text-align: center;
  color: #f56c6c;
  font-size: 13px;
}

.chat-input {
  display: flex;
  gap: 12px;
  align-items: flex-end;
  padding-top: 12px;
}

.chat-input textarea {
  flex: 1;
  resize: none;
  border: 1px solid #dcdfe6;
  border-radius: 8px;
  padding: 10px 12px;
  font-size: 14px;
  font-family: inherit;
  line-height: 1.5;
  outline: none;
}

.chat-input textarea:focus {
  border-color: #16b8a6;
}

.send-btn,
.stop-btn {
  padding: 10px 20px;
  border: none;
  border-radius: 8px;
  font-size: 14px;
  cursor: pointer;
  color: #fff;
}

.send-btn {
  background: #16b8a6;
}

.send-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.stop-btn {
  background: #f56c6c;
}
</style>
