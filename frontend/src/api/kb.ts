/**
 * 知识库管理 API 层
 * 上传用 XMLHttpRequest 而非 fetch：需要 onprogress 上传进度（fetch 目前不支持上传进度）
 */

import type { KbDocument } from '../types'

export async function listDocuments(): Promise<KbDocument[]> {
  const res = await fetch('/api/kb/documents')
  if (!res.ok) throw new Error(`获取文档列表失败（${res.status}）`)
  return res.json()
}

export async function deleteDocument(id: number): Promise<void> {
  const res = await fetch(`/api/kb/documents/${id}`, { method: 'DELETE' })
  if (!res.ok) throw new Error(`删除失败（${res.status}）`)
}

export async function clearDocuments(): Promise<void> {
  const res = await fetch('/api/kb/documents', { method: 'DELETE' })
  if (!res.ok) throw new Error(`清空失败（${res.status}）`)
}

/** 手动向量化：补处理上传时向量化失败/历史遗留的「待处理」文档 */
export async function vectorizeDocument(id: number): Promise<void> {
  const res = await fetch(`/api/kb/vectorize/${id}`, { method: 'POST' })
  if (!res.ok) {
    let detail = `向量化失败（${res.status}）`
    try {
      const body = await res.json()
      if (body?.detail) detail = body.detail
    } catch {
      /* 忽略 */
    }
    throw new Error(detail)
  }
}

export function uploadDocument(
  file: File,
  onProgress?: (percent: number) => void,
): Promise<{ id: number; filename: string; chunk_count: number }> {
  return new Promise((resolve, reject) => {
    const form = new FormData()
    form.append('file', file)

    const xhr = new XMLHttpRequest()
    xhr.open('POST', '/api/kb/upload')
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress) {
        onProgress(Math.round((e.loaded / e.total) * 100))
      }
    }
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(JSON.parse(xhr.responseText))
      } else {
        try {
          reject(new Error(JSON.parse(xhr.responseText).detail || `上传失败（${xhr.status}）`))
        } catch {
          reject(new Error(`上传失败（${xhr.status}）`))
        }
      }
    }
    xhr.onerror = () => reject(new Error('网络异常，上传失败'))
    xhr.send(form)
  })
}
