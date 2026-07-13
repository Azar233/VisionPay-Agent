#!/bin/bash
#SBATCH --job-name=sx_mix_dataset
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --gres=gpu:0
#SBATCH --cpus-per-task=32
#SBATCH --mem=100G
#SBATCH --output=./log/%j_%x.out
#SBATCH --error=./log/%j_%x.err

set -euo pipefail

SRC=/data0/xshi/datasets/visionpay/yolo/vision_pay
OUT=/data0/xshi/datasets/visionpay/yolo/vision_pay_mixed_train4800_val1200
VAL_TO_TRAIN=4800
SEED=42
WORKERS=${SLURM_CPUS_PER_TASK:-24}
FORCE=${FORCE:-0}

mkdir -p /home/xshi/projects/VisionPay-Agent/logs

echo "host=$(hostname)"
echo "job_id=${SLURM_JOB_ID:-none}"
echo "src=$SRC"
echo "out=$OUT"
echo "workers=$WORKERS"
echo "force=$FORCE"

if [ ! -d "$SRC" ]; then
  echo "ERROR: source dataset not found: $SRC" >&2
  exit 1
fi

if [ -e "$OUT" ]; then
  if [ "$FORCE" = "1" ]; then
    case "$OUT" in
      /data0/xshi/datasets/visionpay/yolo/vision_pay_mixed_train4800_val1200)
        echo "Removing existing output: $OUT"
        rm -rf "$OUT"
        ;;
      *)
        echo "ERROR: unsafe OUT path: $OUT" >&2
        exit 2
        ;;
    esac
  else
    echo "ERROR: output already exists: $OUT"
    echo "Use FORCE=1 sbatch $0 to overwrite."
    exit 3
  fi
fi

python -u - <<PY
from __future__ import annotations

import json
import random
import shutil
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

SRC = Path("$SRC")
OUT = Path("$OUT")
VAL_TO_TRAIN = int("$VAL_TO_TRAIN")
SEED = int("$SEED")
WORKERS = int("$WORKERS")
started = time.time()

def log(msg: str) -> None:
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)

def count_labels(label_dir: Path) -> tuple[int, int, int]:
    images = objects = max_obj = 0
    for p in label_dir.glob("*.txt"):
        with p.open("r", encoding="utf-8", errors="ignore") as f:
            n = sum(1 for line in f if line.strip())
        images += 1
        objects += n
        max_obj = max(max_obj, n)
    return images, objects, max_obj

def copy_pair(job: tuple[str, str, str]) -> tuple[str, str, str]:
    src_split, dst_split, stem = job
    img_src = SRC / "images" / src_split / f"{stem}.jpg"
    lab_src = SRC / "labels" / src_split / f"{stem}.txt"
    img_dst = OUT / "images" / dst_split / img_src.name
    lab_dst = OUT / "labels" / dst_split / lab_src.name
    if not img_src.exists():
        raise FileNotFoundError(img_src)
    if not lab_src.exists():
        raise FileNotFoundError(lab_src)
    shutil.copy2(img_src, img_dst)
    shutil.copy2(lab_src, lab_dst)
    return src_split, dst_split, stem

for split in ("train", "val", "test"):
    (OUT / "images" / split).mkdir(parents=True, exist_ok=False)
    (OUT / "labels" / split).mkdir(parents=True, exist_ok=False)

train_stems = sorted(p.stem for p in (SRC / "labels" / "train").glob("*.txt"))
val_stems = sorted(p.stem for p in (SRC / "labels" / "val").glob("*.txt"))
test_stems = sorted(p.stem for p in (SRC / "labels" / "test").glob("*.txt"))

random.Random(SEED).shuffle(val_stems)
val_train_stems = sorted(val_stems[:VAL_TO_TRAIN])
val_keep_stems = sorted(val_stems[VAL_TO_TRAIN:])

jobs = []
jobs += [("train", "train", s) for s in train_stems]
jobs += [("val", "train", s) for s in val_train_stems]
jobs += [("val", "val", s) for s in val_keep_stems]
jobs += [("test", "test", s) for s in test_stems]

plan = {
    "seed": SEED,
    "source": str(SRC),
    "output": str(OUT),
    "train_from_original_train": len(train_stems),
    "train_from_original_val": len(val_train_stems),
    "val_from_original_val": len(val_keep_stems),
    "test_from_original_test": len(test_stems),
}
log("plan=" + json.dumps(plan, ensure_ascii=False))

total = len(jobs)
done = 0
last_log = time.time()

with ThreadPoolExecutor(max_workers=WORKERS) as ex:
    futures = [ex.submit(copy_pair, job) for job in jobs]
    for fut in as_completed(futures):
        src_split, dst_split, stem = fut.result()
        done += 1
        now = time.time()
        if done % 1000 == 0 or done == total or now - last_log >= 30:
            rate = done / max(now - started, 1)
            eta_min = (total - done) / max(rate, 1e-9) / 60
            log(f"copied {done}/{total} ({done/total*100:.1f}%), rate={rate:.1f} pairs/s, eta={eta_min:.1f} min, last={src_split}/{stem}->{dst_split}")
            last_log = now

data_yaml = (SRC / "data.yaml").read_text(encoding="utf-8")
lines = data_yaml.splitlines()
if lines and lines[0].startswith("path:"):
    lines[0] = f"path: {OUT.as_posix()}"
else:
    lines.insert(0, f"path: {OUT.as_posix()}")
(OUT / "data.yaml").write_text("\\n".join(lines) + "\\n", encoding="utf-8")
(OUT / "split_plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\\n", encoding="utf-8")

summary = {}
for split in ("train", "val", "test"):
    image_count = len(list((OUT / "images" / split).glob("*.jpg")))
    label_count, object_count, max_obj = count_labels(OUT / "labels" / split)
    summary[split] = {
        "images": image_count,
        "labels": label_count,
        "objects": object_count,
        "avg_objects_per_image": round(object_count / max(label_count, 1), 4),
        "max_objects_per_image": max_obj,
    }

summary["elapsed_seconds"] = round(time.time() - started, 1)
(OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\\n", encoding="utf-8")
log("summary=" + json.dumps(summary, ensure_ascii=False))
log("done")
PY