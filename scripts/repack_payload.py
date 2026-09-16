"""Refresh application content without rebuilding locked third-party binaries."""
from pathlib import Path
import shutil
import sys
import zipfile
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))
from common import atomic_json, read_json, sha256
payload = ROOT / ".build/payload"
for folder in ("engine", "plugins", "docs"):
    shutil.copytree(ROOT / folder, payload / folder, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__"))
manifest = read_json(payload / "bundle.json")
manifest["files"] = {p.relative_to(payload).as_posix(): sha256(p) for p in sorted(payload.rglob("*"))
                     if p.is_file() and p.name != "bundle.json" and "__pycache__" not in p.parts}
atomic_json(payload / "bundle.json", manifest)
archive = ROOT / "dist/cad-toolkit-payload.zip"
with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
    for p in sorted(payload.rglob("*")):
        if p.is_file() and "__pycache__" not in p.parts: z.write(p, p.relative_to(payload))
release = read_json(ROOT / "installer/release.json")
release["payload"].update(sha256=sha256(archive), size=archive.stat().st_size)
atomic_json(ROOT / "installer/release.json", release)
print("Repacked " + str(archive))
