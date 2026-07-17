# 训练任务状态

- `pending`：任务已登记，等待执行线程或远端资源。
- `running`：训练正在执行，数据集状态同步为 `training`。
- `completed`：训练流程正常结束，应该存在最终指标；可继续验证和登记模型。
- `failed`：执行异常，错误信息和日志用于定位原因。
- `cancelled`：经营者确认停止，未完成权重不保证可发布。

任务进度、当前 epoch 和状态必须调用 `get_training_status` 实时读取。逐 epoch 指标调用 `get_training_metrics`，日志由训练任务 UUID 对应的日志文件读取。不要把聊天中的旧进度当成当前状态。

同一数据集没有运行任务且没有活动模型时状态回到 `pending_train`；有运行任务时为 `training`；登记活动模型后为 `published`。任务完成与模型发布是两个阶段，不能混为一谈。
