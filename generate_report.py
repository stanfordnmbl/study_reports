""" Convert subject folder XXXX passed in to a report file within the folder
XXXX with the name smart_study_report.html
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
import base64, mimetypes, re

import yaml


def _sha(paths, extra: str = "") -> str:
    h = hashlib.sha256(extra.encode())
    for p in paths:
        h.update(Path(p).read_bytes())
    return h.hexdigest()[:12]

def flatten(d, parent="", sep="."):
    out = {}
    for k, v in d.items():
        key = f"{parent}{sep}{k}" if parent else str(k)
        if isinstance(v, dict):
            out.update(flatten(v, key, sep))
        else:
            out[key] = v
    return out

def to_data_uri(path: Path) -> str:
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"

def embed_media(html_path, out_path=None):
    html_path = Path(html_path)
    base_dir = html_path.parent

    def embed(match):
        key, rel = match.group(1), match.group(2)
        file = base_dir / rel
        if not file.exists():
            print(f"missing, left as-is: {rel}")
            return match.group(0)
        return f'{key}:"{to_data_uri(file)}"'

    html = html_path.read_text(encoding="utf-8")
    html = re.sub(r'\b(src):"(movies/[^"]+)"', embed, html)

    out_path = Path(out_path) if out_path else html_path.with_name(html_path.stem + "_embedded.html")
    out_path.write_text(html, encoding="utf-8")
    return out_path

if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("subject_folder")
    a = ap.parse_args()

    subject_path = Path(a.subject_folder).resolve()
    # copy subject.yaml to the subject folder
    subject_yaml_path = Path(__file__).with_name("subject.yaml")
    shutil.copy(subject_yaml_path, subject_path / subject_yaml_path.name)   
    subject_yaml = subject_path / subject_yaml_path.name
    # copy smart_study_report_template.html to the subject folder
    report_template_path = Path(__file__).with_name("smart_study_report_template.html")
    shutil.copy(report_template_path, subject_path / "smart_study_report.html")

    # now run the script run_manifest_movies.py to generate the movies and metrics_summary
    # pass in 
    print(subject_path)
    repo_root = Path(__file__).parent
    subprocess.run(
        [sys.executable, 
         str(Path(__file__).with_name("run_manifest_movies.py")),
         str(subject_yaml),
         "--build",
         str((Path(__file__).parent / "viewer-build" / "build").resolve()),
         "--work",
         str(subject_path / "work"),
         "--out-dir",
         str(subject_path / "movies"),
         "--convert-cmd",
         f"{Path(__file__).parent / '.venv' / 'Scripts' / 'python'} {Path(__file__).parent / 'convert_stage.py'} --backend {Path(__file__).parent / 'vendors' / 'opensim-viewer-backend'} {{model_path}} {{motion_path}} {{force_path}} {{viewer_file}}"],
        cwd=subject_path,
        check=True,
    )

    # at this point, the movies and metrics_summary should be generated in the subject folder
    # copy the values from metrics_summary into subject_folder/smart_study_report.html
    metrics_summary_path = subject_path / "metrics_summary.yaml"
    if metrics_summary_path.is_file():
        report_html_path = subject_path / "smart_study_report.html"
        with open(report_html_path, 'r') as f:
            report_html = f.read()
        report_html = report_html.replace("ParticipantID", subject_path.name)
        with open(metrics_summary_path) as f:
            data = yaml.safe_load(f)

        flat = flatten(data)
        for key, value in flat.items():
            print(key, value)
            report_html = report_html.replace(f"{{{{{key}}}}}", str(value))
        with open(report_html_path, 'w') as f:
            f.write(report_html)

    # Now the report should be fully generated in the subject folder
    # run a command to embed the movies into the report
    embed_media(subject_path / "smart_study_report.html")

