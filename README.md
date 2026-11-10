# Report creation tools

Tools for creating participant reports for various studies utilizing OpenSim ecosystem

## Getting started (Windows)

You need Python 3.11+ and git. 

1. Clone the repo and create a virtual environment:

   ```powershell
   git clone https://github.com/stanfordnmbl/study_reports.git
   cd study_reports
   py -3.13 -m venv .venv
   .venv/Scripts/activate
   ```

2. Install the requirements

   ```powershell
   pip install -r requirements.txt"
   ```

3. Add the OpenSim viewer backend, which exports the model to 3D:

   ```powershell
   git clone --depth 1 https://github.com/opensim-org/opensim-viewer-backend.git vendor\opensim-viewer-backend
   ```

4. 







4. Open a dataset:

   ```powershell
   .venv\Scripts\osdr C:\path\to\dataset
   ```

   This starts a local server and opens the dashboard in your browser. Press Ctrl+C
   to stop it. Run `osdr` with no folder to get a folder picker and your recent
   datasets. You can also double-click `osdr.bat`, or drag a folder onto it.

The server only listens on `127.0.0.1`, so your data never leaves the machine. The
tool keeps its recent-datasets list and caches in `%APPDATA%\osdr`. `osdr index
<folder>` prints the same summary in the terminal.

### On a Mac (or Linux)

The steps are the same, with Unix paths:

```bash
git clone https://github.com/stanfordnmbl/OpenSimDataReviewer.git
cd OpenSimDataReviewer
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[model]"
git clone --depth 1 https://github.com/opensim-org/opensim-viewer-backend.git vendor/opensim-viewer-backend
.venv/bin/osdr /path/to/dataset
```

- **Python 3.11–3.13:** OpenSim's pip wheels only exist for these versions. On macOS
  they need **macOS 15 or later** (Apple Silicon and Intel).
- **Browse… button:** it uses tkinter. The python.org installer includes it; with
  Homebrew's Python run `brew install python-tk@3.11` (matching your version), or just
  paste the folder path instead.
- **No `osdr.bat`:** that launcher is Windows-only.
- **Settings and caches** live in `~/.config/osdr` instead of `%APPDATA%\osdr`.

### Reviewing trials

Click a trial in the dashboard to give it a status (OK, Reprocess or Exclude) and a
note. Each trial's review is saved as one small JSON file next to its results. For
`process-acl-data` that's `OpenSimData\IK\<trial>_annotations.json`:

```json
{ "version": 1, "trial": "Squatting Markerless 1", "status": "reprocess",
  "note": "occlusion at the bottom of the squat", "updated": "2026-09-25T19:34:56Z" }
```

You can also review from the trial viewer, in the Review card. Clearing both the
status and the note deletes the file. Besides these, the only files the tool writes
into a dataset are the force labels below.

### The OpenSim model in 3D

With the `model` extra and the viewer backend (steps 2–3), each participant's model is
exported to glTF once, and each trial's body poses are computed the first time you
view it (about 2 s for a 30 s trial). Both are cached in `%APPDATA%\osdr\cache`, and
nothing is written to the dataset. Without them, the viewer's model options are
disabled and say why.

### Ground reaction forces

For **Mocap** trials, the trial viewer also reads `OpenSimData\ID\<trial>_grf.mot` and
`<trial>_contact_windows.csv` from process-acl-data's forces step. Each force plate is
drawn as an arrow from its centre of pressure (adjustable in m per kN), and Fx, Fy
(vertical) and Fz are plotted per plate with the contact windows shaded, all synced
to the scrubber. Theia trials have no forces: the pipeline doesn't write them, because
the separate force recording has no shared clock with Theia.

Force plates are outlined and numbered on the floor, and filled while loaded. The
outlines come from `ID\<trial>_force_plates.json` when the pipeline wrote one. For
older output, they come from the trial's original recording in
`<participant>\Mocap\C3D\<trial>.c3d`. A C3D stores the plates in the lab frame, so
the tool finds the lab→OpenSim rotation by matching the C3D's markers to the trial's
TRC. If they don't agree to within 5 mm, it draws no outlines rather than misplaced
ones. Only the C3D's parameters and marker positions are read, by a small built-in
reader.

**Contact checks** flag force-plate data to look at twice, after AddBiomechanics's
missing-GRF detector. They are suggestions only: nothing is changed or saved.
They run on the kinematics' frames, with the forces resampled onto them, and the
feet come from the posed model: 5 points per foot on the calcn and toes meshes, as
AddBiomechanics places them. Per plate, except the last, which is per foot:

| Check | Flagged when |
|---|---|
| Brief contact | a contact (\|F\| > 10 N) under 10 frames or 10 N·s |
| Force outlier | \|F\| on one plate > 4× body weight (mass from the scaled model), or 4000 N without a model. AddBiomechanics uses 2500 N, which landings exceed legitimately |
| CoP outside the feet | the force-weighted CoP is more than 2 cm from the nearest foot over a contact |
| Both feet on one plate | both feet are down over the same loaded plate (needs plate outlines) |
| Foot partly off the plate | the loaded foot extends more than 1 cm past the plate's edge (needs outlines) |
| Edge ramp | AddBiomechanics's "extended to nearest peak force": each contact's loading and unloading ramps (hidden by default) |
| Foot on the ground, no force | a foot is down while no plate measures it and it isn't over any plate: a step that missed the plates (needs outlines; see below) |

The last check is from kinematics: nimblephysics's foot-height heuristic, which
AddBiomechanics used before its current force-only detector. The ground height
comes from the plate outlines. Each foot point's contact height is learned from
the trial: the highest it sits above the ground while it's the foot's lowest point
and that foot carries a plate's force (CoP within 2 cm of it). A point counts as
down below that height, with 5 cm more slack when it isn't over a plate. One guard
is added: a foot moving faster than 2 m/s across the floor is swinging, not down.
Findings shorter than 0.05 s are dropped. These aren't on a plate, so they show on
every plate's strip in the force labels.

**Force labels** record which spans of the trial's force data are invalid, as in
AddBiomechanics's review timeline. There's one valid/invalid call per frame, shared
by every plate. There's still one strip per plate under the scrubber, so each plate's
contact windows and suggestions stay visible, but marking a span on any strip marks
it on all of them. Drag along a strip to mark frames invalid; a drag that starts on
an invalid span marks frames valid again, and the current frame follows the drag.
"Mark suggestions invalid" marks the span of each contact-check finding, and "Forces
reviewed" records that you finished the trial. Plates are drawn red in 3D while the
current frame is invalid. Labels save automatically a moment after each edit
(or right away with Save, and before you leave the page) to
`OpenSimData\ID\<trial>_grf_labels.json`, as time spans in seconds on the trial's
clock, with the same spans listed under every plate:

```json
{ "version": 1, "trial": "CutL1",
  "plates": [{ "plate": 2, "invalid": [[0.31, 0.48]] }],
  "reviewed": true, "updated": "2026-10-06T19:34:56Z" }
```

A plate with no spans is valid throughout. Files saved before labels were shared
(different spans per plate) open as the union of their plates' spans, and are
rewritten that way on the next edit. Clearing every span on a trial that isn't
marked reviewed deletes the file.

Without the `model` extra only the force checks run. A foot point only counts as
"down" within 3 cm of the lowest any foot point gets in the trial, so a heel lifting
at toe-off doesn't count as off the plate.

## Supported sources

The layout is detected automatically when you open a folder.

- **process-acl-data** (Theia markerless and/or Mocap marker-based):
  `<participant>\{Theia,Mocap}\OpenSimData\{MarkerData,IK,Models}`. The errors are
  read from the pipeline's own JSON and timeseries CSV files. For Mocap the pipeline
  writes no per-frame errors, so the viewer's error plots are computed the first time
  you open a trial (a few seconds; **needs the `model` extra**) and cached in
  `%APPDATA%\osdr\cache`. Older runs have only `ik` and `bilevel` solutions (`.mot` or
  `.sto`). If no trial in the dataset has a `kinematics` stage, the `bilevel` stage is
  shown instead.
- **opensim-fitter** (marker-based): the layout from its examples. You can open a
  folder of participants, or one participant's folder directly:

  ```
  <participant>\
      <trial>.trc                       marker data (may also be in results\)
      results\                          (optional; everything may be flat instead)
          <trial>_bilevel_solution.sto  shown by default
          <trial>_ik_solution.sto       shown when there's no bilevel fit
          *bilevel_scaled*.osim         model for the bilevel solution
          *marker_scaled*.osim          model for the IK solution
  ```

  A trial pairs with `<trial>.trc`. If a participant has exactly one trial and one TRC,
  they pair whatever their names, as in `example_walk`. opensim-fitter writes no error
  files, so the tool computes marker error itself, the same way as osimfit's
  `compute_marker_errors`, by posing the model at every solution frame. This **needs
  the `model` extra** (Getting started, step 2). Results are cached in `%APPDATA%\osdr\cache`, and the
  first open of a trial takes a second or two. Model markers must have the same names
  as the TRC markers.

## Scope

The tool never reads video. It only picks up known file types inside known
folders: `.trc`, `.sto`, `.mot`, `.json`, `.csv`, `.osim`, `.pdf`, `.c3d`, and
model geometry.

## Development

```powershell
.venv\Scripts\python.exe -m pip install -e ".[dev]"
.venv\Scripts\python.exe tests\fixtures\make_acl_fixture.py   # optional, needs C:\ACL_Results
.venv\Scripts\python.exe -m pytest
```

The ACL fixture is 1 participant with 2 trials copied from `C:\ACL_Results`. It's real
participant data, so it is generated locally and gitignored. Tests that need it skip
when it's absent.

Layout:

```
src/osdr/core/       data model, readers (TRC, STO/MOT, error series), summaries, annotations
src/osdr/adapters/   one adapter per source layout (acl, fitter)
src/osdr/model3d.py  OpenSim posing, glTF export and computed marker errors (model extra)
src/osdr/api.py      JSON payloads for the browser
src/osdr/server.py   local HTTP server
src/osdr/cli.py      the `osdr` command
viewer/              the browser front end: plain JS, no build step
```

The TRC/STO readers and the server are ported from `review-sprinting-data`.
