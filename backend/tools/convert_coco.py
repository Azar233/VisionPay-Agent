"""Convert a COCO dataset directory into a YOLO dataset.

Expected source layout:
    source/
    ├── images/
    └── instances_train2019.json
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.training.data_converter import DataConverter  # noqa: E402
from app.training.dataset_splitter import DatasetSplitter  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Convert COCO annotations to YOLO dataset layout.")
    parser.add_argument("--source", required=True, help="COCO source directory containing images/ and JSON.")
    parser.add_argument(
        "--json",
        default="instances_train2019.json",
        help="COCO JSON file name or absolute path.",
    )
    parser.add_argument(
        "--output",
        default=str(BACKEND_ROOT / "datasets" / "vision_pay"),
        help="Output YOLO dataset directory.",
    )
    parser.add_argument("--train-ratio", type=float, default=0.8)
    parser.add_argument("--val-ratio", type=float, default=0.1)
    parser.add_argument("--test-ratio", type=float, default=0.1)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--clean", action="store_true", help="Remove previous images/labels before writing.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source_dir = Path(args.source).resolve()
    image_dir = source_dir / "images"
    json_file = Path(args.json)
    if not json_file.is_absolute():
        json_file = source_dir / json_file

    output_dir = Path(args.output).resolve()
    temp_label_dir = output_dir / "_tmp_labels"

    if not image_dir.exists():
        print(f"[error] image directory not found: {image_dir}")
        return 1
    if not json_file.exists():
        print(f"[error] COCO JSON not found: {json_file}")
        return 1

    if args.clean and output_dir.exists():
        for child_name in ["images", "labels", "_tmp_labels"]:
            child = output_dir / child_name
            if child.exists():
                shutil.rmtree(child)

    converter = DataConverter()
    conversion_stats = converter.convert_coco_to_yolo(
        json_file=json_file,
        output_dir=temp_label_dir,
        image_dir=image_dir,
    )

    splitter_stats = DatasetSplitter.organize_dataset(
        image_dir=image_dir,
        label_dir=temp_label_dir,
        output_dir=output_dir,
        train_ratio=args.train_ratio,
        val_ratio=args.val_ratio,
        test_ratio=args.test_ratio,
        seed=args.seed,
        clean=args.clean,
    )

    yaml_path = DatasetSplitter.generate_data_yaml(
        output_dir=output_dir,
        class_names=conversion_stats["class_names"],
        dataset_path=output_dir,
    )

    if temp_label_dir.exists():
        shutil.rmtree(temp_label_dir)

    print("COCO to YOLO conversion complete")
    print(f"  source images on disk: {conversion_stats['available_images']}")
    print(f"  json images: {conversion_stats['total_json_images']}")
    print(f"  labels converted: {conversion_stats['converted']}")
    print(f"  annotations converted: {conversion_stats['annotations']}")
    print(
        "  split: "
        f"train={splitter_stats['train']}, "
        f"val={splitter_stats['val']}, "
        f"test={splitter_stats['test']}"
    )
    print(f"  data.yaml: {yaml_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

