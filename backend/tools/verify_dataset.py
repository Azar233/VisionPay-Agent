#!/usr/bin/env python3
"""
YOLO 数据集验证脚本（增强版）

功能：
    对转换后的 YOLO 格式数据集进行全面验证，确保数据质量满足训练要求。

验证内容：
    1. 目录结构是否符合 YOLO 规范（images/train、images/val、labels/train、labels/val）
    2. 图像与标注文件是否一一对应（文件名匹配检查）
    3. 标注文件格式是否正确（每行必须为 5 个值：class_id x_center y_center width height）
    4. 类别 ID 是否有效（必须为整数且在 data.yaml 的类别范围内）
    5. 归一化坐标是否在 [0, 1] 范围内
    6. 统计各类别的标注数量和占比
    7. 类别不平衡检测和警告
    8. 边界框统计
    9. 每个 split（train/val/test）的详细统计
"""

from __future__ import annotations

import os
import sys
from collections import Counter
from pathlib import Path

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}


def load_yaml_classes(dataset_dir: Path) -> dict[int, str]:
    """加载 data.yaml 中的类别定义。"""

    yaml_path = dataset_dir / "data.yaml"
    classes: dict[int, str] = {}
    if not yaml_path.exists():
        return classes

    in_names = False
    with open(yaml_path, "r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.rstrip()
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue

            if stripped.startswith("names:"):
                in_names = True
                continue

            if in_names:
                if not raw_line.startswith((" ", "\t")):
                    break
                if ":" not in stripped:
                    continue
                key, value = stripped.split(":", 1)
                try:
                    class_id = int(key.strip())
                except ValueError:
                    continue
                class_name = value.strip().strip("'\"")
                classes[class_id] = class_name

    return classes


def _list_images(image_dir: Path) -> dict[str, Path]:
    if not image_dir.exists():
        return {}
    return {
        file.stem: file
        for file in image_dir.iterdir()
        if file.is_file() and file.suffix.lower() in IMAGE_EXTS
    }


def _list_labels(label_dir: Path) -> dict[str, Path]:
    if not label_dir.exists():
        return {}
    return {
        file.stem: file
        for file in label_dir.iterdir()
        if file.is_file() and file.suffix.lower() == ".txt"
    }


def verify_dataset(dataset_dir: str) -> dict:
    """验证 YOLO 数据集完整性，返回详细结果。"""

    dataset_path = Path(dataset_dir)
    class_names = load_yaml_classes(dataset_path)
    class_count = len(class_names)

    results = {
        "total_images": 0,
        "total_labels": 0,
        "total_annotations": 0,
        "missing_labels": [],
        "missing_images": [],
        "empty_labels": 0,
        "invalid_format": [],
        "class_distribution": Counter(),
        "split_stats": {},
        "bbox_stats": {
            "total": 0,
            "avg_width": 0.0,
            "avg_height": 0.0,
            "min_width": float("inf"),
            "min_height": float("inf"),
            "max_width": 0.0,
            "max_height": 0.0,
            "small_boxes": 0,
            "large_boxes": 0,
        },
        "class_names": class_names,
        "has_warnings": False,
    }

    if not (dataset_path / "data.yaml").exists():
        results["invalid_format"].append("缺少 data.yaml")

    for split in ["train", "val", "test"]:
        img_dir = dataset_path / "images" / split
        lbl_dir = dataset_path / "labels" / split

        if not img_dir.exists() and split != "test":
            results["invalid_format"].append(f"缺少目录: {img_dir}")
        if not lbl_dir.exists() and split != "test":
            results["invalid_format"].append(f"缺少目录: {lbl_dir}")

        image_files = _list_images(img_dir)
        label_files = _list_labels(lbl_dir)

        missing_labels = sorted(set(image_files) - set(label_files))
        missing_images = sorted(set(label_files) - set(image_files))

        results["missing_labels"].extend([f"{split}/{name}" for name in missing_labels])
        results["missing_images"].extend([f"{split}/{name}" for name in missing_images])
        results["total_images"] += len(image_files)
        results["total_labels"] += len(label_files)

        split_result = {
            "images": len(image_files),
            "labels": len(label_files),
            "annotations": 0,
            "missing_labels": len(missing_labels),
            "missing_images": len(missing_images),
        }

        bbox_widths: list[float] = []
        bbox_heights: list[float] = []

        for label_file in label_files.values():
            with open(label_file, "r", encoding="utf-8") as f:
                lines = [line.strip() for line in f.readlines() if line.strip()]

            if not lines:
                results["empty_labels"] += 1
                continue

            for line_num, line in enumerate(lines, start=1):
                parts = line.split()
                if len(parts) != 5:
                    results["invalid_format"].append(
                        f"{split}/{label_file.name}:{line_num} (字段数不是 5)"
                    )
                    continue

                try:
                    class_id = int(parts[0])
                except ValueError:
                    results["invalid_format"].append(
                        f"{split}/{label_file.name}:{line_num} (类别 ID 不是整数)"
                    )
                    continue

                try:
                    x_center, y_center, width, height = [float(v) for v in parts[1:]]
                except ValueError:
                    results["invalid_format"].append(
                        f"{split}/{label_file.name}:{line_num} (坐标值非浮点数)"
                    )
                    continue

                if class_count and class_id not in class_names:
                    results["invalid_format"].append(
                        f"{split}/{label_file.name}:{line_num} (类别 ID 超出范围)"
                    )
                    continue

                if not all(0 <= value <= 1 for value in [x_center, y_center, width, height]):
                    results["invalid_format"].append(
                        f"{split}/{label_file.name}:{line_num} (坐标值超出 [0, 1])"
                    )
                    continue

                if width <= 0 or height <= 0:
                    results["invalid_format"].append(
                        f"{split}/{label_file.name}:{line_num} (宽或高 <= 0)"
                    )
                    continue

                results["class_distribution"][class_id] += 1
                results["total_annotations"] += 1
                split_result["annotations"] += 1
                bbox_widths.append(width)
                bbox_heights.append(height)

        if bbox_widths:
            bbox_stats = results["bbox_stats"]
            bbox_stats["total"] += len(bbox_widths)
            bbox_stats["avg_width"] += sum(bbox_widths)
            bbox_stats["avg_height"] += sum(bbox_heights)
            bbox_stats["min_width"] = min(bbox_stats["min_width"], min(bbox_widths))
            bbox_stats["min_height"] = min(bbox_stats["min_height"], min(bbox_heights))
            bbox_stats["max_width"] = max(bbox_stats["max_width"], max(bbox_widths))
            bbox_stats["max_height"] = max(bbox_stats["max_height"], max(bbox_heights))
            bbox_stats["small_boxes"] += sum(
                1 for w, h in zip(bbox_widths, bbox_heights) if w * h < 0.001
            )
            bbox_stats["large_boxes"] += sum(
                1 for w, h in zip(bbox_widths, bbox_heights) if w * h > 0.5
            )

        results["split_stats"][split] = split_result

    bbox = results["bbox_stats"]
    if bbox["total"] > 0:
        bbox["avg_width"] /= bbox["total"]
        bbox["avg_height"] /= bbox["total"]
    else:
        bbox["min_width"] = 0.0
        bbox["min_height"] = 0.0

    return results


def print_report(results: dict):
    """打印格式化的验证报告。"""

    print("\n" + "=" * 70)
    print("              YOLO 数据集验证报告")
    print("=" * 70)

    print("\n  [总体统计]")
    print(f"    图像总数：{results['total_images']}")
    print(f"    标注文件数：{results['total_labels']}")
    print(f"    标注目标数：{results['total_annotations']}")
    print(f"    空标注文件：{results['empty_labels']}")
    if results["total_images"] > 0:
        print(f"    平均每图标注：{results['total_annotations'] / results['total_images']:.2f}")
    else:
        print("    平均每图标注：N/A")

    print("\n  [Split 统计]")
    for split in ["train", "val", "test"]:
        stats = results["split_stats"].get(split, {})
        print(
            f"    {split}: {stats.get('images', 0)} 图像, "
            f"{stats.get('labels', 0)} 标注, {stats.get('annotations', 0)} 目标"
        )

    if results["missing_labels"]:
        print(f"\n  [警告] 缺少标注文件 ({len(results['missing_labels'])} 个)：")
        for name in results["missing_labels"][:5]:
            print(f"    - {name}")
        if len(results["missing_labels"]) > 5:
            print(f"    ... 还有 {len(results['missing_labels']) - 5} 个")
        results["has_warnings"] = True

    if results["missing_images"]:
        print(f"\n  [警告] 缺少图像文件 ({len(results['missing_images'])} 个)：")
        for name in results["missing_images"][:5]:
            print(f"    - {name}")
        if len(results["missing_images"]) > 5:
            print(f"    ... 还有 {len(results['missing_images']) - 5} 个")
        results["has_warnings"] = True

    if results["invalid_format"]:
        print(f"\n  [错误] 格式错误 ({len(results['invalid_format'])} 处)：")
        for item in results["invalid_format"][:5]:
            print(f"    - {item}")
        if len(results["invalid_format"]) > 5:
            print(f"    ... 还有 {len(results['invalid_format']) - 5} 处")
        results["has_warnings"] = True

    print("\n  [类别分布]")
    class_distribution = results["class_distribution"]
    class_names = results["class_names"]
    if class_distribution:
        max_count = max(class_distribution.values())
        min_count = min(class_distribution.values())
        total = sum(class_distribution.values())
        imbalance_ratio = max_count / min_count if min_count > 0 else float("inf")

        for class_id, count in sorted(class_distribution.items()):
            percentage = (count / total) * 100 if total else 0
            class_name = class_names.get(class_id, f"class_{class_id}")
            display_name = class_name[:24]
            bar_length = int((count / max_count) * 40) if max_count > 0 else 0
            bar = "█" * bar_length + "░" * (40 - bar_length)
            print(f"    {class_id:3d}. {display_name:24s} {count:6d} 个 ({percentage:5.2f}%) {bar}")

        if imbalance_ratio > 10:
            print(f"\n  [警告] 类别严重不平衡！最大/最小类别比例 = {imbalance_ratio:.1f}:1")
            print("         建议：增加少数类样本或使用数据增强技术")
            results["has_warnings"] = True
        elif imbalance_ratio > 5:
            print(f"\n  [提示] 类别存在一定不平衡，比例 = {imbalance_ratio:.1f}:1")
    else:
        print("    无标注目标")

    print("\n  [边界框统计]")
    bbox = results["bbox_stats"]
    if bbox["total"] > 0:
        print(f"    边界框总数：{bbox['total']}")
        print(f"    平均宽度：{bbox['avg_width']:.4f}")
        print(f"    平均高度：{bbox['avg_height']:.4f}")
        print(f"    最小宽度：{bbox['min_width']:.4f}")
        print(f"    最小高度：{bbox['min_height']:.4f}")
        print(f"    最大宽度：{bbox['max_width']:.4f}")
        print(f"    最大高度：{bbox['max_height']:.4f}")
        print(
            f"    小目标（面积<0.001）：{bbox['small_boxes']} 个 "
            f"({bbox['small_boxes'] / bbox['total'] * 100:.1f}%)"
        )
        print(
            f"    大目标（面积>0.5）：{bbox['large_boxes']} 个 "
            f"({bbox['large_boxes'] / bbox['total'] * 100:.1f}%)"
        )
        if bbox["small_boxes"] / bbox["total"] > 0.3:
            print("\n  [提示] 小目标占比较高（>30%），建议检查图像分辨率与训练尺寸")
    else:
        print("    无边界框")

    print(f"\n{'─' * 70}")
    if results["has_warnings"]:
        print("  结果：⚠ 数据集存在问题或警告，请根据上述信息修复")
    else:
        print("  结果：✓ 数据集验证通过，可以开始训练")
    print(f"{'─' * 70}\n")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    DATASET_DIR = os.path.join(PROJECT_ROOT, "datasets", "vision_pay")

    if len(sys.argv) > 1:
        DATASET_DIR = sys.argv[1]

    if not os.path.exists(DATASET_DIR):
        print(f"[错误] 数据集目录不存在: {DATASET_DIR}")
        sys.exit(1)

    report = verify_dataset(DATASET_DIR)
    print_report(report)
    sys.exit(1 if report["invalid_format"] else 0)
