"""Build and verify the local course submission archive with its frozen evidence."""

import argparse
import hashlib
import os
import re
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "release"
ARCHIVE = DIST / "LumiRead_MVP.zip"
ALLOWED = (
    "apps",
    "ml",
    "data",
    "packages",
    "scripts",
    "tests",
    "docs",
    "artifacts",
    "reports",
)
DENIED = {
    "demo_accounts.json",
    "node_modules",
    "dist",
    "__pycache__",
    ".git",
    ".cache",
    ".pytest_cache",
    ".venv",
    ".ruff_cache",
    ".DS_Store",
    "test-results",
}
FILES = [
    "README.md",
    "GENAI_LOG.md",
    "Makefile",
    "pyproject.toml",
    "uv.lock",
    ".gitignore",
]
NEEDED = [
    "data/dkt/demo_selection.json",
    "data/clouclip/segments.json",
    "data/clouclip/Sample_Clouclip.csv",
    "data/clouclip/LICENSE",
    "data/eyecare/simulated_week.csv",
    "artifacts/ritw/metrics.json",
    "artifacts/ritw/replays.json",
    "artifacts/ritw/baselines.json",
    "artifacts/ritw/SHA256SUMS",
    "data/demo/worksheet-original.png",
    "data/demo/worksheet-revised.png",
    "artifacts/federated/report.json",
    "artifacts/federated/checksums.json",
    "reports/desktop_rehearsal.json",
    "reports/desktop_vision_receipts.json",
    "reports/vision_evaluation.json",
    "apps/web/public/products/clip.glb",
    "apps/web/public/products/frame.glb",
    "apps/web/public/products/clip.webp",
    "apps/web/public/products/frame.webp",
    "apps/web/public/products/frame-open.webp",
    "apps/web/public/products/frame-inside.webp",
    "apps/web/public/products/poster-points.json",
    "apps/web/public/products/fawn.webp",
    "apps/web/public/vision/paper-marker.svg",
    "artifacts/dkt/checksums.json",
    "data/dkt/skill_mapping.json",
    "data/vision/lux-results.json",
    "reports/LumiRead_Roadshow.html",
    "reports/LumiRead_Business_and_ML.pdf",
    "reports/iphone_evidence.json",
    "reports/provider_smoke.json",
    "reports/training_shutdown.json",
    "reports/LumiRead_Online_Replay.webm",
    "reports/replay.json",
]
SENSITIVE = re.compile(
    rb"sk-(?:proj-[A-Za-z0-9_-]{30,}|[a-f0-9]{32}\b)|-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----"
)


def paths():
    for d in ALLOWED:
        for folder, dirs, files in os.walk(ROOT / d):
            dirs[:] = [n for n in dirs if n not in DENIED and not n.startswith(".")]
            for name in sorted(files):
                p = Path(folder) / name
                if (
                    name in DENIED
                    or (name.startswith(".") and name != ".env.example")
                    or p.is_symlink()
                ):
                    continue
                if p.suffix in {".pyc", ".sqlite3", ".key", ".pem", ".tar", ".zip"}:
                    continue
                if (
                    p.parent == ROOT / "reports"
                    and p.suffix == ".webm"
                    and p.name
                    not in ("LumiRead_Online_Replay.webm", "LumiRead_Rehearsal.webm")
                ):
                    continue
                yield p
    yield from (ROOT / n for n in FILES)


def check():
    for name in FILES + NEEDED:
        p = ROOT / name
        if not p.is_file() or p.stat().st_size < 1:
            raise SystemExit("Missing deliverable: " + name)


def pack():
    check()
    DIST.mkdir(exist_ok=True)
    temp = ARCHIVE.with_suffix(".tmp")
    with zipfile.ZipFile(
        temp, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=5
    ) as z:
        for p in sorted(paths()):
            if p.suffix.lower() in {
                ".py",
                ".ts",
                ".tsx",
                ".sh",
                ".js",
                ".mjs",
                ".md",
                ".txt",
                ".json",
                ".csv",
                ".html",
                ".yaml",
                ".yml",
                ".toml",
                ".example",
            } and SENSITIVE.search(p.read_bytes()):
                raise SystemExit("Sensitive material in " + str(p.relative_to(ROOT)))
            z.write(p, "project/" + str(p.relative_to(ROOT)))
    temp.replace(ARCHIVE)
    print(ARCHIVE, ARCHIVE.stat().st_size, "bytes")


def verify():
    with zipfile.ZipFile(ARCHIVE) as z:
        if z.testzip():
            raise SystemExit("Corrupt archive")
        expected = {str(p.relative_to(ROOT)) for p in paths()}
        actual = {n.removeprefix("project/") for n in z.namelist()}
        if expected != actual:
            raise SystemExit(
                "Course archive inventory differs from the project. Run make course-package."
            )
        for n in actual:
            with z.open("project/" + n) as member, (ROOT / n).open("rb") as original:
                matches = (
                    hashlib.file_digest(member, "sha256").digest()
                    == hashlib.file_digest(original, "sha256").digest()
                )
            if not matches:
                raise SystemExit("Stale archive member: " + n)
    print(
        "Archive verified",
        hashlib.file_digest(ARCHIVE.open("rb"), "sha256").hexdigest(),
    )


def reproduce():
    pack()
    verify()
    with tempfile.TemporaryDirectory(prefix="lumiread-clean-") as folder:
        root = Path(folder) / "project"
        with zipfile.ZipFile(ARCHIVE) as z:
            z.extractall(folder)
        for s in ("scripts/web.sh",):
            (root / s).chmod(0o755)
        uv = shutil.which("uv") or str(Path.home() / ".local/bin/uv")

        def run(cmd):
            subprocess.run(cmd, cwd=root, check=True)

        run(
            [
                uv,
                "sync",
                "--frozen",
                "--offline",
                "--cache-dir",
                str(ROOT / ".cache/uv"),
                "--python",
                "3.11",
            ]
        )
        run(
            [
                "sh",
                "scripts/web.sh",
                "install",
                "--offline",
                "--frozen-lockfile",
                "--store-dir",
                str(ROOT / ".cache/pnpm"),
            ]
        )
        # Reuse the operator's original ZIP locally. It never enters the distribution.
        archive = ROOT / ".cache/dkt/assistments2009.zip"
        if archive.exists():
            cached = root / ".cache/dkt/assistments2009.zip"
            cached.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(archive, cached)
        run(["make", "demo-accounts", "web", "doctor", "verify-models", "test-contract"])
        run([str(root / ".venv/bin/python"), "scripts/verify_desktop.py", "--clean-smoke"])
    print(
        "Clean installation from the source archive passed using cached locked dependencies."
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["check", "pack", "verify", "reproduce"])
    {"check": check, "pack": pack, "verify": verify, "reproduce": reproduce}[
        parser.parse_args().action
    ]()
