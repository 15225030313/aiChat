/** 对话消息类型 —— 后续 RAG 的来源引用、Agent 的工具调用都会在这里扩展字段 */
export interface ChatMessage {
  role: 'user' | 'assistant' | 'system'
  content: string
  /** 推理模型（如 deepseek-reasoner）的思维链内容，前端单独渲染「思考过程」 */
  reasoning?: string
}

/** 知识库文档（管理页列表项） */
export interface KbDocument {
  id: number
  filename: string
  size_bytes: number
  chunk_count: number
  /** 第7周接入向量库后的同步标记，管理页先展示出来 */
  vectorized: 0 | 1
  created_at: string
}
