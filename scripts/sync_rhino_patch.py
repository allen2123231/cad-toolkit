"""Developer helper: capture only the owned Rhino changes against the pinned commit."""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
FILES = ["plugin/ToolkitIdentity.cs", "plugin/RhinoMCPPlugin.cs", "plugin/InstanceStatusFile.cs",
         "plugin/RhinoMCPServer.cs", "plugin/Functions/DescribeCapabilities.cs", "plugin/WindowTitleTag.cs",
         "plugin/rhinomcp.csproj", "plugin/manifest.yml", "server/pyproject.toml", "server/src/rhinomcp/server.py"]


def main():
    parser = argparse.ArgumentParser(); parser.add_argument("checkout", type=Path); args = parser.parse_args()
    manifest = ROOT / "sources.json"; sources = json.loads(manifest.read_text(encoding="utf-8"))
    spec = sources["components"]["rhino"]
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=args.checkout, text=True).strip()
    if head != spec["commit"]: raise ValueError("Checkout HEAD must match the pinned baseline")
    parts = []
    for name in FILES:
        prior = subprocess.run(["git", "show", "HEAD:"+name], cwd=args.checkout, capture_output=True)
        old = prior.stdout.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n") if prior.returncode == 0 else ""
        new = (args.checkout / name).read_text(encoding="utf-8")
        if old == new: continue
        parts.append(f"diff --git a/{name} b/{name}\n")
        if prior.returncode: parts.append("new file mode 100644\n")
        for line in difflib.unified_diff(old.splitlines(True), new.splitlines(True), fromfile="a/"+name if prior.returncode == 0 else "/dev/null", tofile="b/"+name):
            parts.append(line if line.endswith("\n") else line+"\n\\ No newline at end of file\n")
    target = ROOT / spec["patch"]
    target.write_text("".join(parts), encoding="utf-8", newline="\n")
    spec["patch_sha256"] = hashlib.sha256(target.read_bytes()).hexdigest()
    manifest.write_text(json.dumps(sources, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(spec["patch_sha256"])


if __name__ == "__main__": main()
