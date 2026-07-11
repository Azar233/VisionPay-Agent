"""Import an already-split COCO dataset into the YOLO dataset layout.

Expected default source layout:
    source/
    |-- train2019/
    |-- val2019/
    |-- test2019/
    |-- instances_train2019.json
    |-- instances_val2019.json
    `-- instances_test2019.json
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.training.data_converter import DataConverter  # noqa: E402
from app.training.dataset_splitter import DatasetSplitter  # noqa: E402

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert an already-split COCO dataset to backend/datasets/vision_pay."
    )
    parser.add_argument("--source", required=True, help="Dataset root directory.")
    parser.add_argument(
        "--output",
        default=str(BACKEND_ROOT / "datasets" / "vision_pay"),
        help="Output YOLO dataset directory.",
    )
    parser.add_argument("--train-dir", default="train2019")
    parser.add_argument("--val-dir", default="val2019")
    parser.add_argument("--test-dir", default="test2019")
    parser.add_argument("--train-json", default="instances_train2019.json")
    parser.add_argument("--val-json", default="instances_val2019.json")
    parser.add_argument("--test-json", default="instances_test2019.json")
    parser.add_argument("--clean", action="store_true", help="Remove previous images/labels before writing.")
    return parser.parse_args()


def load_categories(json_file: Path) -> tuple[dict[int, int], list[str], dict[int, str]]:
    with json_file.open("r", encoding="utf-8") as f:
        coco_data: dict[str, Any] = json.load(f)

    categories = sorted(coco_data.get("categories", []), key=lambda item: item["id"])
    category_names = {int(category["id"]): str(category.get("name", category["id"])) for category in categories}
    if len(category_names) != len(categories):
        raise ValueError(f"duplicate category ids in {json_file}")
    class_mapping = {category["id"]: index for index, category in enumerate(categories)}
    class_names = [category.get("name", str(category["id"])) for category in categories]
    return class_mapping, class_names, category_names


def copy_split_images(image_dir: Path, output_image_dir: Path, output_label_dir: Path) -> int:
    output_image_dir.mkdir(parents=True, exist_ok=True)
    output_label_dir.mkdir(parents=True, exist_ok=True)

    copied = 0
    for image_file in sorted(image_dir.iterdir()):
        if not image_file.is_file() or image_file.suffix.lower() not in IMAGE_EXTENSIONS:
            continue

        shutil.copy2(image_file, output_image_dir / image_file.name)
        label_file = output_label_dir / f"{image_file.stem}.txt"
        if not label_file.exists():
            label_file.write_text("", encoding="utf-8")
        copied += 1

    return copied


def main() -> int:
    args = parse_args()
    source_dir = Path(args.source).resolve()
    output_dir = Path(args.output).resolve()

    split_config = {
        "train": (args.train_dir, args.train_json),
        "val": (args.val_dir, args.val_json),
        "test": (args.test_dir, args.test_json),
    }

    resolved: dict[str, tuple[Path, Path]] = {}
    for split, (dir_name, json_name) in split_config.items():
        image_dir = source_dir / dir_name
        json_file = source_dir / json_name
        if not image_dir.exists():
            print(f"[error] {split} image directory not found: {image_dir}")
            return 1
        if not json_file.exists():
            print(f"[error] {split} COCO JSON not found: {json_file}")
            return 1
        resolved[split] = (image_dir, json_file)

    if args.clean and output_dir.exists():
        for child_name in ["images", "labels"]:
            child = output_dir / child_name
            if child.exists():
                shutil.rmtree(child)

    class_mapping, class_names, train_categories = load_categories(resolved["train"][1])
    for split in ["val", "test"]:
        _, _, split_categories = load_categories(resolved[split][1])
        if split_categories != train_categories:
            missing = sorted(set(train_categories) - set(split_categories))
            extra = sorted(set(split_categories) - set(train_categories))
            renamed = sorted(
                category_id
                for category_id in set(train_categories) & set(split_categories)
                if train_categories[category_id] != split_categories[category_id]
            )
            print(
                f"[error] {split} categories differ from train: "
                f"missing={missing[:10]}, extra={extra[:10]}, renamed={renamed[:10]}"
            )
            return 1
    converter = DataConverter()

    print("Split COCO to YOLO conversion")
    total_images = 0
    total_annotations = 0
    for split, (image_dir, json_file) in resolved.items():
        label_dir = output_dir / "labels" / split
        image_output_dir = output_dir / "images" / split
        label_dir.mkdir(parents=True, exist_ok=True)

        stats = converter.convert_coco_to_yolo(
            json_file=json_file,
            output_dir=label_dir,
            class_mapping=class_mapping,
            image_dir=image_dir,
        )
        copied_images = copy_split_images(image_dir, image_output_dir, label_dir)
        total_images += copied_images
        total_annotations += stats["annotations"]

        print(
            f"  {split}: images={copied_images}, "
            f"labels={stats['converted']}, annotations={stats['annotations']}, "
            f"skipped_annotations={stats['skipped_annotations']}"
        )
        if stats["skipped_annotations"]:
            print(f"[error] {split} contains annotations that could not be converted")
            return 1

    yaml_path = DatasetSplitter.generate_data_yaml(
        output_dir=output_dir,
        class_names=class_names,
        dataset_path=output_dir,
    )

    print(f"  total images: {total_images}")
    print(f"  total annotations: {total_annotations}")
    print(f"  data.yaml: {yaml_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
