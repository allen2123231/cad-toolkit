"""Build an immutable Windows payload from exact source commits and hashed locks."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tomllib
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))
from common import atomic_json, download, extract_zip, read_json, run, sha256

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh-locks", action="store_true")
    parser.add_argument("--dotnet", default="dotnet")
    args = parser.parse_args()
    sources = read_json(ROOT / "sources.json")
    build = ROOT / ".build"
    payload = build / "payload"
    payload.mkdir(parents=True, exist_ok=True)
    dist = ROOT / "dist"
    dist.mkdir(exist_ok=True)
    tools = build / "tools"
    tools.mkdir(exist_ok=True)
    uv_zip = tools / "uv.zip"
    if not uv_zip.exists(): download(f"https://github.com/astral-sh/uv/releases/download/{sources['uv']}/uv-x86_64-pc-windows-msvc.zip", uv_zip)
    extract_zip(uv_zip, tools / "uv")
    uv = next((tools / "uv").rglob("uv.exe"))
    shutil.copy2(uv, payload / "uv.exe")
    for name in ("LICENSE-MIT", "LICENSE-APACHE"):
        license_path = payload / "licenses/uv" / name
        if not license_path.exists(): download(f"https://raw.githubusercontent.com/astral-sh/uv/{sources['uv']}/{name}", license_path)
    env = os.environ.copy()
    env.update(PYTHONUTF8="1", UV_PYTHON_INSTALL_DIR=str(build / "python"))
    print("Preparing Python runtime", flush=True)
    run([uv, "python", "install", sources["python"]], env=env)
    python = Path(run([uv, "python", "find", "--managed-python", sources["python"]], env=env).strip())
    if not (payload / "runtime/python.exe").exists(): shutil.copytree(python.parent, payload / "runtime", dirs_exist_ok=True)
    shutil.copytree(ROOT / "engine", payload / "engine", dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__"))
    run([uv, "pip", "install", "--python", python, "--target", payload / "engine/vendor", "tomlkit==0.13.3"])
    shutil.copytree(ROOT / "plugins", payload / "plugins", dirs_exist_ok=True)
    shutil.copytree(ROOT / "docs", payload / "docs", dirs_exist_ok=True)
    shutil.copy2(ROOT / "LICENSE", payload / "LICENSE")
    components = {}
    for name, spec in sources["components"].items():
        print("Building " + name, flush=True)
        archive = build / (name + "-" + spec["commit"] + ".zip")
        if not archive.exists(): download(f"https://codeload.github.com/{spec['repo']}/zip/{spec['commit']}", archive)
        source_root = build / "sources" / name
        if not source_root.exists(): extract_zip(archive, source_root)
        source = next(source_root.iterdir())
        project = source / spec["subdir"]
        lock = ROOT / "locks" / (name + ".txt")
        if args.refresh_locks or not lock.exists():
            lock.parent.mkdir(exist_ok=True)
            deps = tomllib.loads((project / "pyproject.toml").read_text(encoding="utf-8"))["project"]["dependencies"]
            if name in ("autocad", "inventor"): deps.append("mcp<2")
            req = build / (name + ".in")
            req.write_text("\n".join(deps), encoding="utf-8")
            run([uv, "pip", "compile", req, "--python-version", "3.12", "--python-platform", "windows",
                 "--generate-hashes", "--no-annotate", "--no-header", "--output-file", lock])
        wheel_dir = payload / "wheels" / name
        wheel_dir.mkdir(parents=True, exist_ok=True)
        run([uv, "build", "--wheel", "--out-dir", build / "project-wheels" / name, str(project)], env=env)
        wheel = next((build / "project-wheels" / name).glob("*.whl"))
        shutil.copy2(wheel, wheel_dir / wheel.name)
        run([sys.executable, "-m", "pip", "download", "--only-binary=:all:", "--python-version", "3.12",
             "--platform", "win_amd64", "--implementation", "cp", "--abi", "cp312", "--require-hashes",
             "-r", lock, "-d", wheel_dir], timeout=900)
        (payload / "locks").mkdir(exist_ok=True)
        shutil.copy2(lock, payload / "locks" / lock.name)
        licenses = payload / "licenses" / name
        licenses.mkdir(parents=True, exist_ok=True)
        for license_file in source.glob("LICENSE*"): shutil.copy2(license_file, licenses / license_file.name)
        if name == "autocad": shutil.copytree(source / "lisp-code", payload / "cad/autocad", dirs_exist_ok=True)
        if name == "rhino":
            run([args.dotnet, "build", source / "plugin/rhinomcp.csproj", "-c", "Release"], timeout=900)
            shutil.copytree(source / "plugin/bin/Release/net8.0", payload / "cad/rhino", dirs_exist_ok=True)
        components[name] = {**spec, "wheel": wheel.name}
    files = {p.relative_to(payload).as_posix(): sha256(p) for p in sorted(payload.rglob("*"))
             if p.is_file() and p.name != "bundle.json" and "__pycache__" not in p.parts}
    atomic_json(payload / "bundle.json", {"schema": 1, "version": sources["version"], "python": sources["python"],
                                         "uv": sources["uv"], "components": components, "files": files})
    archive = dist / "cad-toolkit-payload.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for p in sorted(payload.rglob("*")):
            if p.is_file() and "__pycache__" not in p.parts: z.write(p, p.relative_to(payload))
    atomic_json(ROOT / "installer/release.json", {"version": sources["version"], "payload": {
        "url": f"https://github.com/allen2123231/cad-toolkit/releases/download/v{sources['version']}/cad-toolkit-payload.zip",
        "sha256": sha256(archive), "size": archive.stat().st_size}})
    print("Payload ready: " + str(archive), flush=True)

if __name__ == "__main__": main()
