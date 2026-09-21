<script setup lang="ts">
/**
 * 知识库管理页：上传 → 列表 → 删除/清空
 * 第7周接入向量库后，这里将增加「向量化状态」列，问答页选择知识库即可开卷回答
 */
import { onMounted, ref } from 'vue'
import type { KbDocument } from '../types'
import { clearDocuments, deleteDocument, listDocuments, uploadDocument } from '../api/kb'

const documents = ref<KbDocument[]>([])
const loading = ref(false)
const error = ref('')
const uploading = ref(false)
const uploadPercent = ref(0)
const fileInput = ref<HTMLInputElement>()

async function refresh() {
  loading.value = true
  error.value = ''
  try {
    documents.value = await listDocuments()
  } catch (e) {
    error.value = e instanceof Error ? e.message : '加载失败'
  } finally {
    loading.value = false
  }
}

async function handleUpload(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = '' // 允许重复选择同一文件
  if (!file) return
  await doUpload(file)
}

async function doUpload(file: File) {
  error.value = ''
  uploading.value = true
  uploadPercent.value = 0
  try {
    await uploadDocument(file, (p) => (uploadPercent.value = p))
    await refresh()
  } catch (e) {
    error.value = e instanceof Error ? e.message : '上传失败'
  } finally {
    uploading.value = false
  }
}

async function handleDelete(id: number) {
  if (!confirm('确定删除该文档及其全部分片？')) return
  error.value = ''
  try {
    await deleteDocument(id)
    await refresh()
  } catch (e) {
    error.value = e instanceof Error ? e.message : '删除失败'
  }
}

async function handleClear() {
  if (!confirm('确定清空整个知识库？此操作不可恢复。')) return
  error.value = ''
  try {
    await clearDocuments()
    await refresh()
  } catch (e) {
    error.value = e instanceof Error ? e.message : '清空失败'
  }
}

function formatSize(bytes: number): string {
  return bytes > 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(1)} MB` : `${Math.ceil(bytes / 1024)} KB`
}

onMounted(refresh)
</script>

<template>
  <div class="kb-page">
    <div class="kb-toolbar">
      <div>
        <h2>知识库管理</h2>
        <p class="sub">上传的文档会被解析、分片后入库，供后续问答检索引用</p>
      </div>
      <div class="toolbar-actions">
        <button class="ghost-btn" :disabled="!documents.length" @click="handleClear">清空知识库</button>
        <button class="primary-btn" :disabled="uploading" @click="fileInput?.click()">
          {{ uploading ? `上传中 ${uploadPercent}%` : '上传文档' }}
        </button>
        <input
          ref="fileInput"
          type="file"
          accept=".pdf"
          hidden
          @change="handleUpload"
        />
      </div>
    </div>

    <div v-if="uploading" class="progress-track">
      <div class="progress-bar" :style="{ width: uploadPercent + '%' }" />
    </div>

    <div v-if="error" class="error-tip">{{ error }}</div>

    <div v-if="loading" class="empty-tip">加载中…</div>
    <div v-else-if="!documents.length" class="empty-tip">
      <p class="empty-title">知识库还是空的</p>
      <p class="sub">点击右上角「上传文档」，当前支持 PDF（≤10MB）</p>
    </div>

    <table v-else class="doc-table">
      <thead>
        <tr>
          <th>文档名</th>
          <th>大小</th>
          <th>分片数</th>
          <th>向量化</th>
          <th>上传时间</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="doc in documents" :key="doc.id">
          <td class="doc-name">{{ doc.filename }}</td>
          <td>{{ formatSize(doc.size_bytes) }}</td>
          <td>{{ doc.chunk_count }}</td>
          <td>
            <span class="badge" :class="doc.vectorized ? 'ok' : 'pending'">
              {{ doc.vectorized ? '已入库' : '待处理' }}
            </span>
          </td>
          <td>{{ doc.created_at.replace('T', ' ') }}</td>
          <td><button class="del-btn" @click="handleDelete(doc.id)">删除</button></td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.kb-page {
  max-width: 860px;
  margin: 0 auto;
  padding: 12px 16px;
  height: 100%;
  overflow-y: auto;
}

.kb-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 4px 16px;
  border-bottom: 1px solid #eef0f3;
}

.kb-toolbar h2 {
  font-size: 17px;
  font-weight: 500;
}

.sub {
  font-size: 13px;
  color: #909399;
  margin-top: 4px;
}

.toolbar-actions {
  display: flex;
  gap: 10px;
}

.ghost-btn,
.primary-btn {
  border-radius: 999px;
  padding: 7px 18px;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.15s;
}

.ghost-btn {
  border: 1px solid #dcdfe6;
  background: #fff;
  color: #606266;
}

.ghost-btn:hover:not(:disabled) {
  border-color: #f56c6c;
  color: #f56c6c;
}

.ghost-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.primary-btn {
  border: none;
  background: #16b8a6;
  color: #fff;
}

.primary-btn:hover:not(:disabled) {
  background: #12a292;
}

.progress-track {
  margin-top: 12px;
  height: 6px;
  border-radius: 3px;
  background: #eef0f3;
  overflow: hidden;
}

.progress-bar {
  height: 100%;
  background: #16b8a6;
  transition: width 0.2s;
}

.error-tip {
  margin-top: 12px;
  text-align: center;
  color: #f56c6c;
  font-size: 13px;
  background: #fef0f0;
  border-radius: 8px;
  padding: 8px 12px;
}

.empty-tip {
  margin-top: 80px;
  text-align: center;
  color: #909399;
}

.empty-title {
  font-size: 15px;
  color: #606266;
  margin-bottom: 6px;
}

.doc-table {
  width: 100%;
  margin-top: 16px;
  border-collapse: collapse;
  font-size: 13px;
}

.doc-table th,
.doc-table td {
  text-align: left;
  padding: 10px 12px;
  border-bottom: 1px solid #f0f2f5;
}

.doc-table th {
  color: #909399;
  font-weight: 400;
}

.doc-name {
  max-width: 260px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.badge {
  padding: 2px 10px;
  border-radius: 999px;
  font-size: 12px;
}

.badge.ok {
  background: #e6f7f4;
  color: #16b8a6;
}

.badge.pending {
  background: #faeeda;
  color: #ba7517;
}

.del-btn {
  border: none;
  background: none;
  color: #f56c6c;
  cursor: pointer;
  font-size: 13px;
}

.del-btn:hover {
  text-decoration: underline;
}
</style>
