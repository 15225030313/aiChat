# 企业知识库AI问答系统

8年前端转型AI应用工程师的落地产出项目，当前为**阶段一骨架**：Vue3 + FastAPI 流式对话闭环。

## 技术栈

- **前端** `frontend/`：Vue3 + TypeScript + Vite，核心是 `useChat` Hook（流式状态管理）
- **后端** `backend/`：FastAPI 薄层，仅做 DeepSeek API 的流式中转代理（API Key 不落前端）

## 快速启动

### 1. 配置后端密钥

```bash
cd backend
cp .env.example .env
# 编辑 .env，填入你的 DeepSeek API Key（https://platform.deepseek.com 申请）
```

### 2. 启动后端（端口 8000）

```bash
cd backend
pip install -r requirements.txt
python -m uvicorn main:app --reload --port 8000
```

### 3. 启动前端（端口 5173）

```bash
cd frontend
npm install
npm run dev
```

浏览器打开 http://localhost:5173 即可对话。

## 目录结构

```
ai-knowledge-qa/
├── backend/
│   ├── main.py              # FastAPI 入口：/api/chat 流式代理、/api/health
│   ├── requirements.txt
│   ├── .env.example         # 密钥配置模板
│   └── .env                 # 本地密钥（不入库，需自行创建）
└── frontend/
    └── src/
        ├── api/chat.ts          # 流式请求层：ReadableStream + SSE 解析 + TTFT 埋点
        ├── composables/useChat.ts  # 通用对话 Hook（未来开源组件库的核心雏形）
        ├── utils/markdown.ts    # Markdown 流式渲染 + highlight.js 代码高亮
        ├── types.ts             # 消息类型（后续扩展来源引用、工具调用字段）
        └── App.vue              # 对话界面（含代码块高亮样式）
```

## 学习路线对照（阶段一）

- 第1周：LLM 基础 + DeepSeek API 调用规范 → 本骨架的 backend 代理层
- 第2-3周：流式核心（ReadableStream/SSE/buffer/abort） → `src/api/chat.ts`
- 第2-3周：useChat Hook + Markdown 流式渲染 → `src/composables/useChat.ts`（Markdown 渲染待补）
- 第4周：FastAPI 薄层细节 → `backend/main.py`
- 第5周：抽离开源组件库 vue-ai-chat

## 注意事项

- `.env` 含密钥，**永远不要提交到 Git**（已建议加入 .gitignore）
- 无 API Key 时 `/api/chat` 会返回明确错误提示，前端能正常展示兜底信息
