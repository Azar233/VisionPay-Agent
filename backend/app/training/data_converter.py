"""Dataset annotation converters.

The converters normalize VOC, COCO, and LabelMe annotations into YOLO TXT
format: class_id x_center y_center width height, with coordinates in [0, 1].
"""

from __future__ import annotations

import json
import logging
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class DataConverter:
    """Convert common detection annotation formats to YOLO TXT labels."""

    @staticmethod
    def _clip(value: float, min_value: float, max_value: float) -> float:
        return max(min_value, min(value, max_value))

    @classmethod
    def _bbox_to_yolo(
        cls,
        x_min: float,
        y_min: float,
        box_width: float,
        box_height: float,
        image_width: float,
        image_height: float,
    ) -> tuple[float, float, float, float] | None:
        if image_width <= 0 or image_height <= 0:
            return None

        x1 = cls._clip(x_min, 0, image_width)
        y1 = cls._clip(y_min, 0, image_height)
        x2 = cls._clip(x_min + box_width, 0, image_width)
        y2 = cls._clip(y_min + box_height, 0, image_height)

        clipped_width = x2 - x1
        clipped_height = y2 - y1
        if clipped_width <= 0 or clipped_height <= 0:
            return None

        x_center = (x1 + clipped_width / 2) / image_width
        y_center = (y1 + clipped_height / 2) / image_height
        norm_width = clipped_width / image_width
        norm_height = clipped_height / image_height
        return x_center, y_center, norm_width, norm_height

    @staticmethod
    def _format_yolo_line(class_id: int, bbox: tuple[float, float, float, float]) -> str:
        x_center, y_center, width, height = bbox
        return f"{class_id} {x_center:.6f} {y_center:.6f} {width:.6f} {height:.6f}"

    def convert_voc_to_yolo(
        self,
        xml_dir: str | Path,
        output_dir: str | Path,
        class_mapping: dict[str, int],
    ) -> dict[str, Any]:
        """Convert Pascal VOC XML files to YOLO TXT labels."""

        xml_path = Path(xml_dir)
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)

        stats: dict[str, Any] = {
            "total": 0,
            "converted": 0,
            "skipped": 0,
            "annotations": 0,
            "unknown_classes": defaultdict(int),
        }

        for xml_file in sorted(xml_path.glob("*.xml")):
            stats["total"] += 1
            try:
                root = ET.parse(xml_file).getroot()
                size = root.find("size")
                if size is None:
                    stats["skipped"] += 1
                    continue

                image_width = float(size.findtext("width", "0"))
                image_height = float(size.findtext("height", "0"))
                lines: list[str] = []

                for obj in root.findall("object"):
                    class_name = obj.findtext("name", "").strip()
                    if class_name not in class_mapping:
                        stats["unknown_classes"][class_name] += 1
                        continue

                    bbox = obj.find("bndbox")
                    if bbox is None:
                        continue

                    x_min = float(bbox.findtext("xmin", "0"))
                    y_min = float(bbox.findtext("ymin", "0"))
                    x_max = float(bbox.findtext("xmax", "0"))
                    y_max = float(bbox.findtext("ymax", "0"))
                    yolo_bbox = self._bbox_to_yolo(
                        x_min,
                        y_min,
                        x_max - x_min,
                        y_max - y_min,
                        image_width,
                        image_height,
                    )
                    if yolo_bbox is None:
                        continue
                    lines.append(self._format_yolo_line(class_mapping[class_name], yolo_bbox))

                (out_path / f"{xml_file.stem}.txt").write_text("\n".join(lines), encoding="utf-8")
                stats["converted"] += 1
                stats["annotations"] += len(lines)
            except Exception as exc:  # noqa: BLE001 - keep batch conversion resilient.
                logger.warning("Skipping VOC file %s: %s", xml_file, exc)
                stats["skipped"] += 1

        stats["unknown_classes"] = dict(stats["unknown_classes"])
        return stats

    def convert_coco_to_yolo(
        self,
        json_file: str | Path,
        output_dir: str | Path,
        class_mapping: dict[int, int] | None = None,
        image_dir: str | Path | None = None,
    ) -> dict[str, Any]:
        """Convert COCO JSON annotations to YOLO TXT labels.

        If image_dir is provided, only images physically present in that
        directory are converted. This is useful for Kaggle subsets that ship a
        full COCO annotation file but only a small image subset.
        """

        json_path = Path(json_file)
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)

        with json_path.open("r", encoding="utf-8") as f:
            coco_data = json.load(f)

        categories = sorted(coco_data.get("categories", []), key=lambda item: item["id"])
        if class_mapping is None:
            class_mapping = {category["id"]: index for index, category in enumerate(categories)}

        class_names = [category.get("name", str(category["id"])) for category in categories]
        images = coco_data.get("images", [])
        annotations = coco_data.get("annotations", [])

        available_files: set[str] | None = None
        if image_dir is not None:
            image_path = Path(image_dir)
            available_files = {item.name for item in image_path.iterdir() if item.is_file()}

        image_by_id: dict[int, dict[str, Any]] = {}
        for image in images:
            file_name = image.get("file_name")
            if not file_name:
                continue
            if available_files is not None and Path(file_name).name not in available_files:
                continue
            image_by_id[image["id"]] = image

        annotations_by_image: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for annotation in annotations:
            image_id = annotation.get("image_id")
            if image_id in image_by_id:
                annotations_by_image[image_id].append(annotation)

        stats: dict[str, Any] = {
            "total_json_images": len(images),
            "available_images": len(image_by_id),
            "converted": 0,
            "annotations": 0,
            "skipped_annotations": 0,
            "class_mapping": class_mapping,
            "class_names": class_names,
        }

        for image_id, image in sorted(image_by_id.items(), key=lambda item: item[1]["file_name"]):
            width = float(image.get("width", 0))
            height = float(image.get("height", 0))
            lines: list[str] = []

            for annotation in annotations_by_image.get(image_id, []):
                category_id = annotation.get("category_id")
                bbox = annotation.get("bbox") or []
                if category_id not in class_mapping or len(bbox) != 4:
                    stats["skipped_annotations"] += 1
                    continue

                yolo_bbox = self._bbox_to_yolo(
                    float(bbox[0]),
                    float(bbox[1]),
                    float(bbox[2]),
                    float(bbox[3]),
                    width,
                    height,
                )
                if yolo_bbox is None:
                    stats["skipped_annotations"] += 1
                    continue

                lines.append(self._format_yolo_line(class_mapping[category_id], yolo_bbox))

            label_name = f"{Path(image['file_name']).stem}.txt"
            (out_path / label_name).write_text("\n".join(lines), encoding="utf-8")
            stats["converted"] += 1
            stats["annotations"] += len(lines)

        return stats

    def convert_labelme_to_yolo(
        self,
        json_dir: str | Path,
        output_dir: str | Path,
        class_mapping: dict[str, int],
    ) -> dict[str, Any]:
        """Convert LabelMe rectangle JSON files to YOLO TXT labels."""

        json_path = Path(json_dir)
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)

        stats: dict[str, Any] = {"total": 0, "converted": 0, "annotations": 0, "skipped": 0}
        for labelme_file in sorted(json_path.glob("*.json")):
            stats["total"] += 1
            try:
                data = json.loads(labelme_file.read_text(encoding="utf-8"))
                width = float(data.get("imageWidth", 0))
                height = float(data.get("imageHeight", 0))
                lines: list[str] = []

                for shape in data.get("shapes", []):
                    label = shape.get("label")
                    points = shape.get("points") or []
                    if label not in class_mapping or len(points) < 2:
                        continue
                    xs = [float(point[0]) for point in points]
                    ys = [float(point[1]) for point in points]
                    x_min, x_max = min(xs), max(xs)
                    y_min, y_max = min(ys), max(ys)
                    yolo_bbox = self._bbox_to_yolo(
                        x_min,
                        y_min,
                        x_max - x_min,
                        y_max - y_min,
                        width,
                        height,
                    )
                    if yolo_bbox is None:
                        continue
                    lines.append(self._format_yolo_line(class_mapping[label], yolo_bbox))

                (out_path / f"{labelme_file.stem}.txt").write_text("\n".join(lines), encoding="utf-8")
                stats["converted"] += 1
                stats["annotations"] += len(lines)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Skipping LabelMe file %s: %s", labelme_file, exc)
                stats["skipped"] += 1

        return stats

