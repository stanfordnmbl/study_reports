"""Render one MP4 per motion listed in a subject manifest (subject.yaml).

Per trial:  .osim + .mot (+ GRF .mot)  --convert-->  viewer file in --work  --render-->  MP4

Requires: pyyaml, plus everything viewer_movie.py needs (playwright, imageio-ffmpeg).
Keep this file next to viewer_movie.py.

Usage:
    python run_manifest_movies.py subject.yaml \
        --build vendor/opensim-viewer/build --work work/ID119 \
        --out-dir ID119/movies \
        --convert-cmd "python convert_trial.py --model {model} --motion {motion} --force {force} --out {out}"

Placeholders available in --convert-cmd: {model} {motion} {force} {out}
(paths are absolute; {force} is an empty string if the trial has no force_path).
If the converted file already exists in --work, conversion is skipped (use --reconvert to redo it).
Use --skip-convert if the viewer files are already in --work as <slug>.json.
"""
from __future__ import annotations

import argparse
import os
import re
import shlex
import subprocess
import sys
import time
import traceback
from pathlib import Path

import yaml

from viewer_movie import render_movie, start_server


def slugify(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_").lower()


def resolve(base: Path, p: str | None) -> Path | None:
    if not p:
        return None
    q = Path(p)
    return q if q.is_absolute() else (base / q).resolve()


def convert_trial(cmd_template: str, model: Path, motion: Path, force: Path | None, out: Path) -> None:
    """Run the external .osim + .mot -> viewer-file converter."""
    if not cmd_template:
        raise RuntimeError(
            f"{out.name} not found in the work dir and no --convert-cmd given.\n"
            "Pass --convert-cmd with a command that writes the viewer file "
            "(placeholders: {model} {motion} {force} {out}), or put the files in --work yourself."
        )
    tokens = shlex.split(cmd_template, posix=(os.name != "nt"))
    values = dict(model=str(model), motion=str(motion), force=str(force) if force else "", out=str(out))
    argv = [t.strip('"').format(**values) for t in tokens]
    if not force:  # drop a dangling "--force ''" pair
        argv = [a for i, a in enumerate(argv)
                if a != "" and not (a == "--force" and (i + 1 == len(argv) or argv[i + 1] == ""))]
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(argv, check=True)
    if not out.is_file():
        raise RuntimeError(f"Converter ran but did not create {out}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("manifest")
    ap.add_argument("--build", required=True, help="built viewer directory (CRA build/)")
    ap.add_argument("--work", default="work", help="dir for converted viewer files (served at /data/)")
    ap.add_argument("--out-dir", help="where MP4s go (default: <manifest dir>/movies)")
    ap.add_argument("--convert-cmd", default="", help="converter command template (see top of file)")
    ap.add_argument("--skip-convert", action="store_true")
    ap.add_argument("--reconvert", action="store_true")
    ap.add_argument("--only", help="comma-separated substrings of labels/slugs to run")
    ap.add_argument("--fps", type=int, default=30, help="default fps (a trial's own 'fps' wins)")
    ap.add_argument("--route", default="/viewer/{model}")
    ap.add_argument("--timeout", type=int, default=90)
    ap.add_argument("--headed", action="store_true")
    ap.add_argument("--no-probe", action="store_true")
    a = ap.parse_args()

    manifest_path = Path(a.manifest).resolve()

    cfg = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    base = manifest_path.parent
    model = resolve(base, cfg["model"])
    if not model.is_file():
        sys.exit(f"Model not found: {model}")

    work = Path(a.work).resolve()
    out_dir = Path(a.out_dir).resolve() if a.out_dir else base / "movies"
    work.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    trials = cfg["motions"]
    if a.only:
        keys = [k.strip().lower() for k in a.only.split(",")]
        trials = [t for t in trials
                  if any(k in slugify(t.get("label", Path(t["motion_path"]).stem)) for k in keys)]

    server = start_server(a.build, work)
    results: list[tuple[str, str, str]] = []
    try:
        for t in trials:
            # customize convert command here
            label = t.get("label", Path(t["motion_path"]).stem)
            slug = slugify(label)
            viewer_file = work / f"{slug}.gltf"
            out_mp4 = out_dir / f"{slug}.mp4"          # always a FILE with an extension
            t0 = time.time()
            print(f"\n=== {label} -> {out_mp4}")
            try:
                motion = resolve(base, t["motion_path"])
                force = resolve(base, t.get("force_path"))
                for p in (motion, force):
                    if p is not None and not p.is_file():
                        raise FileNotFoundError(p)
                #  ".venv/Scripts/python convert_stage.py --backend ./opensim-viewer/src/backend ID119/opensim/LaiUhlrich2022_KA_scaled.osim ID119/opensim/rc_l1_trimmed.mot ID119/opensim/rc_l1_grf.mot --force ID119/work/run_cut_left.gltf"
                if not a.skip_convert and (a.reconvert or not viewer_file.is_file()):
                    print("  converting ...")
                    command = a.convert_cmd
                    command = command.replace('{motion_path}', str(motion))
                    command = command.replace('{force_path}', str(force))
                    command = command.replace('{viewer_file}', str(viewer_file))
                    command = command.replace('{model_path}', str(model))
                    convert_trial(command, model, motion, force, viewer_file)
                elif not viewer_file.is_file():
                    raise FileNotFoundError(f"{viewer_file} (conversion skipped)")

                size = tuple(t.get("size", (1280, 720)))
                render_movie(
                    server, viewer_file.name, out_mp4,
                    fps=int(t.get("fps", a.fps)),
                    size=size,
                    camera=t.get("camera", "sagittal"),
                    route=a.route,
                    timeout_s=a.timeout,
                    headed=a.headed,
                    probe=not a.no_probe,
                )
                results.append((label, "OK", f"{out_mp4} ({time.time() - t0:.0f}s)"))
            except Exception as e:  # keep going; report at the end
                traceback.print_exc()
                results.append((label, "FAILED", f"{type(e).__name__}: {str(e).splitlines()[0] if str(e) else ''}"))
    finally:
        server.shutdown()

    # Extract numbers from metrics file to be included in the summary
    metrics_list = cfg["metrics"]
    out = {}
    try:
        for metric in metrics_list:
            metric_file = resolve(base, metric.get("file"))
            if metric_file and metric_file.is_file():
                with open(metric_file, 'r') as f:
                    lines = f.readlines()
                    if len(lines) > 1:
                        side = "left"
                        out[side] = {}
                        header = lines[0].strip().split(',')
                        values = lines[1].strip().split(',')
                        metric_data = dict(zip(header, values))
                         # print(f"\n--- {metric.get('label', metric.get('name'))} ---")
                        indx = 0
                        for key, value in metric_data.items():
                            # print(f"{key}: {value}")
                            if key in metric.get("columnLabels", []):
                                value = float(value)
                                unit = metric.get("unit", "")
                                print(f"Found key, Value: {key}: {value} {unit}")
                                out[side][key] = value
                                indx += 1
                        # repeat for lines[2] if it exists
                        if len(lines) > 2:
                            side = "right"
                            out[side] = {}
                            values2 = lines[2].strip().split(',')
                            metric_data2 = dict(zip(header, values2))
                            indx = 0
                            for key, value in metric_data2.items():
                                if key in metric.get("columnLabels", []):
                                    value = float(value)
                                    unit = metric.get("unit", "")
                                    print(f"Found key, Value: {key}: {value} {unit}")
                                    out[side][key] = value
                                    indx += 1
        yaml_output_path = base / "metrics_summary.yaml"
        with open(yaml_output_path, 'w') as yaml_file:
            yaml.dump(out, yaml_file)
        print(f"\nMetrics summary written to {yaml_output_path}")
    except Exception as e:
        print(f"Error occurred while processing metrics: {e}")
    print("\n--- summary ---")
    for label, status, detail in results:
        print(f"{status:7} {label}: {detail}")
    return 0 if all(s == "OK" for _, s, _ in results) else 1

if __name__ == "__main__":
    sys.exit(main())
