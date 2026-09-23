/**
 * Markdown 渲染层（阶段一第2-3周任务）
 *
 * 当前版本：每次增量到达后整段重渲染（简单可靠，面试可以讲清楚）。
 * 方案里的「防闪烁优化」（增量 diff 渲染 / 只重渲染最后一个未闭合块）是后续优化项。
 */

import { Marked } from 'marked'
import hljs from 'highlight.js'
import 'highlight.js/styles/github.css'

const marked = new Marked({
  renderer: {
    // 代码块高亮：AI 回答里最多的就是代码，面试演示的高频画面
    code({ text, lang }) {
      const language = lang && hljs.getLanguage(lang) ? lang : 'plaintext'
      const html = hljs.highlight(text, { language }).value
      const langLabel = lang ? `${lang}` : 'text'
      return `<div class="code-block"><div class="code-lang">${langLabel}</div><pre><code class="hljs language-${language}">${html}</code></pre></div>`
    },
  },
  breaks: true,
  gfm: true,
})

/** 把 AI 回答的 Markdown 文本渲染成 HTML（配合 v-html 使用） */
export function renderMarkdown(text: string): string {
  if (!text) return ''
  return marked.parse(text, { async: false })
}

/**
 * 渲染并把正文里的 [1] [2] 引用编号转成可点击角标（RAG 来源溯源）。
 * 注意要跳过代码块/行内代码——代码里出现 [0] 之类的数组下标是常态，不能误伤。
 */
export function renderMarkdownWithCitations(text: string): string {
  const html = renderMarkdown(text)
  if (!html) return ''
  // 按代码段切分：只有代码外的文本做替换
  return html
    .split(/(<code[\s\S]*?<\/code>)/g)
    .map((seg) =>
      seg.startsWith('<code')
        ? seg
        : seg.replace(/\[(\d{1,2})\]/g, '<sup class="cite-ref" data-idx="$1">[$1]</sup>'),
    )
    .join('')
}
