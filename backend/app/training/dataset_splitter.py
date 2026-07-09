"""Dataset splitting and YOLO data.yaml generation utilities."""

from __future__ import annotations

import random
import shutil
from pathlib import Path
from typing import Any


class DatasetSplitter:
    """Organize image/label pairs into YOLO train, val, and test splits."""

    IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}

    @classmethod
    def _image_files(cls, image_dir: Path) -> list[Path]:
        return sorted(
            item
            for item in image_dir.iterdir()
            if item.is_file() and item.suffix.lower() in cls.IMAGE_EXTENSIONS
        )

    @staticmethod
    def _validate_ratios(train_ratio: float, val_ratio: float, test_ratio: float) -> None:
        total = train_ratio + val_ratio + test_ratio
        if abs(total - 1.0) > 1e-6:
            raise ValueError("train_ratio + val_ratio + test_ratio must equal 1.0")
        if min(train_ratio, val_ratio, test_ratio) < 0:
            raise ValueError("split ratios must be non-negative")

    @classmethod
    def organize_dataset(
        cls,
        image_dir: str | Path,
        label_dir: str | Path,
        output_dir: str | Path,
        train_ratio: float = 0.8,
        val_ratio: float = 0.1,
        test_ratio: float = 0.1,
        seed: int = 42,
        clean: bool = False,
    ) -> dict[str, Any]:
        """Copy paired images and labels into YOLO split directories."""

        cls._validate_ratios(train_ratio, val_ratio, test_ratio)
        src_img_dir = Path(image_dir)
        src_lbl_dir = Path(label_dir)
        out_dir = Path(output_dir)

        if clean:
            for child in ["images", "labels"]:
                target = out_dir / child
                if target.exists():
                    shutil.rmtree(target)

        images = cls._image_files(src_img_dir)
        random.Random(seed).shuffle(images)

        train_end = int(len(images) * train_ratio)
        val_end = train_end + int(len(images) * val_ratio)
        split_map = {
            "train": images[:train_end],
            "val": images[train_end:val_end],
            "test": images[val_end:],
        }

        stats: dict[str, Any] = {
            "total_images": len(images),
            "train": 0,
            "val": 0,
            "test": 0,
            "missing_labels": [],
        }

        for split_name, split_images in split_map.items():
            dst_img_dir = out_dir / "images" / split_name
            dst_lbl_dir = out_dir / "labels" / split_name
            dst_img_dir.mkdir(parents=True, exist_ok=True)
            dst_lbl_dir.mkdir(parents=True, exist_ok=True)

            for image_file in split_images:
                label_file = src_lbl_dir / f"{image_file.stem}.txt"
                shutil.copy2(image_file, dst_img_dir / image_file.name)
                if label_file.exists():
                    shutil.copy2(label_file, dst_lbl_dir / label_file.name)
                else:
                    (dst_lbl_dir / f"{image_file.stem}.txt").write_text("", encoding="utf-8")
                    stats["missing_labels"].append(image_file.name)
                stats[split_name] += 1

        return stats

    @staticmethod
    def generate_data_yaml(
        output_dir: str | Path,
        class_names: list[str],
        dataset_path: str | Path | None = None,
    ) -> str:
        """Generate a YOLO data.yaml file."""

        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        path_value = Path(dataset_path).resolve() if dataset_path is not None else out_dir.resolve()

        lines = [
            f"path: {path_value.as_posix()}",
            "train: images/train",
            "val: images/val",
            "test: images/test",
            f"nc: {len(class_names)}",
            "names:",
        ]
        for index, name in enumerate(class_names):
            safe_name = str(name).replace('"', '\\"')
            lines.append(f'  {index}: "{safe_name}"')

        yaml_path = out_dir / "data.yaml"
        yaml_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return str(yaml_path)

