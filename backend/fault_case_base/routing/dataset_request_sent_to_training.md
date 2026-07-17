# 数据集添加商品被错误路由到 Training Agent

## 现象

用户派生新数据集后要求“向新版本增加商品训练图”，回复来自 Training Agent。

## 根因

“训练图、模型”等词触发 Training 语义，但实际动作是修改数据集样品；旧 Training 上下文进一步放大了错误。

## 解决方案

数据集版本、添加商品、样品、标注和检测框等编辑意图应确定性路由 Dataset，并覆盖 Training Embedding 候选。缺少参数时展示 `dataset.add_samples` 固定表单，随后转人工页面。

## 验证

分别在新会话和上一轮为 Training 的会话输入同类请求，均应路由 Dataset，且不能直接启动训练。
