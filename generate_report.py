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

import yaml


def _sha(paths, extra: str = "") -> str:
    h = hashlib.sha256(extra.encode())
    for p in paths:
        h.update(Path(p).read_bytes())
    return h.hexdigest()[:12]

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
         f"D:\\dev\\src\\report_fresh\\study_reports\\.venv\\Scripts\\python {Path(__file__).parent / 'convert_stage.py'} --backend D:\\dev\\src\\report_fresh\\study_reports\\vendors\\opensim-viewer-backend {{model_path}} {{motion_path}} {{force_path}} {{viewer_file}}"],
        cwd=subject_path,
        check=True,
    )

    # at this point, the movies and metrics_summary should be generated in the subject folder
    # copy the values from metrics_summary into subject_folder/smart_study_report.html
    metrics_summary_path = subject_path / "metrics_summary.yaml"
    if metrics_summary_path.is_file():
        with open(metrics_summary_path, 'r') as f:
            metrics_summary = yaml.safe_load(f)
        report_html_path = subject_path / "smart_study_report.html"
        with open(report_html_path, 'r') as f:
            report_html = f.read()
        report_html = report_html.replace("ParticipantID", subject_path.name)
        for key, value in metrics_summary.items():
            report_html = report_html.replace(f"{{{{{key}}}}}", str(value))
        with open(report_html_path, 'w') as f:
            f.write(report_html)

    # Now the report should be fully generated in the subject folder
    # run a command to embed the movies into the report
    movies_dir = subject_path / "movies"
    if movies_dir.is_dir():
        for movie in movies_dir.glob("*.mp4"):
            report_html_path = subject_path / "smart_study_report.html"
            with open(report_html_path, 'r') as f:
                report_html = f.read()
            report_html = report_html.replace(
                f"{{{{movie_{movie.stem}}}}}",
                f'<video controls src="{movie.name}"></video>'
            )
            with open(report_html_path, 'w') as f:
                f.write(report_html)
