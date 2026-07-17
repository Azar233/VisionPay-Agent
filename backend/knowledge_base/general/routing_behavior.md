# 多 Agent 路由行为

正式模式为 `AGENT_ROUTING_MODE=hybrid`。每条普通管理消息会生成 Embedding 语义候选，但确定性强意图优先：检测附件、数据集生命周期与样品编辑、训练操作、价格操作和平台概念都有可审计规则。

带图片、ZIP 或视频且明确要求检测时必须进入 Detection，即使上一轮是 Knowledge 或 Dataset。Dataset 的未完成人工交接可以保持 Dataset 上下文，但聊天附件本身不能代替样品页面。结构化表单提交不重新路由，而是回到产生表单的 Agent。

会话上下文只用于延续缺少显式领域的新消息，不能覆盖本轮明确操作。Agent 职责、平台数量和通用概念由 Knowledge 解释；实时任务问题仍由对应领域 Agent 查询。

`embedding_only` 只用于评估向量路由，会跳过强意图、附件和上下文保护，不适合生产。测试结束必须恢复 `hybrid`。
