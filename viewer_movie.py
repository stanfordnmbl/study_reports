"""Render an OpenSim-viewer animation to MP4 by stepping the viewer's animation clock.

Requires: playwright (`pip install playwright imageio-ffmpeg && playwright install chromium`); ffmpeg comes from PATH or imageio-ffmpeg.
The viewer must be built (npm run build) with CaptureBridge mounted (see CaptureBridge.tsx).

Usage:
    python viewer_movie.py --build vendor/opensim-viewer/build --data work/ \
        --model ik_drop_jump.json --out out/drop_jump.mp4 --fps 30 --camera sagittal
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import http.server
import shutil
import struct
import subprocess
import threading
from pathlib import Path
from urllib.parse import quote

from playwright.sync_api import TimeoutError as PWTimeout
from playwright.sync_api import sync_playwright


class _Handler(http.server.SimpleHTTPRequestHandler):
    """Serves the CRA build + a data dir, with SPA fallback.

    package.json has "homepage": ".", so asset URLs are relative ("./static/...").
    From a nested route like /viewer/<model> they resolve to /viewer/static/..., so any
    path containing /static/ is mapped back to the build root.
    """

    build_dir: Path
    data_dir: Path

    def translate_path(self, path: str) -> str:
        path = path.split("?", 1)[0].split("#", 1)[0]
        if path.startswith("/data/"):
            p = (self.data_dir / path[len("/data/"):]).resolve()
            if self.data_dir.resolve() in p.parents:
                return str(p)
            return str(self.build_dir / "index.html")
        if "/static/" in path:
            path = path[path.index("/static/"):]
        cand = (self.build_dir / path.lstrip("/")).resolve()
        if cand.is_file() and self.build_dir.resolve() in cand.parents:
            return str(cand)
        return str(self.build_dir / "index.html")  # client-side route

    def log_message(self, *args):  # keep stdout clean
        pass


def start_server(build_dir: str | Path, data_dir: str | Path, port: int = 0):
    handler = type("H", (_Handler,), {"build_dir": Path(build_dir), "data_dir": Path(data_dir)})
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def _build_has_bridge(srv) -> bool:
    """Does the served build contain CaptureBridge? (the string window.__viewer survives minification)"""
    root = Path(srv.RequestHandlerClass.build_dir)
    return any(b"__viewer" in f.read_bytes() for f in root.rglob("*.js"))


_NO_MOTION_MSG = (
    "Frames at the start, middle and end of the clip are identical, so the animation is not being applied.\n"
    "Most likely the AnimationAction was never started: in OpenSimGUIScene.tsx, in the "
    "`if (viewerState.isTimeControlledExternally)` branch of useFrame, add BEFORE `action.time = externalTime;`:\n"
    "    if (!action.isRunning()) { action.clampWhenFinished = true; action.paused = false; action.play(); }\n"
    "(mixer.update(0) only applies actions that have been play()ed), then rebuild the viewer.\n"
    "Use --no-probe if this clip really is static."
)


def _probe_motion(page, t0: float, t1: float, fps: int) -> None:
    """Render 3 frames across the clip; identical pixels mean time is not driving the model."""
    hashes = set()
    for t in (t0, (t0 + t1) / 2, max(t0, t1 - 1.0 / fps)):
        png = base64.b64decode(page.evaluate("t => window.__viewer.frame(t)", t))
        hashes.add(hashlib.md5(png).hexdigest())
    if len(hashes) == 1:
        raise RuntimeError(_NO_MOTION_MSG)


def _ffmpeg_exe() -> str:
    """ffmpeg on PATH if present, else the binary bundled with the imageio-ffmpeg package."""
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        raise FileNotFoundError(
            "ffmpeg not found. Either `pip install imageio-ffmpeg` (bundles a binary), or install "
            "ffmpeg (winget install Gyan.FFmpeg) and open a NEW terminal so PATH updates."
        ) from None


def _start_ffmpeg(out: Path, fps: int, w: int, h: int, bg: str) -> subprocess.Popen:
    w2, h2 = w - w % 2, h - h % 2
    # Flatten the (possibly transparent) canvas onto a solid background, force even dimensions.
    graph = (
        f"color=c={bg}:s={w}x{h}:r={fps}[bg];"
        f"[bg][0:v]overlay=shortest=1,crop={w2}:{h2}:0:0,format=yuv420p"
    )
    cmd = [
        _ffmpeg_exe(), "-y", "-loglevel", "error",
        "-f", "image2pipe", "-framerate", str(fps), "-c:v", "png", "-i", "-",
        "-filter_complex", graph,
        "-c:v", "libx264", "-crf", "20", "-movflags", "+faststart", str(out),
    ]
    return subprocess.Popen(cmd, stdin=subprocess.PIPE)


def render_movie(
    srv,
    data_name: str,
    out_mp4: str | Path,
    *,
    fps: int = 30,
    size: tuple[int, int] = (1280, 720),
    camera="sagittal",
    time_range: tuple[float, float] | None = None,
    route: str = "/viewer/{model}",   # check the router in App.tsx; the page reads useParams().urlParam
    background: str = "black",
    timeout_s: int = 90,
    headed: bool = False,
    probe: bool = True,
) -> Path:
    out_mp4 = Path(out_mp4)
    out_mp4.parent.mkdir(parents=True, exist_ok=True)
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    model_param = quote(f"{base}/data/{data_name}", safe="")
    url = base + route.format(model=model_param)
    url += ("&" if "?" in url else "?") + "capture=1&floor=wood&bkgnd=black"

    ff: subprocess.Popen | None = None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=not headed, args=[
                "--use-gl=angle", "--use-angle=swiftshader",
                "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist",
            ])
            # Canvas is 100vw x calc(100vh - 68px) outside GUI mode, so add 68px of height.
            page = browser.new_page(
                viewport={"width": size[0], "height": size[1] + 68}, device_scale_factor=1
            )
            logs: list[str] = []
            page.on("console", lambda m: logs.append(f"[console.{m.type}] {m.text}"))
            page.on("pageerror", lambda e: logs.append(f"[pageerror] {e}"))
            page.on("requestfailed", lambda r: logs.append(f"[requestfailed] {r.url} {r.failure}"))
            page.on("response", lambda r: logs.append(f"[http {r.status}] {r.url}") if r.status >= 400 else None)
            page.goto(url)
            try:
                page.wait_for_function("window.__viewer !== undefined", timeout=timeout_s * 1000)
            except PWTimeout:
                shot = out_mp4.with_suffix(".debug.png")
                page.screenshot(path=str(shot))
                body = (page.evaluate("document.body.innerText") or "").strip()[:500]
                has_canvas = page.evaluate("!!document.querySelector('canvas')")
                in_build = _build_has_bridge(srv)
                raise RuntimeError(
                    "window.__viewer never appeared (CaptureBridge did not mount).\n"
                    f"  URL opened : {url}\n"
                    f"  page URL   : {page.url}\n"
                    f"  screenshot : {shot}\n"
                    f"  page text  : {body!r}\n"
                    f"  canvas in page        : {has_canvas}\n"
                    f"  CaptureBridge in build: {in_build}"
                    + ("" if in_build else "   <-- NOT in the served build: mount <CaptureBridge/> in ModelViewPage and rebuild")
                    + "\n"
                    "  browser log (last 25):\n    " + "\n    ".join(logs[-25:]) + "\n"
                    "Check: viewer rebuilt after the edits? <CaptureBridge/> inside <Canvas>? "
                    "--route matches the router (BrowserRouter '/viewer/{model}' vs HashRouter '/#/viewer/{model}')?"
                ) from None
            info = page.evaluate("window.__viewer.ready()")
            page.evaluate("c => window.__viewer.setCamera(c)", camera)

            # default window = first keyframe of any track .. clip end (not 0, the clip's times are absolute)
            t0, t1 = time_range or (float(info.get("startTime", 0.0)), float(info["duration"]))
            n = max(1, int(round((t1 - t0) * fps)))
            if probe and n > 2:
                _probe_motion(page, t0, t1, fps)
            for i in range(n):  # last sample is t1 - 1/fps, which avoids clamping at clip end
                b64 = page.evaluate("t => window.__viewer.frame(t)", t0 + i / fps)
                png = base64.b64decode(b64)
                if ff is None:
                    w, h = struct.unpack(">II", png[16:24])  # PNG IHDR width/height
                    ff = _start_ffmpeg(out_mp4, fps, w, h, background)
                ff.stdin.write(png)
            browser.close()
    finally:
        if ff is not None:
            ff.stdin.close()
            ff.wait()
    return out_mp4


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", required=True, help="built viewer directory (CRA build/)")
    ap.add_argument("--data", required=True, help="directory holding the viewer model/animation file")
    ap.add_argument("--model", required=True, help="file name inside --data")
    ap.add_argument("--out", required=True)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--camera", default="sagittal")
    ap.add_argument("--route", default="/viewer/{model}", help="e.g. '/#/viewer/{model}' for a HashRouter app")
    ap.add_argument("--timeout", type=int, default=90)
    ap.add_argument("--headed", action="store_true", help="show the browser window for debugging")
    ap.add_argument("--no-probe", action="store_true", help="skip the check that the clip actually moves")
    a = ap.parse_args()

    server = start_server(a.build, a.data)
    print(render_movie(server, a.model, a.out, fps=a.fps, camera=a.camera, route=a.route,
                       timeout_s=a.timeout, headed=a.headed, probe=not a.no_probe))
    server.shutdown()
