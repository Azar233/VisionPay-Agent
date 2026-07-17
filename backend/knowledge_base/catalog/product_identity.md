# 商品稳定身份与类别映射

`product_id` 是数据库中的稳定商品身份，用于价格、条码和跨版本关联。`product_key` 是业务稳定键；`class_name` 是模型类别英文名；`class_index` 是某个数据集版本中的从 0 开始类别位置；`category_id` 兼容旧价格映射。

同一商品在不同数据集版本中的 `class_index` 可能不同。删除类别会重排后续索引，因此长期价格和审计不能只保存 `class_index`。Catalog 操作必须同时提供 `dataset_version_id` 和 `product_id`，先确认商品属于该版本。

查询时可按商品 ID、product_key、类别名、显示名称或条码搜索。名称可能重复，已知 `product_id` 时优先使用稳定 ID；不知道时先实时列出候选，不要由 Agent猜测。
