
#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import random
import shutil
from collections import Counter, defaultdict
from pathlib import Path

IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.bmp', '.tif', '.tiff', '.webp'}


def parse_args():
    parser = argparse.ArgumentParser(description='Create a symlinked YOLO sample dataset for quick training.')
    parser.add_argument('--source', default='/data0/xshi/datasets/visionpay/yolo/vision_pay')
    parser.add_argument('--output', default='/data0/xshi/datasets/visionpay/yolo/vision_pay_sample_2k')
    parser.add_argument('--train-per-class', type=int, default=10)
    parser.add_argument('--val-size', type=int, default=400)
    parser.add_argument('--test-size', type=int, default=400)
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--copy', action='store_true', help='Copy files instead of symlinking.')
    parser.add_argument('--clean', action='store_true')
    return parser.parse_args()


def first_class(label_path: Path) -> int | None:
    for line in label_path.read_text(encoding='utf-8').splitlines():
        parts = line.strip().split()
        if parts:
            return int(parts[0])
    return None


def label_classes(label_path: Path) -> set[int]:
    classes: set[int] = set()
    for line in label_path.read_text(encoding='utf-8').splitlines():
        parts = line.strip().split()
        if parts:
            classes.add(int(parts[0]))
    return classes


def image_for_label(image_dir: Path, stem: str) -> Path:
    for ext in IMAGE_EXTS:
        p = image_dir / f'{stem}{ext}'
        if p.exists():
            return p
    raise FileNotFoundError(f'image not found for label stem: {stem}')


def link_or_copy(src: Path, dst: Path, copy: bool) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists() or dst.is_symlink():
        dst.unlink()
    if copy:
        shutil.copy2(src, dst)
    else:
        os.symlink(src, dst)


def write_split(source: Path, output: Path, split: str, label_paths: list[Path], copy: bool) -> dict:
    src_img_dir = source / 'images' / split
    out_img_dir = output / 'images' / split
    out_lbl_dir = output / 'labels' / split
    dist = Counter()
    annotations = 0
    for label in sorted(label_paths, key=lambda p: p.name):
        img = image_for_label(src_img_dir, label.stem)
        link_or_copy(img, out_img_dir / img.name, copy)
        link_or_copy(label, out_lbl_dir / label.name, copy)
        classes = label_classes(label)
        for cls in classes:
            dist[cls] += 1
        annotations += sum(1 for line in label.read_text(encoding='utf-8').splitlines() if line.strip())
    return {
        'images': len(label_paths),
        'labels': len(label_paths),
        'annotations': annotations,
        'classes_present': len(dist),
        'class_distribution': dict(sorted(dist.items())),
    }


def sample_train(source: Path, per_class: int, rng: random.Random) -> list[Path]:
    labels = sorted((source / 'labels' / 'train').glob('*.txt'))
    by_class: dict[int, list[Path]] = defaultdict(list)
    for label in labels:
        cls = first_class(label)
        if cls is not None:
            by_class[cls].append(label)
    selected: list[Path] = []
    for cls in sorted(by_class):
        candidates = by_class[cls]
        rng.shuffle(candidates)
        selected.extend(candidates[:per_class])
    rng.shuffle(selected)
    return selected


def sample_multilabel(source: Path, split: str, target_size: int, rng: random.Random) -> list[Path]:
    labels = sorted((source / 'labels' / split).glob('*.txt'))
    class_to_labels: dict[int, list[Path]] = defaultdict(list)
    label_to_classes: dict[Path, set[int]] = {}
    for label in labels:
        classes = label_classes(label)
        if not classes:
            continue
        label_to_classes[label] = classes
        for cls in classes:
            class_to_labels[cls].append(label)

    selected: list[Path] = []
    selected_set: set[Path] = set()
    covered: set[int] = set()

    for cls in range(200):
        candidates = [p for p in class_to_labels.get(cls, []) if p not in selected_set]
        if not candidates:
            continue
        best = max(candidates, key=lambda p: len(label_to_classes[p] - covered))
        selected.append(best)
        selected_set.add(best)
        covered |= label_to_classes[best]

    remaining = [p for p in labels if p not in selected_set]
    rng.shuffle(remaining)
    for p in remaining:
        if len(selected) >= target_size:
            break
        selected.append(p)
        selected_set.add(p)

    selected = selected[:target_size]
    rng.shuffle(selected)
    return selected


def main() -> int:
    args = parse_args()
    source = Path(args.source).resolve()
    output = Path(args.output).resolve()
    rng = random.Random(args.seed)

    if not (source / 'data.yaml').exists():
        raise FileNotFoundError(source / 'data.yaml')

    allowed_root = Path('/data0/xshi/datasets/visionpay').resolve()
    if allowed_root not in output.parents and output != allowed_root:
        raise ValueError(f'unsafe output outside allowed data root: {output}')

    if args.clean and output.exists():
        shutil.rmtree(output)

    for split in ['train', 'val', 'test']:
        (output / 'images' / split).mkdir(parents=True, exist_ok=True)
        (output / 'labels' / split).mkdir(parents=True, exist_ok=True)

    train_labels = sample_train(source, args.train_per_class, rng)
    val_labels = sample_multilabel(source, 'val', args.val_size, rng)
    test_labels = sample_multilabel(source, 'test', args.test_size, rng)

    shutil.copy2(source / 'data.yaml', output / 'data.yaml')
    data_yaml = (output / 'data.yaml').read_text(encoding='utf-8').splitlines()
    data_yaml[0] = f'path: {output.as_posix()}'
    (output / 'data.yaml').write_text('\n'.join(data_yaml) + '\n', encoding='utf-8')

    report = {
        'source': str(source),
        'output': str(output),
        'seed': args.seed,
        'symlinked': not args.copy,
        'config': {
            'train_per_class': args.train_per_class,
            'val_size': args.val_size,
            'test_size': args.test_size,
        },
        'splits': {
            'train': write_split(source, output, 'train', train_labels, args.copy),
            'val': write_split(source, output, 'val', val_labels, args.copy),
            'test': write_split(source, output, 'test', test_labels, args.copy),
        },
    }
    (output / 'sample_report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
