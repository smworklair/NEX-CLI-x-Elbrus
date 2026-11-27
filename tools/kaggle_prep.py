"""Stage Kaggle dataset and kernel scripts into `build/kaggle/` offline.

    python tools/kaggle_prep.py
    tools/kaggle_push.sh          # injects real Kaggle username and uploads
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build" / "kaggle"
DATA = BUILD / "dataset"

# Dataset payload: (source_path, target_name)
PAYLOAD = [
    ("train_merged.jsonl", "train_merged.jsonl"),
    ("dataset.jsonl", "dataset.jsonl"),
    ("training/checkpoints/eval.jsonl", "eval.jsonl"),
    ("eval_wide.jsonl", "eval_wide.jsonl"),
    ("training/validate_kaggle.py", "validate_kaggle.py"),
    ("training/train_qlora.py", "train_qlora.py"),
]
ADAPTER_SRC = "training/checkpoints/qwen-vliw-lora"
ADAPTER_DST = "qwen-vliw-lora"

# Include run-1 adapter so both adapters can be compared in one kernel.
#
#
#
EOS_ADAPTER_SRC = "training/checkpoints/lora-eos"
EOS_ADAPTER_DST = "lora-eos"

DATASET_SLUG = "vliw-eos-run"

# Adapter files required for inference/resuming (omit intermediate checkpoints).
#
#
ADAPTER_FILES = ("adapter_config.json", "adapter_model.safetensors",
                 "tokenizer.json", "tokenizer_config.json",
                 "chat_template.jinja")

# Shared kernel prologue: locate mounted dataset in /kaggle/input with retries.
#
#
#
#
#
#
#
#
#
#
#
#
FIND_DATASET = '''\
def _find_dataset(marker_file, tries=6, pause=10):
    import glob, os, time
    for i in range(tries):
        hits = glob.glob(f"/kaggle/input/**/{marker_file}", recursive=True)
        if hits:
            return os.path.dirname(hits[0])
        if i < tries - 1:
            print(f"  dataset not mounted yet (attempt {i+1}/{tries}), "
                  f"waiting {pause}s...", flush=True)
            time.sleep(pause)
    tree = []
    for root, dirs, files in os.walk("/kaggle/input"):
        depth = root.count(os.sep) - "/kaggle/input".count(os.sep)
        tree.append(root + (" [" + ", ".join(files) + "]" if files else ""))
        if depth >= 4:   # stop descending past depth 4
            dirs[:] = []
    raise AssertionError(
        f"dataset not mounted: {marker_file!r} not found in /kaggle/input "
        f"(recursive, {tries} tries). Tree:\\n  " + "\\n  ".join(tree))
'''

# Early GPU self-check: catches CUDA/torch mismatch before downloading weights.
#
#
#
#
#
#
#
#
#
CHECK_GPU = '''\
def _check_gpu():
    import torch
    if not torch.cuda.is_available():
        raise SystemExit("no GPU: torch.cuda.is_available() == False")
    name = torch.cuda.get_device_name(0)
    cap = torch.cuda.get_device_capability(0)
    print(f"GPU: {name}, compute capability {cap[0]}.{cap[1]}", flush=True)
    try:
        (torch.zeros(8, 8, device="cuda") @ torch.zeros(8, 8, device="cuda")).sum().item()
    except RuntimeError as e:
        raise SystemExit(
            f"GPU {name} (capability {cap[0]}.{cap[1]}) is incompatible with this "
            f"torch build: {e}\\n"
            f"P100 (sm_60) fails under the default Kaggle image — "
            f"kernel-metadata.json requests NvidiaTeslaT4, but if Kaggle "
            f"still allocated an incompatible GPU, fail fast here "
            f"instead of after pip install and downloading weights."
        ) from e
    print("GPU: basic CUDA matmul succeeded — compatibility verified", flush=True)
'''

STEP0 = '''\
"""Step 0: baseline evaluation of existing adapter (inference only)."""
import subprocess, sys, os

''' + FIND_DATASET + CHECK_GPU + '''
BASE = _find_dataset("validate_kaggle.py")
print("dataset:", BASE, flush=True)
_check_gpu()

subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-U",
                "transformers", "peft", "bitsandbytes", "accelerate"], check=True)

for data, dump in (("eval.jsonl", "base_eval.jsonl"),
                   ("eval_wide.jsonl", "base_eval_wide.jsonl")):
    print("\\n" + "=" * 70, flush=True)
    print("EVAL:", data, flush=True)
    print("=" * 70, flush=True)
    subprocess.run([sys.executable, f"{BASE}/validate_kaggle.py",
                    "--model", f"{BASE}/qwen-vliw-lora",
                    "--dump", f"/kaggle/working/{dump}",
                    f"{BASE}/{data}"], check=True)
'''

RUN1 = '''\
"""Run 1: isolated EOS fix on dataset.jsonl (1 epoch, aborts if EOS check fails)."""
import subprocess, sys, os

''' + FIND_DATASET + CHECK_GPU + '''
BASE = _find_dataset("train_qlora.py")
OUT = "/kaggle/working/lora-eos"
_check_gpu()

subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-U",
                "transformers", "peft", "bitsandbytes", "accelerate", "datasets"],
               check=True)

# --- training with live EOS self-check in stdout ------------------------
proc = subprocess.Popen(
    [sys.executable, "-u", f"{BASE}/train_qlora.py",
     "--base", "Qwen/Qwen2.5-3B-Instruct",
     "--adapter", f"{BASE}/qwen-vliw-lora",
     "--data", f"{BASE}/dataset.jsonl",
     "--out", OUT, "--epochs", "1"],
    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)

eos_ok = None
for line in proc.stdout:
    print(line, end="", flush=True)
    # Match explicit train_qlora.py::check_eos() markers only.
    #
    #
    #
    if "EOS_SELFCHECK: OK" in line:
        eos_ok = True
    elif "EOS_SELFCHECK: FAIL" in line:
        eos_ok = False
        print("\\n!! EOS self-check failed — terminating training to save GPU quota.",
              flush=True)
        proc.kill()
        break
proc.wait()

if eos_ok is False:
    raise SystemExit("EOS missing from loss — see log above")
if eos_ok is None:
    raise SystemExit("EOS self-check marker missing: wrong train_qlora.py version?")
if proc.returncode != 0:
    raise SystemExit(f"training failed with exit code {proc.returncode}")

# --- evaluate on both eval sets -----------------------------------------
for data, dump in (("eval.jsonl", "eos_eval.jsonl"),
                   ("eval_wide.jsonl", "eos_eval_wide.jsonl")):
    print("\\n" + "=" * 70, flush=True)
    print("EVAL:", data, flush=True)
    print("=" * 70, flush=True)
    subprocess.run([sys.executable, f"{BASE}/validate_kaggle.py",
                    "--model", OUT, "--dump", f"/kaggle/working/{dump}",
                    f"{BASE}/{data}"], check=True)
'''

RUN2 = '''\
"""Run 2: full training from scratch on train_merged.jsonl (2 epochs, batch 2x8)."""
import os, subprocess, sys

''' + FIND_DATASET + CHECK_GPU + '''
BASE = _find_dataset("train_qlora.py")
OUT = "/kaggle/working/lora-merged"
_check_gpu()

subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-U",
                "transformers", "peft", "bitsandbytes", "accelerate", "datasets"],
               check=True)

# --- training with live EOS self-check in stdout ------------------------
# expandable_segments reduces CUDA allocator fragmentation on long runs.
#
env = dict(os.environ,
           PYTORCH_CUDA_ALLOC_CONF="expandable_segments:True")
proc = subprocess.Popen(
    [sys.executable, "-u", f"{BASE}/train_qlora.py",
     "--base", "Qwen/Qwen2.5-3B-Instruct",
     "--data", f"{BASE}/train_merged.jsonl",
     "--out", OUT, "--epochs", "2",
     "--batch-size", "2", "--accum", "8"],
    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
    env=env)

eos_ok = None
for line in proc.stdout:
    print(line, end="", flush=True)
    if "EOS_SELFCHECK: OK" in line:
        eos_ok = True
    elif "EOS_SELFCHECK: FAIL" in line:
        eos_ok = False
        print("\\n!! EOS self-check failed — terminating training to save GPU quota.",
              flush=True)
        proc.kill()
        break
proc.wait()

if eos_ok is False:
    raise SystemExit("EOS missing from loss — see log above")
if proc.returncode != 0:
    raise SystemExit(f"training failed with exit code {proc.returncode}")
if eos_ok is None:
    # Warn if EOS marker was lost in log pipe despite clean exit.
    #
    #
    #
    #
    #
    #
    print("\\n!! EOS_SELFCHECK marker not seen despite clean training exit — "
          "may have dropped in log pipe; verify self-check output above "
          "manually", flush=True)

# --- evaluate on both eval sets -----------------------------------------
for data, dump in (("eval.jsonl", "merged_eval.jsonl"),
                   ("eval_wide.jsonl", "merged_eval_wide.jsonl")):
    print("\\n" + "=" * 70, flush=True)
    print("EVAL:", data, flush=True)
    print("=" * 70, flush=True)
    subprocess.run([sys.executable, f"{BASE}/validate_kaggle.py",
                    "--model", OUT, "--dump", f"/kaggle/working/{dump}",
                    f"{BASE}/{data}"], check=True)
'''

# Kernel title must slugify identically to id (ASCII words matching slug).
#
#
#
#
#
#
#
#
RESUME2 = '''\
"""Resume Run 2 from latest checkpoint or run remaining evals if train_meta.json exists."""
import glob, os, shutil, subprocess, sys

''' + FIND_DATASET + CHECK_GPU + '''
BASE = _find_dataset("train_qlora.py")
OUT = "/kaggle/working/lora-merged"
_check_gpu()

subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-U",
                "transformers", "peft", "bitsandbytes", "accelerate", "datasets"],
               check=True)

# --- locate previous run output ------------------------------------------
# Discover prior output by marker files (train_meta.json or checkpoint-*).
#
#
#
#
meta_hits = glob.glob("/kaggle/input/**/train_meta.json", recursive=True)
ckpt_hits = glob.glob("/kaggle/input/**/checkpoint-*/trainer_state.json",
                      recursive=True)

def _tree_hint():
    tree = []
    for root, dirs, files in os.walk("/kaggle/input"):
        depth = root.count(os.sep) - "/kaggle/input".count(os.sep)
        tree.append(root + (" [" + ", ".join(files) + "]" if files else ""))
        if depth >= 3:
            dirs[:] = []
    return "\\n  ".join(tree)

if meta_hits:
    parents = sorted({os.path.dirname(p) for p in meta_hits})
    if len(parents) != 1:
        raise SystemExit("multiple completed adapters found:"
                         "\\n  " + "\\n  ".join(parents))
    PREV = parents[0]
elif ckpt_hits:
    roots = sorted({os.path.dirname(os.path.dirname(p)) for p in ckpt_hits})
    if len(roots) != 1:
        raise SystemExit("checkpoints found in multiple roots:"
                         "\\n  " + "\\n  ".join(roots))
    PREV = roots[0]
else:
    raise SystemExit("neither train_meta.json "
                     "nor checkpoint-*/trainer_state.json found. Tree:\\n  "
                     + _tree_hint())

if os.path.exists(f"{PREV}/train_meta.json"):
    # Training completed: skip training and run evals directly.
    print("adapter from previous run is complete (train_meta.json) — "
          "skipping training, running evals", flush=True)
    MODEL = PREV          # input is read-only — sufficient for inference
else:
    cks = glob.glob(f"{PREV}/checkpoint-*")
    if not cks:
        raise SystemExit("no checkpoints or "
                         "train_meta.json found — nothing to resume")
    latest = max(cks, key=lambda p: int(p.rsplit("-", 1)[1]))
    n = os.path.basename(latest).rsplit("-", 1)[1]
    dst = f"{OUT}/checkpoint-{n}"
    print(f"resuming from {os.path.basename(latest)}", flush=True)
    # Clean existing dst before copying checkpoint.
    #
    if os.path.exists(dst):
        shutil.rmtree(dst)
    shutil.copytree(latest, dst)

    env = dict(os.environ,
               PYTORCH_CUDA_ALLOC_CONF="expandable_segments:True")
    proc = subprocess.Popen(
        [sys.executable, "-u", f"{BASE}/train_qlora.py",
         "--base", "Qwen/Qwen2.5-3B-Instruct",
         "--data", f"{BASE}/train_merged.jsonl",
         "--out", OUT, "--epochs", "2",
         "--batch-size", "2", "--accum", "8",
         "--resume", dst],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        bufsize=1, env=env)
    eos_ok = None
    for line in proc.stdout:
        print(line, end="", flush=True)
        if "EOS_SELFCHECK: OK" in line:
            eos_ok = True
        elif "EOS_SELFCHECK: FAIL" in line:
            eos_ok = False
            print("\\n!! EOS self-check failed — terminating resumed training.",
                  flush=True)
            proc.kill()
            break
    proc.wait()
    if eos_ok is False:
        raise SystemExit("EOS missing from loss — see log above")
    if proc.returncode != 0:
        raise SystemExit(f"resumed training failed with exit code {proc.returncode}")
    if eos_ok is None:
        print("\\n!! EOS_SELFCHECK marker not seen despite clean resumed exit "
              "— may have dropped in log pipe", flush=True)
    MODEL = OUT

# --- evaluate on both eval sets -----------------------------------------
for data, dump in (("eval.jsonl", "merged_eval.jsonl"),
                   ("eval_wide.jsonl", "merged_eval_wide.jsonl")):
    print("\\n" + "=" * 70, flush=True)
    print("EVAL:", data, flush=True)
    print("=" * 70, flush=True)
    subprocess.run([sys.executable, f"{BASE}/validate_kaggle.py",
                    "--model", MODEL, "--dump", f"/kaggle/working/{dump}",
                    f"{BASE}/{data}"], check=True)
'''


# Run-2 diagnostic kernel: 20 examples with raw completion text.
#
#
#
#
#
#
#
#
#
DIAG2 = '''\
"""Run-2 adapter diagnostics: 20 examples with raw completion text."""
import glob, os, subprocess, sys

''' + FIND_DATASET + CHECK_GPU + '''
BASE = _find_dataset("validate_kaggle.py")
_check_gpu()

subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-U",
                "transformers", "peft", "bitsandbytes", "accelerate"], check=True)

# Locate run-2 adapter via train_meta.json.
#
hits = glob.glob("/kaggle/input/**/train_meta.json", recursive=True)
if not hits:
    raise SystemExit("run-2 adapter not found (searched for train_meta.json)")
MODEL = os.path.dirname(hits[0])
print("adapter:", MODEL, flush=True)

# Compare unconstrained vs constrained decoding on the same 20 examples.
#
for extra, dump in (([], "diag2_free.jsonl"),
                    (["--constrained"], "diag2_constrained.jsonl")):
    print("\\n" + "=" * 70, flush=True)
    print("EVAL:", "constrained" if extra else "free", "decoding", flush=True)
    print("=" * 70, flush=True)
    subprocess.run([sys.executable, f"{BASE}/validate_kaggle.py",
                    "--model", MODEL, "--limit", "20",
                    "--dump", f"/kaggle/working/{dump}",
                    f"{BASE}/eval.jsonl"] + extra, check=True)
'''

# 2x2 eval_wide matrix: 2 adapters x 2 decoding modes (300 examples).
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
DIAG3 = '''\
"""Constrained vs free decoding on eval_wide across both adapters."""
import glob, os, subprocess, sys

''' + FIND_DATASET + CHECK_GPU + '''
BASE = _find_dataset("validate_kaggle.py")
_check_gpu()

subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-U",
                "transformers", "peft", "bitsandbytes", "accelerate"], check=True)

# Locate run-2 (train_meta.json) and run-1 (lora-eos) adapters.
#
#
#
hits = glob.glob("/kaggle/input/**/train_meta.json", recursive=True)
if not hits:
    raise SystemExit("run-2 adapter not found (searched for train_meta.json)")
RUN2 = os.path.dirname(hits[0])

eos = [d for d in glob.glob("/kaggle/input/**/lora-eos", recursive=True)
       if os.path.isdir(d)]
if not eos:
    raise SystemExit("run-1 adapter not found (searched for lora-eos)")
RUN1 = eos[0]

print("run 1:", RUN1, flush=True)
print("run 2:", RUN2, flush=True)

for tag, model in (("run1", RUN1), ("run2", RUN2)):
    for extra, mode in ((["--constrained"], "constrained"), ([], "free")):
        print("\\n" + "=" * 70, flush=True)
        print(f"ADAPTER {tag} / {mode} decoding", flush=True)
        print("=" * 70, flush=True)
        subprocess.run([sys.executable, f"{BASE}/validate_kaggle.py",
                        "--model", model,
                        "--dump", f"/kaggle/working/diag3_{tag}_"
                                  + ("con" if extra else "free") + ".jsonl",
                        f"{BASE}/eval_wide.jsonl"] + extra, check=True)
'''

KERNELS = [
    ("vliw-step0-baseline", "step0.py", STEP0, "vliw step0 baseline"),
    ("vliw-run1-eos", "run1_eos.py", RUN1, "vliw run1 eos"),
    ("vliw-run2-merged", "run2_merged.py", RUN2, "vliw run2 merged"),
    # Run-2 resume kernel (mounts vliw-run2-lora dataset; explicit `resume` only).
    #
    #
    #
    #
    #
    ("vliw-run2-resume", "run2_resume.py", RESUME2, "vliw run2 resume",
     {"dataset_sources": [f"USERNAME/{DATASET_SLUG}",
                          f"USERNAME/vliw-run2-lora"]}),
    # Diagnostics kernel: 20-example inference (`kaggle_push.sh diag`).
    #
    #
    ("vliw-diag2", "diag2.py", DIAG2, "vliw diag2",
     {"dataset_sources": [f"USERNAME/{DATASET_SLUG}",
                          f"USERNAME/vliw-run2-lora"]}),
    # 2x2 eval_wide kernel (`kaggle_push.sh diag3`); title matches id slug.
    #
    #
    #
    #
    #
    #
    #
    ("vliw-diag3-wide", "diag3.py", DIAG3, "vliw diag3 wide",
     {"dataset_sources": [f"USERNAME/{DATASET_SLUG}",
                          f"USERNAME/vliw-run2-lora"]}),
]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--force", action="store_true",
                    help="rebuild build/kaggle from scratch")
    args = ap.parse_args()

    if args.force and BUILD.exists():
        shutil.rmtree(BUILD)
    DATA.mkdir(parents=True, exist_ok=True)

    missing = [src for src, _ in PAYLOAD if not (ROOT / src).exists()]
    missing += [f"{ADAPTER_SRC}/{name}" for name in ADAPTER_FILES
               if not (ROOT / ADAPTER_SRC / name).exists()]
    # lora-eos saves only adapter weights (no tokenizer).
    #
    missing += [f"{EOS_ADAPTER_SRC}/{name}"
                for name in ("adapter_config.json", "adapter_model.safetensors")
                if not (ROOT / EOS_ADAPTER_SRC / name).exists()]
    if missing:
        raise SystemExit("missing files: " + ", ".join(missing))

    # Copy unconditionally (avoid stale mtime bugs on WSL/mounted drives).
    #
    #
    #
    #
    #
    #
    #
    total = 0
    for src, dst in PAYLOAD:
        s, d = ROOT / src, DATA / dst
        shutil.copy2(s, d)
        total += d.stat().st_size

    for src_dir, dst_dir in ((ADAPTER_SRC, ADAPTER_DST),
                             (EOS_ADAPTER_SRC, EOS_ADAPTER_DST)):
        adir = DATA / dst_dir
        adir.mkdir(exist_ok=True)
        for name in ADAPTER_FILES:
            src_file = ROOT / src_dir / name
            if not src_file.exists():
                # lora-eos has no tokenizer files; loader falls back to base model.
                #
                #
                continue
            d = adir / name
            shutil.copy2(src_file, d)
            total += d.stat().st_size

    # Username placeholder replaced at push time by kaggle_push.sh.
    #
    (DATA / "dataset-metadata.json").write_text(json.dumps({
        "title": "VLIW e2k scheduler — data, adapter, scripts",
        "id": f"USERNAME/{DATASET_SLUG}",
        "licenses": [{"name": "CC0-1.0"}],
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    for entry in KERNELS:
        slug, code_file, code, title = entry[:4]
        extras = entry[4] if len(entry) > 4 else {}
        kdir = BUILD / slug
        kdir.mkdir(parents=True, exist_ok=True)
        (kdir / code_file).write_text(code, encoding="utf-8")
        meta = {
            "id": f"USERNAME/{slug}",
            "title": title,
            "code_file": code_file,
            "language": "python",
            "kernel_type": "script",
            "is_private": True,
            "enable_gpu": True,
            # Pin NvidiaTeslaT4 (P100/sm_60 lacks kernels in default Kaggle torch).
            #
            #
            # `CUDA error: no kernel image is available for execution on the
            #
            #
            #
            #
            "machine_shape": "NvidiaTeslaT4",
            "enable_internet": True,
            "dataset_sources": [f"USERNAME/{DATASET_SLUG}"],
            "competition_sources": [],
            "kernel_sources": [],
        }
        # Resume/diag kernels mount the previous run adapter dataset.
        meta.update(extras)
        (kdir / "kernel-metadata.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"staged in {BUILD.relative_to(ROOT)}")
    print(f"  dataset: {len(PAYLOAD)} files + adapter, {total / 2**20:.0f} MB")
    for entry in KERNELS:
        print(f"  kernel:  {entry[0]}/{entry[1]}")
    print("\nnext: tools/kaggle_push.sh (injects username and uploads)")


if __name__ == "__main__":
    main()
