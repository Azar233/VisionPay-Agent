# Dataset Agent 只能找到部分数据集版本

## 现象

数据库中存在多个版本，但 Agent 只返回一个版本，按名称继续询问时声称其他版本不存在。

## 根因

把“当前版本”查询结果当成全部版本，或错误继承 scene/status 筛选；也可能混淆版本号和数据库 ID。

## 解决方案

调用 `list_dataset_versions` 并设置 `current_only=false`，默认不加状态筛选，返回稳定 ID、版本号、场景和状态。查看详情再使用明确 dataset ID。

## 验证

Agent 返回的 total 与数据库版本总数一致，所有状态的版本都可按 ID 查询详情。
