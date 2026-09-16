import json
from pathlib import Path
import shutil
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))
from common import atomic_json, read_json, sha256
release = read_json(ROOT / "installer/release.json")
exe = ROOT / "dist/CadToolkitSetup.exe"
shutil.copy2(ROOT / "dist/setup/CadToolkitSetup.exe", exe)
release["setup"] = {"url": f"https://github.com/allen2123231/cad-toolkit/releases/download/v{release['version']}/CadToolkitSetup.exe",
                    "sha256": sha256(exe), "size": exe.stat().st_size}
atomic_json(ROOT / "dist/release-manifest.json", release)
paths = [exe, ROOT / "dist/cad-toolkit-payload.zip", ROOT / "dist/release-manifest.json"]
(ROOT / "dist/SHA256SUMS.txt").write_text("\n".join(f"{sha256(p)}  {p.name}" for p in paths)+"\n")
print(json.dumps(release, indent=2))
