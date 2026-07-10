"""Create or update a DetectionScene from configurable CLI arguments.

Examples:
    python tools/create_scene.py \
        --name vision_pay \
        --display-name "VisionPay Retail Checkout" \
        --category retail \
        --data-yaml /data0/xshi/datasets/visionpay/yolo/vision_pay/data.yaml

    python tools/create_scene.py \
        --name demo_scene \
        --display-name "Demo Scene" \
        --category retail \
        --class-names "cola,chips,bread"
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import text

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.database.session import SessionLocal, engine  # noqa: E402
from app.entity.db_models import DetectionScene  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create or update a detection scene used by training and inference."
    )
    parser.add_argument("--name", required=True, help="Unique scene key, for example vision_pay.")
    parser.add_argument("--display-name", required=True, help="Human-readable scene name.")
    parser.add_argument("--description", default="", help="Scene description.")
    parser.add_argument(
        "--category",
        default="retail",
        help="Scene category, for example retail/agriculture/industry/medical.",
    )
    parser.add_argument(
        "--data-yaml",
        help="YOLO data.yaml. Class names are read from names when class inputs are omitted.",
    )
    parser.add_argument(
        "--class-names",
        help="Comma-separated class names, for example cola,chips,bread.",
    )
    parser.add_argument(
        "--class-file",
        help="Class file. Supports JSON list/dict or plain text with one class per line.",
    )
    parser.add_argument(
        "--class-names-cn",
        help="Optional JSON string or JSON file path for Chinese class-name mapping.",
    )
    parser.add_argument("--created-by", type=int, help="Optional creator user id.")
    parser.add_argument(
        "--inactive",
        action="store_true",
        help="Create/update the scene as inactive. Default is active.",
    )
    parser.add_argument(
        "--no-update",
        action="store_true",
        help="Fail if the scene already exists instead of updating it.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate inputs and print the pending change without writing to database.",
    )
    return parser.parse_args()


def _ordered_names(names: Any) -> list[str]:
    if isinstance(names, list):
        return [str(item) for item in names]
    if isinstance(names, dict):
        try:
            keys = sorted(names, key=lambda item: int(item))
        except (TypeError, ValueError):
            keys = sorted(names)
        return [str(names[key]) for key in keys]
    raise ValueError("names must be a list or dict")


def load_classes_from_data_yaml(path_value: str) -> list[str]:
    data_yaml = Path(path_value).expanduser().resolve()
    if not data_yaml.exists():
        raise FileNotFoundError(f"data.yaml not found: {data_yaml}")

    config = yaml.safe_load(data_yaml.read_text(encoding="utf-8"))
    if not isinstance(config, dict) or "names" not in config:
        raise ValueError(f"data.yaml has no names field: {data_yaml}")

    class_names = _ordered_names(config["names"])
    nc = config.get("nc")
    if nc is not None and int(nc) != len(class_names):
        raise ValueError(f"data.yaml class count mismatch: nc={nc}, names={len(class_names)}")
    return class_names


def load_classes_from_file(path_value: str) -> list[str]:
    path = Path(path_value).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"class file not found: {path}")

    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        return _ordered_names(data)

    class_names: list[str] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line and not line.startswith("#"):
            class_names.append(line)
    return class_names


def resolve_class_names(args: argparse.Namespace) -> list[str]:
    if args.class_file:
        class_names = load_classes_from_file(args.class_file)
    elif args.class_names:
        class_names = [item.strip() for item in args.class_names.split(",") if item.strip()]
    elif args.data_yaml:
        class_names = load_classes_from_data_yaml(args.data_yaml)
    else:
        raise ValueError("Provide one of --data-yaml, --class-names, or --class-file")

    if not class_names:
        raise ValueError("class_names cannot be empty")
    if len(class_names) != len(set(class_names)):
        duplicates = sorted({item for item in class_names if class_names.count(item) > 1})
        raise ValueError(f"duplicate class names: {duplicates}")
    return class_names


def resolve_class_names_cn(path_or_json: str | None) -> dict[str, str]:
    if not path_or_json:
        return {}

    maybe_path = Path(path_or_json).expanduser()
    if maybe_path.exists():
        data = json.loads(maybe_path.read_text(encoding="utf-8"))
    else:
        data = json.loads(path_or_json)

    if not isinstance(data, dict):
        raise ValueError("--class-names-cn must be a JSON object")
    return {str(key): str(value) for key, value in data.items()}


def main() -> int:
    args = parse_args()
    class_names = resolve_class_names(args)
    class_names_cn = resolve_class_names_cn(args.class_names_cn)
    is_active = not args.inactive

    if args.dry_run:
        print("dry_run=true action=not_checked")
        print(f"name={args.name}")
        print(f"display_name={args.display_name}")
        print(f"category={args.category}")
        print(f"is_active={is_active}")
        print(f"class_count={len(class_names)}")
        print(f"first_classes={class_names[:5]}")
        print(f"class_names_cn_count={len(class_names_cn)}")
        return 0

    db = SessionLocal()
    try:
        with engine.connect() as conn:
            conn.execute(text("select 1"))

        scene = db.query(DetectionScene).filter(DetectionScene.name == args.name).first()
        if scene is not None and args.no_update:
            raise ValueError(f"scene already exists: {args.name}")

        action = "update" if scene is not None else "create"
        if scene is None:
            scene = DetectionScene(name=args.name)
            db.add(scene)

        scene.display_name = args.display_name
        scene.description = args.description
        scene.category = args.category
        scene.class_names = class_names
        scene.class_names_cn = class_names_cn
        scene.is_active = is_active
        if args.created_by is not None:
            scene.created_by = args.created_by

        db.commit()
        db.refresh(scene)

        print(f"action={action}")
        print(f"scene_id={scene.id}")
        print(f"name={scene.name}")
        print(f"display_name={scene.display_name}")
        print(f"category={scene.category}")
        print(f"is_active={scene.is_active}")
        print(f"class_count={len(scene.class_names)}")
        print(f"first_classes={scene.class_names[:5]}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
