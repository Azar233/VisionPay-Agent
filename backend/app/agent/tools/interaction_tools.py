"""Reusable structured input form for every domain Agent."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Literal
from uuid import uuid4

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.agent.tools.common import json_text
from app.agent.tools.form_templates import FORM_TEMPLATES


ScalarValue = str | int | float | bool
FieldType = Literal[
    "text",
    "textarea",
    "integer",
    "number",
    "select",
    "multiselect",
    "boolean",
    "date",
]
FormPurpose = Literal[
    "dataset.detail", "dataset.add_samples", "dataset.derive", "dataset.freeze",
    "dataset.archive", "dataset.delete_product", "dataset.delete_draft",
    "training.start", "training.stop", "training.status", "training.metrics",
    "training.set_default_model", "catalog.list_prices", "catalog.update_price",
    "catalog.clear_price", "detection.parameters", "knowledge.remember",
]


class FormOptionSpec(BaseModel):
    label: str = Field(min_length=1, max_length=100)
    value: ScalarValue


def _dataset_version_options() -> list[dict[str, Any]]:
    """Auto-fill dataset-version dropdowns server-side.

    Fields marked ``dynamic_options`` ship without static options, and some Agents
    (e.g. Catalog) have no tool to list dataset versions, so the LLM cannot always
    supply ``option_overrides``. The form builder resolves the options itself;
    failures leave the field empty instead of breaking form generation.
    """
    from app.database.session import SessionLocal
    from app.services.dataset_service import dataset_service

    db = SessionLocal()
    try:
        result = dataset_service.list(db, current_only=False, limit=50)
    finally:
        db.close()
    options: list[dict[str, Any]] = []
    for item in result.get("items", []):
        base_label = item.get("version") or item.get("name") or str(item["id"])
        label = f"{base_label}（{item.get('status', 'unknown')}）"
        if item.get("is_current"):
            label += " · 当前"
        options.append({"label": label, "value": item["id"]})
    return options


_DYNAMIC_OPTION_RESOLVERS = {
    "dataset_version_id": _dataset_version_options,
}


class FormVisibilitySpec(BaseModel):
    field: str = Field(pattern=r"^[a-zA-Z][a-zA-Z0-9_]{0,63}$")
    equals: ScalarValue


class FormFieldSpec(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(pattern=r"^[a-zA-Z][a-zA-Z0-9_]{0,63}$")
    label: str = Field(min_length=1, max_length=100)
    field_type: FieldType = Field(alias="type")
    required: bool = True
    default: Any = None
    placeholder: str = Field(default="", max_length=200)
    help_text: str = Field(default="", max_length=300)
    options: list[FormOptionSpec] = Field(default_factory=list, max_length=50)
    dynamic_options: bool = False
    minimum: float | None = None
    maximum: float | None = None
    step: float | None = Field(default=None, gt=0)
    visible_when: FormVisibilitySpec | None = None

    @model_validator(mode="after")
    def validate_options(self):
        if (
            self.field_type in {"select", "multiselect"}
            and not self.options
            and not self.dynamic_options
        ):
            raise ValueError("select/multiselect 字段必须提供 options")
        if self.minimum is not None and self.maximum is not None:
            if self.minimum > self.maximum:
                raise ValueError("minimum 不能大于 maximum")
        return self


class RequestUserInputFormArgs(BaseModel):
    purpose: FormPurpose
    known_values: dict[str, Any] = Field(default_factory=dict)
    option_overrides: dict[str, list[FormOptionSpec]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_overrides(self):
        fields = {field["name"]: field for field in FORM_TEMPLATES[self.purpose]["fields"]}
        for name in self.option_overrides:
            field = fields.get(name)
            if field is None or field["type"] not in {"select", "multiselect"}:
                raise ValueError(f"{name} 不是可覆盖选项的字段")
        return self


def build_interaction_tools(agent_name: str) -> list:
    def request_user_input_form(
        purpose: FormPurpose,
        known_values: dict[str, Any] | None = None,
        option_overrides: dict[str, list[dict[str, Any]]] | None = None,
    ) -> str:
        """缺少参数时按固定 purpose 展示标准表单；只能预填值或覆盖动态选项，不能自定义字段。"""
        request = RequestUserInputFormArgs.model_validate(
            {
                "purpose": purpose,
                "known_values": known_values or {},
                "option_overrides": option_overrides or {},
            }
        )
        if request.purpose.split(".", 1)[0] != agent_name:
            raise ValueError(f"{agent_name} Agent 无权生成 {request.purpose} 表单")
        template = deepcopy(FORM_TEMPLATES[request.purpose])
        fields = []
        for raw_field in template.pop("fields"):
            field = dict(raw_field)
            if field["name"] in request.known_values:
                field["default"] = request.known_values[field["name"]]
            if field["name"] in request.option_overrides:
                field["options"] = [
                    option.model_dump() for option in request.option_overrides[field["name"]]
                ]
            # LLM 未提供选项时，服务端兜底解析动态下拉（如数据集版本列表）。
            if field.get("dynamic_options") and not field.get("options"):
                resolver = _DYNAMIC_OPTION_RESOLVERS.get(field["name"])
                if resolver is not None:
                    try:
                        field["options"] = resolver()
                    except Exception:  # noqa: BLE001 - 选项缺失不应阻断表单生成
                        field["options"] = []
            fields.append(
                FormFieldSpec.model_validate(field).model_dump(
                    by_alias=True, exclude_none=True
                )
            )
        return json_text(
            {
                "form_type": "dynamic_parameters",
                "schema_version": 1,
                "template_version": 1,
                "form_id": uuid4().hex,
                "agent": agent_name,
                "purpose": request.purpose,
                "known_values": request.known_values,
                **template,
                "fields": fields,
            }
        )

    return [
        StructuredTool.from_function(
            request_user_input_form,
            name="request_user_input_form",
            args_schema=RequestUserInputFormArgs,
        )
    ]


def _field_is_visible(field: dict[str, Any], values: dict[str, Any]) -> bool:
    rule = field.get("visible_when")
    if not isinstance(rule, dict):
        return True
    return values.get(str(rule.get("field") or "")) == rule.get("equals")


def validate_form_submission(form: dict[str, Any], values: dict[str, Any]) -> dict[str, Any]:
    """Validate browser-submitted values against the persisted form schema."""
    if form.get("form_type") != "dynamic_parameters":
        raise ValueError("不支持的表单类型")
    if not isinstance(values, dict):
        raise ValueError("表单值格式无效")

    normalized: dict[str, Any] = {}
    raw_values = dict(values)
    for raw_field in form.get("fields") or []:
        field = FormFieldSpec.model_validate(raw_field)
        if not _field_is_visible(raw_field, raw_values):
            continue
        value = raw_values.get(field.name)
        missing = value is None or value == "" or value == []
        if missing:
            if field.required:
                raise ValueError(f"{field.label}为必填项")
            normalized[field.name] = None
            continue

        if field.field_type == "integer":
            if isinstance(value, bool):
                raise ValueError(f"{field.label}必须是整数")
            value = int(value)
        elif field.field_type == "number":
            if isinstance(value, bool):
                raise ValueError(f"{field.label}必须是数字")
            value = float(value)
        elif field.field_type == "boolean":
            if not isinstance(value, bool):
                raise ValueError(f"{field.label}必须是布尔值")
        elif field.field_type == "multiselect":
            if not isinstance(value, list):
                raise ValueError(f"{field.label}必须是列表")
        elif field.field_type not in {"select"}:
            value = str(value).strip()

        if field.field_type in {"integer", "number"}:
            if field.minimum is not None and value < field.minimum:
                raise ValueError(f"{field.label}不能小于 {field.minimum:g}")
            if field.maximum is not None and value > field.maximum:
                raise ValueError(f"{field.label}不能大于 {field.maximum:g}")
        if field.field_type in {"select", "multiselect"}:
            allowed = {option.value for option in field.options}
            selected = value if isinstance(value, list) else [value]
            if any(item not in allowed for item in selected):
                raise ValueError(f"{field.label}包含无效选项")
        normalized[field.name] = value
    return normalized
