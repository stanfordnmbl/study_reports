"""Convert stage: .osim + .mot -> .gltf using the opensim-viewer backend (src/backend).

Why not just call convertNativeFileToGLTF (what lambda_function.py does)?
  * it takes ONE file and, for a .mot, routes to convertMotForce2Gltf, which treats the file as
    FORCE data (arrows). A kinematics motion (IK result) has to go through
    convertOsim2Gltf(osim, geometrySearchPath, motionPaths=[...]) instead.

Backend quirks handled here:
  * initGltf() loads 'basicShapes.gltf' from the CURRENT DIRECTORY, and convertOsim2Gltf adds the
    relative paths 'Geometry' and 'osimConverters/Geometry' to the mesh search path, so the
    conversion must run with cwd = the folder that holds osimConverters/ and basicShapes.gltf.
    It runs in a subprocess with that cwd, which also keeps opensim's global state out of your process.
  * osimConverters/__init__.py imports every converter eagerly (trc, c3d, osimz, ...), so the
    backend's own dependencies (opensim, pygltflib, numpy, and whatever the c3d converter needs) must
    be installed in the Python environment used here.

One motion per output file: the viewer activates every clip in a file at once, so a file with several
motions would play them on top of each other. Convert each motion separately.

Untested here (needs opensim + your backend checkout): run it on one real model/motion first.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

_WORKER = r"""
import sys
import opensim as osim
from osimConverters import *          # same import the Lambda handler uses

osim.Logger.setLevelString('Off')
osim_path, mot_path, force_mot_path, out_path = sys.argv[1:5]
geom_dirs = sys.argv[5:]
for d in geom_dirs[1:]:
    osim.ModelVisualizer.addDirToGeometrySearchPaths(d)
options = osimViewerOptions()
options.setShowMarkers(False)
options.setShowMuscles(False)
gltf = convertOsim2Gltf(osim_path, geom_dirs[0] if geom_dirs else '', [mot_path], options)
gltf = convertForceFileToGltf(force_mot_path, None, gltf)
gltf.save(out_path)
"""


def _sha(paths, extra: str = "") -> str:
    h = hashlib.sha256(extra.encode())
    for p in paths:
        h.update(Path(p).read_bytes())
    return h.hexdigest()[:12]


def inspect_gltf(path: Path) -> dict:
    """Cheap sanity check of what the viewer will see."""
    g = json.loads(path.read_text())
    anims = g.get("animations", [])
    durations = []
    for a in anims:
        for s in a.get("samplers", []):
            mx = g["accessors"][s["input"]].get("max")
            if mx:
                durations.append(float(mx[0]))
    external = [b["uri"] for b in g.get("buffers", []) if "uri" in b and not b["uri"].startswith("data:")]
    return {
        "scene_roots": len(g["scenes"][g.get("scene", 0)].get("nodes", [])),
        "clips": len(anims),
        "duration": max(durations) if durations else None,
        "external_buffers": external,  # must be copied next to the .gltf if not empty
    }


def convert(
    osim_path: str | Path,
    mot_path: str | Path,
    force_mot_path: str | Path,
    out_path: str | Path,
    *,
    backend_dir: str | Path,
    geometry_dirs: list[str | Path] = (),
    force: bool = True,
) -> tuple[Path, dict]:
    """Returns (path to .gltf, info). Cached by hash of the inputs."""
    osim_path, mot_path, force_mot_path = Path(osim_path).resolve(), Path(mot_path).resolve(), Path(force_mot_path).resolve()
    out_path = Path(out_path).resolve()
    backend_dir, out_dir = Path(backend_dir).resolve(), out_path.parent
    for p in (osim_path, mot_path, force_mot_path):
        if not p.is_file():
            raise FileNotFoundError(p)
    if not (backend_dir / "osimConverters").is_dir() or not (backend_dir / "basicShapes.gltf").is_file():
        raise FileNotFoundError(
            f"{backend_dir} must contain osimConverters/ and basicShapes.gltf (the opensim-viewer src/backend folder)"
        )
    geoms = [str(Path(g).resolve()) for g in geometry_dirs]

    out_dir.mkdir(parents=True, exist_ok=True)
    key = _sha([osim_path, mot_path, force_mot_path], extra="|".join(geoms))
    out = out_path
    if out.exists() and not force:
        return out, inspect_gltf(out)

    env = {**os.environ, "PYTHONPATH": str(backend_dir) + os.pathsep + os.environ.get("PYTHONPATH", "")}
    proc = subprocess.run(
        [sys.executable, "-c", _WORKER, str(osim_path), str(mot_path), str(force_mot_path), str(out), *geoms],
        cwd=backend_dir, env=env, capture_output=True, text=True,
    )
    if proc.returncode != 0 or not out.exists():
        raise RuntimeError(f"backend conversion failed:\n{proc.stdout}\n{proc.stderr}")

    info = inspect_gltf(out)
    if info["scene_roots"] != 1:
        print(f"[warn] {out.name}: {info['scene_roots']} top-level scene nodes; "
              "OpenSimGUIScene builds its mixer on children[0] only")
    if info["clips"] != 1:
        print(f"[warn] {out.name}: {info['clips']} animation clips (expected 1)")
    return out, info


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("osim")
    ap.add_argument("motion")
    ap.add_argument("force_motion")
    ap.add_argument("out_dir")
    ap.add_argument("--backend", required=True, help="opensim-viewer/src/backend checkout")
    ap.add_argument("--geom", action="append", default=[], help="extra Geometry folder (repeatable)")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    path, info = convert(a.osim, a.motion, a.force_motion, a.out_dir, backend_dir=a.backend, geometry_dirs=a.geom, force=a.force)
    print(path, info)
