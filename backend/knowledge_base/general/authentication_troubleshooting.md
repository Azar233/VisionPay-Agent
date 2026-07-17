# 登录与 API 配置排查

## 管理端 401

401 通常表示 JWT 缺失、无效或过期。前端会清除登录状态并跳转 `/login`。重新登录后再发起请求，不要反复提交旧确认令牌。默认 Token 有效期由 `ACCESS_TOKEN_EXPIRE_MINUTES` 控制。

## DeepSeek 不可用

Agent 对话依赖 `backend/.env` 中的 `DEEPSEEK_API_KEY`、Base URL 和模型名。普通检测、数据集页面、训练页面和结算业务不应因为 DeepSeek 未配置而停止。修改 `.env` 后必须重启后端。

## Embedding 或知识库不可用

检查 `DASHSCOPE_API_KEY`、`EMBEDDING_MODEL=text-embedding-v4`、1024 维和 Chroma 路径。调用 `/api/knowledge/status` 查看配置与集合计数。Embedding 失败时 Hybrid 路由应降级到强意图和上下文规则；RAG、故障检索和长期记忆会返回不可用提示。

不要把密码、Token 或真实 API Key写入知识文档、长期记忆、聊天回复或 Git。
