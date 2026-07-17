# Training 表单的数据集版本无法选择

## 现象

Agent 能列出可训练数据集，但训练问询框中的版本 ID 不能输入，或动态选项覆盖时报“不是可覆盖选项的字段”。

## 根因

模板把 `dataset_version_id` 定义为普通整数，而 Training Agent 尝试通过 `option_overrides` 注入可用版本。

## 解决方案

把字段固定为 `select` 并标记 `dynamic_options=true`；选项 value 保留数字 ID，Agent 只覆盖选项列表和已知值，不自定义字段。

## 验证

同一训练请求始终显示相同表单结构，下拉列出可用数据集，选择后提交值为整数并返回 Training Agent。
