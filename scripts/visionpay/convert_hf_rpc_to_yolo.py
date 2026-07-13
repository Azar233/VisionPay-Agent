#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from collections import Counter
from io import BytesIO
from pathlib import Path
from typing import Any

import yaml
from datasets import Image, load_dataset
from PIL import Image as PILImage

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = Path(os.environ.get('VISIONPAY_BACKEND_ROOT', PROJECT_ROOT / 'backend')).resolve()
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.training.data_converter import DataConverter  # noqa: E402
from app.training.dataset_splitter import DatasetSplitter  # noqa: E402

SPLIT_MAP = {
    'train': 'train',
    'validation': 'val',
    'test': 'test',
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Convert HF RPC parquet dataset to YOLO layout.')
    parser.add_argument('--source', default='/data0/xshi/datasets/visionpay/raw/hf_rpc')
    parser.add_argument('--output', default='/data0/xshi/datasets/visionpay/yolo/vision_pay')
    parser.add_argument('--backend-root', default=str(BACKEND_ROOT))
    parser.add_argument('--clean', action='store_true')
    parser.add_argument('--limit-train', type=int, default=None)
    parser.add_argument('--limit-val', type=int, default=None)
    parser.add_argument('--limit-test', type=int, default=None)
    parser.add_argument('--progress-every', type=int, default=1000)
    return parser.parse_args()


def load_class_names(readme_path: Path) -> list[str]:
    text = readme_path.read_text(encoding='utf-8')
    data = next(yaml.safe_load_all(text))
    names = None
    features = data.get('dataset_info', {}).get('features', []) if isinstance(data, dict) else []
    for feature in features:
        if feature.get('name') != 'objects':
            continue
        for item in feature.get('struct', []):
            if item.get('name') == 'category':
                names = item.get('list', {}).get('class_label', {}).get('names')
                break
    if not names:
        raise ValueError(f'Could not find category names in {readme_path}')
    return [names[str(index)] for index in range(len(names))]


def data_files(data_dir: Path) -> dict[str, str]:
    return {
        'train': str(data_dir / 'train-*.parquet'),
        'validation': str(data_dir / 'validation-*.parquet'),
        'test': str(data_dir / 'test-*.parquet'),
    }


def image_bytes(record: dict[str, Any]) -> bytes:
    image = record['image']
    if isinstance(image, dict):
        raw = image.get('bytes')
        if raw is not None:
            return raw
        path = image.get('path')
        if path:
            return Path(path).read_bytes()
    if hasattr(image, 'save'):
        buf = BytesIO()
        image.save(buf, format='JPEG', quality=95)
        return buf.getvalue()
    raise TypeError(f'Unsupported image value: {type(image)!r}')


def convert_one_split(ds, split_name: str, yolo_split: str, output_dir: Path, limit: int | None, progress_every: int) -> dict[str, Any]:
    image_dir = output_dir / 'images' / yolo_split
    label_dir = output_dir / 'labels' / yolo_split
    image_dir.mkdir(parents=True, exist_ok=True)
    label_dir.mkdir(parents=True, exist_ok=True)

    stats = {
        'images': 0,
        'annotations': 0,
        'skipped_annotations': 0,
        'class_distribution': Counter(),
    }

    total = len(ds[split_name]) if limit is None else min(limit, len(ds[split_name]))
    for idx, record in enumerate(ds[split_name]):
        if limit is not None and idx >= limit:
            break

        raw = image_bytes(record)
        image_name = f'{yolo_split}_{idx:06d}.jpg'
        image_path = image_dir / image_name
        image_path.write_bytes(raw)

        with PILImage.open(BytesIO(raw)) as im:
            width, height = im.size

        objects = record.get('objects') or {}
        bboxes = objects.get('bbox') or []
        categories = objects.get('category') or []
        lines: list[str] = []
        for category_id, bbox in zip(categories, bboxes):
            if bbox is None or len(bbox) != 4:
                stats['skipped_annotations'] += 1
                continue
            yolo_bbox = DataConverter._bbox_to_yolo(
                float(bbox[0]),
                float(bbox[1]),
                float(bbox[2]),
                float(bbox[3]),
                float(width),
                float(height),
            )
            if yolo_bbox is None:
                stats['skipped_annotations'] += 1
                continue
            class_id = int(category_id)
            lines.append(DataConverter._format_yolo_line(class_id, yolo_bbox))
            stats['class_distribution'][class_id] += 1

        label_text = '\n'.join(lines) + ('\n' if lines else '')
        (label_dir / f'{Path(image_name).stem}.txt').write_text(label_text, encoding='utf-8')
        stats['images'] += 1
        stats['annotations'] += len(lines)

        if progress_every and (idx + 1) % progress_every == 0:
            print(
                f'[{yolo_split}] {idx + 1}/{total} images, annotations={stats["annotations"]}',
                flush=True,
            )

    stats['class_distribution'] = dict(sorted(stats['class_distribution'].items()))
    print(
        f'[{yolo_split}] done images={stats["images"]} annotations={stats["annotations"]} skipped={stats["skipped_annotations"]}',
        flush=True,
    )
    return stats


def main() -> int:
    args = parse_args()
    source = Path(args.source).resolve()
    output = Path(args.output).resolve()
    data_dir = source / 'data'
    readme = source / 'README.md'

    if not data_dir.exists():
        print(f'[error] missing parquet data dir: {data_dir}', file=sys.stderr)
        return 1
    if not readme.exists():
        print(f'[error] missing README with class names: {readme}', file=sys.stderr)
        return 1

    if args.clean and output.exists():
        for child_name in ['images', 'labels']:
            child = output / child_name
            if child.exists():
                shutil.rmtree(child)

    class_names = load_class_names(readme)
    print(f'class_count={len(class_names)}', flush=True)
    print(f'source={source}', flush=True)
    print(f'output={output}', flush=True)

    ds = load_dataset('parquet', data_files=data_files(data_dir))
    ds = ds.cast_column('image', Image(decode=False))
    print(ds, flush=True)

    limits = {
        'train': args.limit_train,
        'validation': args.limit_val,
        'test': args.limit_test,
    }
    report = {
        'source': str(source),
        'output': str(output),
        'class_count': len(class_names),
        'class_names': class_names,
        'splits': {},
    }

    for hf_split, yolo_split in SPLIT_MAP.items():
        report['splits'][yolo_split] = convert_one_split(
            ds=ds,
            split_name=hf_split,
            yolo_split=yolo_split,
            output_dir=output,
            limit=limits[hf_split],
            progress_every=args.progress_every,
        )

    yaml_path = DatasetSplitter.generate_data_yaml(output_dir=output, class_names=class_names, dataset_path=output)
    report['data_yaml'] = yaml_path
    report_path = output / 'conversion_report.json'
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'data_yaml={yaml_path}', flush=True)
    print(f'report={report_path}', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
