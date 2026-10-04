"""Write ``docs/wandb-runs/``, the two W&B runs the W&B gallery page reads.

Each run is a small causal language model's fine-tune as W&B logs it, with
the real SDK in offline mode: ``train/loss`` and ``train/learning_rate`` every
step, ``eval/loss`` every 20. Only the run file, ``run-<id>.wandb``, is kept:
it is all ``maidr.read_wandb_history`` reads, and the rest of a run directory
records the machine it ran on. Run from the repository root::

    uv run --with wandb python docs/_scripts/wandb_example.py
"""

from __future__ import annotations

import glob
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "wandb-runs"

WRITER = """
import math, random, wandb
random.seed({seed})
run = wandb.init(
    project="tiny-lm",
    name={name!r},
    id={run_id!r},
    mode="offline",
    settings=wandb.Settings(
        x_disable_stats=True, x_disable_meta=True, x_disable_machine_info=True
    ),
)
steps = 120
for step in range(steps):
    warmup = min(1.0, (step + 1) / 10)
    lr = {peak} * warmup * 0.5 * (1 + math.cos(math.pi * step / steps))
    loss = {floor} + 2.4 * math.exp(-step / {pace}) + random.gauss(0, 0.06)
    row = {{"train/loss": round(loss, 4), "train/learning_rate": lr}}
    if step % 20 == 19:
        row["eval/loss"] = round({floor} + 0.12 + 2.4 * math.exp(-step / {pace}), 4)
    wandb.log(row, step=step)
run.finish()
"""

RUNS = [
    dict(name="baseline", run_id="baseline1", seed=1, peak=2e-4, floor=1.9, pace=35),
    dict(name="lora-r16", run_id="lorar16x1", seed=2, peak=1e-3, floor=1.7, pace=22),
]


def main() -> None:
    shutil.rmtree(OUT, ignore_errors=True)
    for spec in RUNS:
        with tempfile.TemporaryDirectory() as directory:
            env = {
                **os.environ,
                "WANDB_DIR": directory,
                "WANDB_SILENT": "true",
                "WANDB_DISABLE_GIT": "true",
                "WANDB_DISABLE_CODE": "true",
                "WANDB_CONSOLE": "off",
            }
            code = WRITER.format(**spec)
            subprocess.run([sys.executable, "-c", code], env=env, check=True)
            (run_file,) = glob.glob(f"{directory}/wandb/offline-run-*/*.wandb")
            target = OUT / spec["name"]
            target.mkdir(parents=True)
            shutil.copy(run_file, target / os.path.basename(run_file))


if __name__ == "__main__":
    main()
