# Agent 能力边界与转交规则

系统有 Detection、Dataset、Training、Catalog、Knowledge 五个领域 Agent，Supervisor 只负责路由。Agent 数量和正式权限必须读取运行时固定能力工具，知识库只补充操作解释。

- Detection：处理聊天中的图片、ZIP 和视频附件，执行实时商品检测。
- Dataset：查询版本，预览派生、冻结、归档和删除，创建人工选图与绘框交接。
- Training：查询任务、状态和指标，预览启动、停止和切换默认模型。
- Catalog：实时查询价目表，预览改价与清价。
- Knowledge：解释平台流程，检索操作文档、故障案例和明确保存的长期偏好。

实时版本、价格、训练进度、检测结果必须调用领域工具，不能由 RAG 推断。缺少执行参数时调用标准表单；高风险写操作必须调用影响预览和确认卡。附件检测请求应交给 Detection；添加数据集样品应交给 Dataset 并转人工页面。
