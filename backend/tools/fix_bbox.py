#!/usr/bin/env python3
"""Fix invalid or out-of-range YOLO label bounding boxes.

Rules:
    - Coordinates are clipped to [0, 1].
    - Lines with invalid field counts or non-numeric values are removed.
    - Boxes with width <= 0 or height <= 0 are removed.

Usage:
    cd backend
    python tools/fix_bbox.py
    python tools/fix_bbox.py datasets/vision_pay
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _clip(value: float) -> float:
    return max(0.0, min(1.0, value))


def fix_bbox_coordinates(label_dir: str | Path) -> dict[str, int]:
    """Fix one labels directory and return repair stats."""

    label_path = Path(label_dir)
    stats = {"fixed": 0, "deleted": 0, "total": 0, "files_affected": 0}

    if not label_path.exists():
        return stats

    for label_file in sorted(label_path.glob("*.txt")):
        original_lines = label_file.read_text(encoding="utf-8").splitlines()
        new_lines: list[str] = []
        file_fixed = 0
        file_deleted = 0

        for line in original_lines:
            line = line.strip()
            if not line:
                continue

            stats["total"] += 1
            parts = line.split()
            if len(parts) != 5:
                file_deleted += 1
                continue

            try:
                class_id = int(parts[0])
                x_center = float(parts[1])
                y_center = float(parts[2])
                width = float(parts[3])
                height = float(parts[4])
            except ValueError:
                file_deleted += 1
                continue

            clipped_x = _clip(x_center)
            clipped_y = _clip(y_center)
            clipped_width = _clip(width)
            clipped_height = _clip(height)

            if (
                clipped_x != x_center
                or clipped_y != y_center
                or clipped_width != width
                or clipped_height != height
            ):
                file_fixed += 1

            if clipped_width <= 0 or clipped_height <= 0:
                file_deleted += 1
                continue

            new_lines.append(
                f"{class_id} {clipped_x:.6f} {clipped_y:.6f} "
                f"{clipped_width:.6f} {clipped_height:.6f}"
            )

        if file_fixed > 0 or file_deleted > 0 or len(new_lines) != len([line for line in original_lines if line.strip()]):
            label_file.write_text("\n".join(new_lines) + ("\n" if new_lines else ""), encoding="utf-8")

        stats["fixed"] += file_fixed
        stats["deleted"] += file_deleted
        if file_fixed > 0 or file_deleted > 0:
            stats["files_affected"] += 1

    return stats


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    project_root = Path(__file__).resolve().parents[1]
    dataset_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else project_root / "datasets" / "vision_pay"
    if not dataset_dir.is_absolute():
        dataset_dir = Path.cwd() / dataset_dir

    print("=" * 70)
    print("      修复 YOLO 标注文件中的越界边界框")
    print("=" * 70)
    print(f"  数据集目录: {dataset_dir}")

    total_stats = {"fixed": 0, "deleted": 0, "total": 0, "files_affected": 0}
    for split in ["train", "val", "test"]:
        label_dir = dataset_dir / "labels" / split
        print(f"\n[处理 {split}]")
        if not label_dir.exists():
            print("  目录不存在，跳过")
            continue

        stats = fix_bbox_coordinates(label_dir)
        print(f"  检查: {stats['total']} 个边界框")
        print(f"  修复: {stats['fixed']} 个边界框")
        print(f"  删除: {stats['deleted']} 个无效边界框")
        print(f"  影响文件: {stats['files_affected']} 个")

        for key in total_stats:
            total_stats[key] += stats[key]

    print("\n" + "=" * 70)
    print("  修复完成！")
    print(f"  总计边界框: {total_stats['total']}")
    print(f"  修复越界: {total_stats['fixed']} 个")
    print(f"  删除无效: {total_stats['deleted']} 个")
    print(f"  影响文件: {total_stats['files_affected']} 个")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
