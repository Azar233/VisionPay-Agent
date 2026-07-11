from pathlib import Path

from tools.verify_dataset import verify_dataset


def _write_split(root: Path, split: str, labels: dict[str, list[str]]) -> None:
    image_dir = root / "images" / split
    label_dir = root / "labels" / split
    image_dir.mkdir(parents=True)
    label_dir.mkdir(parents=True)
    for stem, rows in labels.items():
        (image_dir / f"{stem}.jpg").write_bytes(b"sample")
        (label_dir / f"{stem}.txt").write_text("\n".join(rows), encoding="utf-8")


def test_verify_dataset_reports_split_density_and_class_coverage(tmp_path):
    (tmp_path / "data.yaml").write_text(
        'path: .\ntrain: images/train\nval: images/val\nnc: 2\nnames:\n  0: "a"\n  1: "b"\n',
        encoding="utf-8",
    )
    _write_split(tmp_path, "train", {"train": ["0 0.5 0.5 0.2 0.2"]})
    _write_split(
        tmp_path,
        "val",
        {
            "val": [
                "0 0.2 0.2 0.1 0.1",
                "0 0.4 0.4 0.1 0.1",
                "1 0.6 0.6 0.1 0.1",
            ]
        },
    )

    report = verify_dataset(str(tmp_path))

    assert report["split_stats"]["train"]["annotations_per_image"] == 1.0
    assert report["split_stats"]["val"]["annotations_per_image"] == 3.0
    assert any("val 含有 train 未出现" in warning for warning in report["split_warnings"])
    assert any("存在明显场景分布偏移" in warning for warning in report["split_warnings"])
