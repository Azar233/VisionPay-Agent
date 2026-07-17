# 数据集版本生命周期概览

VisionPay 的数据集状态为 `draft`、`pending_train`、`training`、`published` 和 `archived`。

- `draft`：可编辑草稿，可以添加样品、删除商品和修改版本内容。
- `pending_train`：已冻结且校验通过，等待训练；内容只读。
- `training`：至少有一个关联训练任务正在运行；内容只读。
- `published`：已有可用模型与该数据集关联；内容只读。
- `archived`：历史版本，不再作为可用训练版本展示。

冻结把草稿变为 `pending_train`。训练开始、结束以及模型登记会根据实时任务和模型记录同步为 `training`、`published` 或重新回到 `pending_train`。这些状态必须查询数据库，不能根据聊天历史推断。

修改已冻结版本前，应从 `pending_train`、`training`、`published` 或 `archived` 版本派生新草稿。添加样品必须转到数据集页面，由经营者选择图片并逐图绘制检测框；Agent 不能自动生成或确认标注。
