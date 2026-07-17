# 参数表单数字输入导致页面运行出错

## 现象

在数据集 ID 等数字字段输入时页面崩溃，控制台出现 `[InputNumber] min should not be greater than max`。

## 根因

后端把未设置的 `maximum` 序列化为 null，前端仍把 null 传给 Element Plus；组件将其解释为最大值 0，与 `min=1` 冲突。

## 解决方案

后端序列化表单时排除 None；前端只在值为有限数字时传递 min、max 和 step。固定模板中的动态下拉字段不要退化为错误的数字输入。

## 验证

真实 Element Plus 数字输入可输入正整数，控制台无 min/max 警告，表单能够提交并通过后端校验。
