"""Canonical form schemas keyed by business operation purpose."""

from __future__ import annotations

from typing import Any


def field(name: str, label: str, field_type: str, **kwargs) -> dict[str, Any]:
    return {"name": name, "label": label, "type": field_type, **kwargs}


MODEL_OPTIONS = [
    {"label": value, "value": value}
    for value in ("yolov11n", "yolov11s", "yolov11m", "yolov11l", "yolov11x")
]
OPTIMIZER_OPTIONS = [
    {"label": value, "value": value} for value in ("SGD", "Adam", "AdamW", "auto")
]
CURRENCY_OPTIONS = [
    {"label": "人民币（CNY）", "value": "CNY"},
    {"label": "美元（USD）", "value": "USD"},
]


FORM_TEMPLATES: dict[str, dict[str, Any]] = {
    "dataset.detail": {
        "title": "查看数据集版本详情",
        "description": "填写目标数据集版本 ID。",
        "submit_label": "查询版本详情",
        "fields": [field("dataset_id", "数据集版本 ID", "integer", minimum=1)],
    },
    "dataset.add_samples": {
        "title": "补充样品信息",
        "description": "填写后将创建人工选图与绘框交接，不会直接写入样品。",
        "submit_label": "继续创建交接",
        "fields": [
            field("dataset_id", "草稿数据集 ID", "integer", minimum=1),
            field(
                "mode",
                "添加模式",
                "select",
                default="train_new",
                options=[
                    {"label": "新建商品训练图", "value": "train_new"},
                    {"label": "已有商品训练图", "value": "train_existing"},
                    {"label": "val/test 结账场景", "value": "scene"},
                ],
            ),
            field("name", "商品名称", "text", visible_when={"field": "mode", "equals": "train_new"}),
            field("class_name", "类别英文名", "text", visible_when={"field": "mode", "equals": "train_new"}),
            field("unit_price", "价格（元）", "number", minimum=0, step=0.01, visible_when={"field": "mode", "equals": "train_new"}),
            field("barcode", "条码", "text", required=False, visible_when={"field": "mode", "equals": "train_new"}),
            field("existing_product_id", "已有商品 ID", "integer", minimum=1, visible_when={"field": "mode", "equals": "train_existing"}),
        ],
    },
    "dataset.derive": {
        "title": "派生数据集版本",
        "description": "填写父版本与新草稿版本信息。",
        "submit_label": "生成派生预览",
        "fields": [
            field("dataset_id", "父数据集版本 ID", "integer", minimum=1),
            field("version", "新版本号", "text"),
            field("name", "版本名称", "text"),
            field("description", "版本说明", "textarea", required=False),
        ],
    },
    "dataset.freeze": {
        "title": "冻结数据集版本",
        "description": "冻结后版本将变为只读。",
        "submit_label": "生成冻结预览",
        "fields": [
            field("dataset_id", "草稿数据集 ID", "integer", minimum=1),
            field("check_filesystem", "检查文件系统", "boolean", default=False, required=False),
        ],
    },
    "dataset.archive": {
        "title": "归档数据集版本",
        "description": "填写需要归档的数据集版本 ID。",
        "submit_label": "生成归档预览",
        "fields": [field("dataset_id", "数据集版本 ID", "integer", minimum=1)],
    },
    "dataset.delete_product": {
        "title": "删除商品样品",
        "description": "删除会影响图片、标注和类别编号。",
        "submit_label": "生成删除预览",
        "fields": [
            field("dataset_id", "草稿数据集 ID", "integer", minimum=1),
            field("product_id", "商品 ID", "integer", minimum=1),
            field("deactivate_product", "同时停用商品", "boolean", default=True, required=False),
        ],
    },
    "dataset.delete_draft": {
        "title": "删除数据集草稿",
        "description": "填写需要永久删除的草稿 ID。",
        "submit_label": "生成删除预览",
        "fields": [field("dataset_id", "草稿数据集 ID", "integer", minimum=1)],
    },
    "training.start": {
        "title": "配置训练任务",
        "description": "确认完整训练参数后生成启动影响预览。",
        "submit_label": "生成训练预览",
        "fields": [
            field("scene_id", "场景 ID", "integer", minimum=1),
            field("dataset_version_id", "数据集版本", "select", dynamic_options=True),
            field("model_name", "基础模型", "select", default="yolov11n", options=MODEL_OPTIONS),
            field("epochs", "训练轮数（epochs）", "integer", default=100, minimum=1, maximum=10000),
            field("img_size", "图像尺寸", "integer", default=640, minimum=32, maximum=4096, step=32),
            field("batch_size", "批次大小", "integer", default=16, minimum=1, maximum=1024),
            field("device", "训练设备", "text", default="cpu"),
            field("optimizer", "优化器", "select", default="SGD", options=OPTIMIZER_OPTIONS),
            field("lr0", "初始学习率", "number", default=0.01, minimum=0.000001, maximum=1, step=0.001),
        ],
    },
    "training.stop": {
        "title": "停止训练任务",
        "description": "填写需要停止的训练任务 ID。",
        "submit_label": "生成停止预览",
        "fields": [field("task_id", "训练任务 ID", "integer", minimum=1)],
    },
    "training.status": {
        "title": "查询训练状态",
        "description": "填写训练任务 ID。",
        "submit_label": "查询训练状态",
        "fields": [field("task_id", "训练任务 ID", "integer", minimum=1)],
    },
    "training.metrics": {
        "title": "查询训练指标",
        "description": "填写训练任务 ID。",
        "submit_label": "查询训练指标",
        "fields": [field("task_id", "训练任务 ID", "integer", minimum=1)],
    },
    "training.set_default_model": {
        "title": "切换默认模型",
        "description": "填写要设为默认的模型版本 ID。",
        "submit_label": "生成切换预览",
        "fields": [field("model_version_id", "模型版本 ID", "integer", minimum=1)],
    },
    "catalog.list_prices": {
        "title": "查询数据集价目表",
        "description": "选择数据集版本并设置可选筛选条件。",
        "submit_label": "查询价目表",
        "fields": [
            field("dataset_version_id", "数据集版本", "select", dynamic_options=True),
            field("keyword", "商品关键词", "text", required=False),
            field("unpriced_only", "仅查看未定价商品", "boolean", default=False, required=False),
        ],
    },
    "catalog.update_price": {
        "title": "修改商品价格",
        "description": "填写商品定位信息和目标价格；已知内容会自动预填。",
        "submit_label": "生成改价预览",
        "fields": [
            field("dataset_version_id", "数据集版本", "select", dynamic_options=True),
            field("product_id", "商品 ID（product_id）", "integer", required=False, minimum=1, help_text="知道商品 ID 时填写，可避免同名商品歧义。"),
            field("product_keyword", "商品关键词", "text", required=False, help_text="不知道商品 ID 时填写名称或条码，由 Agent 先查询定位。"),
            field("unit_price", "目标价格", "number", minimum=0, step=0.01),
            field("currency", "币种", "select", default="CNY", options=CURRENCY_OPTIONS),
        ],
    },
    "catalog.clear_price": {
        "title": "清除商品价格",
        "description": "填写数据集版本与商品标识。",
        "submit_label": "生成清除预览",
        "fields": [
            field("dataset_version_id", "数据集版本", "select", dynamic_options=True),
            field("product_id", "商品 ID（product_id）", "integer", minimum=1),
        ],
    },
    "detection.parameters": {
        "title": "配置检测参数",
        "description": "文件仍通过聊天附件上传。",
        "submit_label": "应用参数并继续",
        "fields": [field("confidence", "置信度阈值", "number", default=0.25, minimum=0.05, maximum=0.95, step=0.05)],
    },
    "knowledge.remember": {
        "title": "保存长期偏好",
        "description": "只保存稳定偏好，不要填写密码、Token、价格或临时任务状态。",
        "submit_label": "保存偏好",
        "fields": [
            field("content", "需要记住的内容", "textarea"),
            field("category", "类别", "select", default="preference", options=[
                {"label": "经营偏好", "value": "preference"},
                {"label": "稳定事实", "value": "fact"},
            ]),
        ],
    },
}


FORM_PURPOSES = tuple(FORM_TEMPLATES)
