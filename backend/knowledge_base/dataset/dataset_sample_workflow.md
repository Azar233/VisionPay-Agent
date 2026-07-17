# 数据集添加样品流程

添加样品只允许针对 `draft`，聊天附件不会直接写入数据集。Dataset Agent 先收集参数，再创建有效期内的页面交接，经营者前往 `/datasets` 完成选图、绘框和提交。

## 新建商品训练图 `train_new`

必须填写商品名称、类别英文名和非负价格，条码可选。只添加 train 图片；每张图片必须至少绘制该商品的有效检测框。提交后创建稳定商品、类别映射和价格记录。

## 已有商品训练图 `train_existing`

必须选择当前草稿中已有的 `product_id`。只添加 train 图片，不新建商品或价格。不能使用其他数据集中的商品映射。

## val/test 结账场景 `scene`

上传 val 和/或 test 场景图。图片可以包含多个商品，每个检测框都必须关联当前版本中的已有商品。

交接状态依次为 `ready_for_handoff`、`selecting_files`、`annotating`、`submitting`，最终为 `completed`；也可能进入 `failed`、`cancelled` 或 `expired`。失败后可重新选择文件，过期交接必须重新从聊天发起。
