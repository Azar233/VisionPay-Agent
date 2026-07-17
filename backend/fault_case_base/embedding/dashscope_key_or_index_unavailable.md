# Embedding 或 Chroma 知识检索不可用

## 现象

Knowledge Agent 返回知识库不可用，路由事件显示 Embedding 降级，或 `/api/knowledge/status` 集合计数为 0。

## 根因

`backend/.env` 缺少 DashScope Key、模型/维度不一致、后端未重启、Chroma 路径错误或尚未构建索引。

## 解决方案

确认 `text-embedding-v4`、1024 维、Cosine 和 Chroma 路径，重启后端，再运行 `python tools/build_knowledge_index.py`。不要把真实 Key 写入 Git。

## 验证

状态接口显示 embedding_configured=true；`visionpay_knowledge`、`visionpay_fault_cases` 和 `visionpay_agent_routes` 计数大于 0，测试查询能召回对应来源。
