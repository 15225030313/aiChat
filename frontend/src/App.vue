<script setup lang="ts">
/**
 * 对话界面
 * - 智能滚动（贴底跟随）：用户停留在底部时新内容自动跟随；向上翻阅历史时不打断
 *   （判断逻辑：scrollHeight - scrollTop - clientHeight < 阈值 即认为「贴底」）
 * - 用户主动发送消息时，无论当前在哪里都强制回到底部
 */
import { ref, nextTick, watch, onMounted } from 'vue'
import { useChat } from './composables/useChat'
import { renderMarkdownWithCitations } from './utils/markdown'
import KnowledgePanel from './components/KnowledgePanel.vue'
import { listDocuments } from './api/kb'
import type { ChatMessage, KbDocument, SourceRef } from './types'

/** 顶部导航：对话 / 知识库（后续页面多了再换 vue-router） */
const activeTab = ref<'chat' | 'kb'>('chat')

const { messages, isLoading, error, ttft, sendMessage, stopGeneration, clearMessages } = useChat()

// ===== 知识库选择（RAG 模式开关）=====
const kbDocs = ref<KbDocument[]>([])
const kbError = ref('')
/** null = 不用知识库（普通对话）；选中的文档必须是已向量化的 */
const selectedKbId = ref<number | null>(null)

async function loadKbDocs() {
  kbError.value = ''
  try {
    kbDocs.value = await listDocuments()
    // 当前选中的文档被删除/未向量化时，自动回落到普通对话
    const cur = kbDocs.value.find((d) => d.id === selectedKbId.value)
    if (!cur || !cur.vectorized) selectedKbId.value = null
  } catch (e) {
    kbError.value = e instanceof Error ? e.message : '知识库列表加载失败'
  }
}

onMounted(loadKbDocs)
// 从知识库页切回对话页时刷新列表（上传/删除后状态可能变了）
watch(activeTab, (t) => {
  if (t === 'chat') loadKbDocs()
})

// ===== 引用溯源：点击角标/来源chip弹窗看原文 =====
const activeSource = ref<SourceRef | null>(null)

/**
 * 正文角标点击（事件委托在 v-html 容器上）：
 * sup.cite-ref 带 data-idx，据此在本条消息的 sources 里找对应引用
 */
function handleCiteClick(msg: ChatMessage, e: MouseEvent) {
  const target = e.target as HTMLElement
  const idx = target.dataset?.idx
  if (!idx) return
  const source = msg.sources?.find((s) => s.index === Number(idx))
  if (source) activeSource.value = source
}

const input = ref('')
const listRef = ref<HTMLElement>()
/** 用户是否停留在列表底部（决定新内容要不要自动跟随） */
const isNearBottom = ref(true)

/** 贴底判定阈值：距底部 60px 以内都算贴底 */
function handleScroll() {
  const el = listRef.value
  if (!el) return
  isNearBottom.value = el.scrollHeight - el.scrollTop - el.clientHeight < 60
}

function scrollToBottom() {
  listRef.value?.scrollTo({ top: listRef.value.scrollHeight })
}

async function handleSend() {
  const content = input.value
  input.value = ''
  // 发送即强制回到底部：用户关心的就是新回答
  isNearBottom.value = true
  await nextTick()
  scrollToBottom()
  await sendMessage(content, selectedKbId.value)
}

function handleKeydown(e: KeyboardEvent) {
  // Enter 发送，Shift+Enter 换行
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    handleSend()
  }
}

// 流式输出时：只有贴底状态才自动跟随滚动
watch(
  () => messages.value[messages.value.length - 1]?.content,
  async () => {
    if (!isNearBottom.value) return
    await nextTick()
    scrollToBottom()
  },
)

async function backToBottom() {
  isNearBottom.value = true
  await nextTick()
  scrollToBottom()
}
</script>

<template>
  <div class="chat-page">
    <header class="chat-header">
      <div class="title-wrap">
        <span class="logo-dot" />
        <h1>企业知识库AI问答系统</h1>
      </div>
      <nav class="tab-nav">
        <button class="tab-item" :class="{ active: activeTab === 'chat' }" @click="activeTab = 'chat'">对话</button>
        <button class="tab-item" :class="{ active: activeTab === 'kb' }" @click="activeTab = 'kb'">知识库</button>
      </nav>
      <button v-if="activeTab === 'chat'" class="ghost-btn" :disabled="!messages.length" @click="clearMessages">清空对话</button>
    </header>

    <KnowledgePanel v-if="activeTab === 'kb'" />
    <template v-else>
    <span v-if="ttft" class="ttft" title="首字延迟 Time To First Token">TTFT {{ ttft }}ms</span>

    <main ref="listRef" class="chat-list" @scroll="handleScroll">
      <div v-if="!messages.length" class="empty-tip">
        <div class="empty-icon" />
        <p class="empty-title">流式对话 Demo 已就绪</p>
        <p class="sub">输入问题开始对话（Enter 发送 / Shift+Enter 换行）</p>
      </div>

      <div
        v-for="(msg, i) in messages"
        :key="i"
        class="msg-row"
        :class="msg.role"
      >
        <div class="avatar" :class="msg.role">
          {{ msg.role === 'user' ? '我' : 'AI' }}
        </div>
        <div class="bubble">
          <!-- 用户消息纯文本；AI 回答走 Markdown 流式渲染 -->
          <pre v-if="msg.role === 'user'" class="content">{{ msg.content }}</pre>
          <div
            v-else
            class="content markdown-body"
            v-html="renderMarkdownWithCitations(msg.content)"
            @click="handleCiteClick(msg, $event)"
          />
          <!-- 来源溯源：答案引用的知识库片段 -->
          <div v-if="msg.sources?.length" class="sources">
            <span class="sources-label">引用来源</span>
            <button
              v-for="s in msg.sources"
              :key="s.index"
              class="source-chip"
              @click="activeSource = s"
            >
              [{{ s.index }}] {{ s.filename }}
            </button>
          </div>
          <span v-if="msg.role === 'assistant' && isLoading && i === messages.length - 1" class="cursor" />
        </div>
      </div>

      <div v-if="error" class="error-tip">{{ error }}</div>
    </main>

    <!-- 向上翻阅历史时出现，点击回到最新消息 -->
    <button v-if="!isNearBottom && messages.length" class="back-bottom" @click="backToBottom">
      回到最新 ↓
    </button>

    <footer class="chat-input">
      <!-- 知识库选择器：选中即进入 RAG 检索问答模式 -->
      <div class="kb-selector">
        <span class="kb-icon">📚</span>
        <select v-model="selectedKbId" class="kb-select" :disabled="isLoading">
          <option :value="null">普通对话（不使用知识库）</option>
          <option v-for="d in kbDocs" :key="d.id" :value="d.id" :disabled="!d.vectorized">
            {{ d.filename }}（{{ d.chunk_count }} 片{{ d.vectorized ? '' : ' · 待向量化' }}）
          </option>
        </select>
        <span v-if="selectedKbId" class="kb-mode-tag">RAG 检索模式</span>
      </div>
      <div class="input-box" :class="{ focused: input.trim() }">
        <textarea
          v-model="input"
          :disabled="isLoading"
          rows="3"
          placeholder="输入问题，Enter 发送 / Shift+Enter 换行"
          @keydown="handleKeydown"
        />
        <div class="input-footer">
          <span class="hint">{{ isLoading ? '回答生成中…' : 'Enter 发送 · Shift+Enter 换行' }}</span>
          <button v-if="isLoading" class="stop-btn" @click="stopGeneration">
            <span class="stop-icon" /> 停止生成
          </button>
          <button v-else class="send-btn" :disabled="!input.trim()" @click="handleSend">
            发送
          </button>
        </div>
      </div>
    </footer>
    </template>

    <!-- 引用溯源弹窗：点击 [n] 角标查看原文片段 -->
    <div v-if="activeSource" class="source-mask" @click.self="activeSource = null">
      <div class="source-modal">
        <header class="source-head">
          <span class="source-title">[{{ activeSource.index }}] {{ activeSource.filename }} · 第{{ activeSource.chunk_index + 1 }}片</span>
          <button class="source-close" @click="activeSource = null">✕</button>
        </header>
        <p class="source-sim">相关度 {{ (activeSource.similarity * 100).toFixed(1) }}%</p>
        <p class="source-snippet">{{ activeSource.snippet }}</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.chat-page {
  display: flex;
  flex-direction: column;
  height: 100%;
  max-width: 860px;
  margin: 0 auto;
  padding: 12px 16px 16px;
  position: relative;
}

/* ===== 头部 ===== */
.chat-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 4px 14px;
  border-bottom: 1px solid #eef0f3;
}

.title-wrap {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
}

.logo-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #16b8a6;
}

.chat-header h1 {
  font-size: 17px;
  font-weight: 500;
}

.tab-nav {
  display: flex;
  gap: 4px;
  background: #f0f2f5;
  border-radius: 999px;
  padding: 3px;
}

.tab-item {
  border: none;
  background: transparent;
  border-radius: 999px;
  padding: 5px 16px;
  font-size: 13px;
  color: #606266;
  cursor: pointer;
  transition: all 0.15s;
}

.tab-item.active {
  background: #fff;
  color: #16b8a6;
  font-weight: 500;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.08);
}

.ttft {
  font-size: 12px;
  color: #16b8a6;
  background: #e6f7f4;
  padding: 3px 10px;
  border-radius: 999px;
}

.ghost-btn {
  border: 1px solid #dcdfe6;
  background: #fff;
  color: #606266;
  border-radius: 999px;
  padding: 5px 14px;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.15s;
}

.ghost-btn:hover:not(:disabled) {
  border-color: #16b8a6;
  color: #16b8a6;
}

.ghost-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

/* ===== 消息列表 ===== */
.chat-list {
  flex: 1;
  overflow-y: auto;
  padding: 16px 4px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  scroll-behavior: smooth;
}

.empty-tip {
  margin: auto;
  text-align: center;
  color: #909399;
}

.empty-icon {
  width: 48px;
  height: 48px;
  margin: 0 auto 14px;
  border-radius: 14px;
  background: #e6f7f4;
  position: relative;
}

.empty-icon::after {
  content: '';
  position: absolute;
  inset: 14px;
  border-radius: 6px;
  background: #16b8a6;
  opacity: 0.55;
}

.empty-title {
  font-size: 15px;
  color: #606266;
  margin-bottom: 6px;
}

.empty-tip .sub {
  font-size: 13px;
}

.msg-row {
  display: flex;
  gap: 10px;
  align-items: flex-start;
}

.msg-row.user {
  flex-direction: row-reverse;
}

.avatar {
  flex-shrink: 0;
  width: 32px;
  height: 32px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  color: #fff;
}

.avatar.user {
  background: #7a8ef5;
}

.avatar.assistant {
  background: #16b8a6;
}

.bubble {
  max-width: 78%;
  border-radius: 12px;
  padding: 10px 14px;
  line-height: 1.65;
  font-size: 14px;
}

.msg-row.user .bubble {
  background: #16b8a6;
  color: #fff;
  border-top-right-radius: 4px;
}

.msg-row.assistant .bubble {
  background: #fff;
  border: 1px solid #e8eaee;
  border-top-left-radius: 4px;
}

.content {
  font-family: inherit;
  white-space: pre-wrap;
  word-break: break-word;
}

/* 流式输出中的光标 */
.cursor {
  display: inline-block;
  width: 7px;
  height: 15px;
  margin-left: 2px;
  vertical-align: -2px;
  background: #16b8a6;
  animation: blink 0.9s steps(2) infinite;
}

@keyframes blink {
  50% {
    opacity: 0;
  }
}

.error-tip {
  text-align: center;
  color: #f56c6c;
  font-size: 13px;
  background: #fef0f0;
  border-radius: 8px;
  padding: 8px 12px;
}

/* ===== 回到底部按钮 ===== */
.back-bottom {
  position: absolute;
  bottom: 130px;
  left: 50%;
  transform: translateX(-50%);
  background: #fff;
  border: 1px solid #e4e7ed;
  color: #606266;
  border-radius: 999px;
  padding: 6px 16px;
  font-size: 13px;
  cursor: pointer;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
}

.back-bottom:hover {
  color: #16b8a6;
  border-color: #16b8a6;
}

/* ===== 知识库选择器 ===== */
.kb-selector {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  padding: 0 4px;
}

.kb-icon {
  font-size: 14px;
}

.kb-select {
  border: 1px solid #dcdfe6;
  border-radius: 8px;
  background: #fff;
  color: #606266;
  font-size: 13px;
  padding: 5px 10px;
  max-width: 420px;
  cursor: pointer;
  outline: none;
}

.kb-select:focus {
  border-color: #16b8a6;
}

.kb-mode-tag {
  font-size: 12px;
  color: #16b8a6;
  background: #e6f7f4;
  padding: 2px 10px;
  border-radius: 999px;
}

/* ===== 引用溯源 ===== */
.sources {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 10px;
  padding-top: 8px;
  border-top: 1px dashed #e8eaee;
}

.sources-label {
  font-size: 12px;
  color: #909399;
}

.source-chip {
  border: 1px solid #d7ede9;
  background: #f2faf8;
  color: #0e8a7b;
  border-radius: 999px;
  padding: 2px 10px;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s;
}

.source-chip:hover {
  background: #e6f7f4;
  border-color: #16b8a6;
}

.source-mask {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 50;
}

.source-modal {
  width: min(560px, 92vw);
  max-height: 70vh;
  overflow-y: auto;
  background: #fff;
  border-radius: 14px;
  padding: 16px 18px;
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.18);
}

.source-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.source-title {
  font-size: 14px;
  font-weight: 500;
  color: #303133;
}

.source-close {
  border: none;
  background: none;
  color: #909399;
  cursor: pointer;
  font-size: 15px;
}

.source-close:hover {
  color: #303133;
}

.source-sim {
  font-size: 12px;
  color: #16b8a6;
  margin: 6px 0 10px;
}

.source-snippet {
  font-size: 13px;
  line-height: 1.7;
  color: #606266;
  white-space: pre-wrap;
  background: #f7f8fa;
  border-radius: 8px;
  padding: 12px;
}

/* ===== 输入区 ===== */
.chat-input {
  padding-top: 12px;
}

.input-box {
  border: 1px solid #dcdfe6;
  border-radius: 14px;
  background: #fff;
  padding: 10px 12px 8px;
  transition: border-color 0.15s, box-shadow 0.15s;
}

.input-box:focus-within {
  border-color: #16b8a6;
  box-shadow: 0 0 0 3px rgba(22, 184, 166, 0.12);
}

.input-box textarea {
  width: 100%;
  border: none;
  outline: none;
  resize: none;
  font-size: 14px;
  font-family: inherit;
  line-height: 1.55;
  background: transparent;
  display: block;
}

.input-box textarea::placeholder {
  color: #b9bdc7;
}

.input-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 6px;
}

.hint {
  font-size: 12px;
  color: #b9bdc7;
}

.send-btn,
.stop-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 22px;
  border: none;
  border-radius: 10px;
  font-size: 14px;
  cursor: pointer;
  color: #fff;
  transition: all 0.15s;
}

.send-btn {
  background: #16b8a6;
}

.send-btn:hover:not(:disabled) {
  background: #12a292;
}

.send-btn:disabled {
  background: #c8eae4;
  cursor: not-allowed;
}

.stop-btn {
  background: #f56c6c;
}

.stop-btn:hover {
  background: #e25656;
}

.stop-icon {
  width: 10px;
  height: 10px;
  border-radius: 2px;
  background: #fff;
}
</style>
