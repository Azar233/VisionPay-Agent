"""Independent YOLO model evaluation script.

Usage:
    cd backend
    python tools/evaluate_model.py --weights runs/train/task_xxxxxxxx/weights/best.pt
    python tools/evaluate_model.py --weights runs/train/task_xxxxxxxx/weights/best.pt --data /path/to/data.yaml --split test
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def safe_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def class_names(names: Any) -> dict[int, str]:
    if isinstance(names, dict):
        return {int(key): str(value) for key, value in names.items()}
    if isinstance(names, (list, tuple)):
        return {index: str(value) for index, value in enumerate(names)}
    return {}


def find_data_yaml(weights_path: Path) -> Path | None:
    task_dir = weights_path.parent.parent
    args_yaml = task_dir / "args.yaml"
    if args_yaml.exists():
        for line in args_yaml.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.strip().startswith("data:"):
                candidate = Path(line.split(":", 1)[1].strip().strip("'\""))
                if not candidate.is_absolute():
                    candidate = (PROJECT_ROOT / candidate).resolve()
                if candidate.exists():
                    return candidate

    for candidate in [
        PROJECT_ROOT / "datasets" / "vision_pay" / "data.yaml",
        PROJECT_ROOT / "datasets" / "vision_pay" / "yolo_dataset" / "data.yaml",
    ]:
        if candidate.exists():
            return candidate
    return None


def collect_artifacts(output_dir: Path) -> dict[str, str]:
    artifacts: dict[str, str] = {}
    expected = {
        "confusion_matrix.png",
        "confusion_matrix_normalized.png",
        "PR_curve.png",
        "F1_curve.png",
        "P_curve.png",
        "R_curve.png",
        "results.png",
    }
    if not output_dir.exists():
        return artifacts
    for file in output_dir.iterdir():
        if file.is_file() and (file.name in expected or file.name.startswith("val_batch")):
            artifacts[file.name] = str(file)
    return artifacts


def build_report(model: Any, metrics: Any, output_dir: Path, args: argparse.Namespace) -> dict[str, Any]:
    names = class_names(getattr(model, "names", {}) or {})
    box_metrics = getattr(metrics, "box", None)
    overall = {
        "precision": safe_float(getattr(box_metrics, "mp", None)),
        "recall": safe_float(getattr(box_metrics, "mr", None)),
        "map50": safe_float(getattr(box_metrics, "map50", None)),
        "map50_95": safe_float(getattr(box_metrics, "map", None)),
    }

    per_class_ap: dict[str, float | None] = {}
    maps = getattr(box_metrics, "maps", None)
    if maps is not None:
        try:
            maps = maps.tolist()
        except AttributeError:
            maps = list(maps)
        for index, ap_value in enumerate(maps):
            per_class_ap[names.get(index, str(index))] = safe_float(ap_value)

    weak_classes = sorted(
        [
            {"class_name": class_name, "ap": ap}
            for class_name, ap in per_class_ap.items()
            if ap is not None
        ],
        key=lambda item: item["ap"],
    )[:10]

    return {
        "weights_path": str(args.weights),
        "data_yaml": str(args.data_yaml),
        "split": args.split,
        "device": args.device,
        "img_size": args.img_size,
        "conf": args.conf,
        "iou": args.iou,
        "output_dir": str(output_dir),
        "overall": overall,
        "precision": overall["precision"],
        "recall": overall["recall"],
        "map50": overall["map50"],
        "map50_95": overall["map50_95"],
        "per_class_ap": per_class_ap,
        "weak_classes": weak_classes,
        "artifacts": collect_artifacts(output_dir),
        "created_at": datetime.now().isoformat(),
    }


def run_evaluation(args: argparse.Namespace) -> dict[str, Any]:
    from ultralytics import YOLO

    model = YOLO(str(args.weights))
    output_dir = args.output or args.weights.parent.parent / f"eval_{args.split}"
    output_dir = Path(output_dir).resolve()

    metrics = model.val(
        data=str(args.data_yaml),
        split=args.split,
        conf=args.conf,
        iou=args.iou,
        imgsz=args.img_size,
        device=args.device,
        project=str(output_dir.parent),
        name=output_dir.name,
        exist_ok=True,
        plots=True,
        verbose=True,
    )
    save_dir = Path(getattr(metrics, "save_dir", output_dir))
    report = build_report(model, metrics, save_dir, args)
    report_path = save_dir / "eval_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    report["report_path"] = str(report_path)
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate a YOLO model and save eval_report.json")
    parser.add_argument("--weights", required=True, type=Path, help="Path to best.pt")
    parser.add_argument("--data", "--data-yaml", dest="data_yaml", type=Path, default=None)
    parser.add_argument("--split", default="val", choices=["train", "val", "test"])
    parser.add_argument("--conf", type=float, default=0.001)
    parser.add_argument("--iou", type=float, default=0.6)
    parser.add_argument("--img-size", "--imgsz", dest="img_size", type=int, default=640)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--output", type=Path, default=None, help="Output directory for plots and report")
    args = parser.parse_args()

    args.weights = args.weights.resolve()
    if not args.weights.exists():
        raise FileNotFoundError(f"weights not found: {args.weights}")

    if args.data_yaml is None:
        args.data_yaml = find_data_yaml(args.weights)
    if args.data_yaml is None:
        raise FileNotFoundError("data.yaml not found; pass --data /path/to/data.yaml")
    args.data_yaml = args.data_yaml.resolve()
    if not args.data_yaml.exists():
        raise FileNotFoundError(f"data.yaml not found: {args.data_yaml}")
    return args


def main() -> None:
    args = parse_args()
    report = run_evaluation(args)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
