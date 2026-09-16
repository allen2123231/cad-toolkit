"""Shared, standard-library-only installation primitives."""
import contextlib
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import urllib.request
import zipfile

COMPONENTS = ("autocad", "inventor", "rhino")
SKILLS = {
    "cad-setup-diagnostics": (), "cad-file-handoff": (),
    "autocad-drafting": ("autocad",), "inventor-modeling": ("inventor",),
    "inventor-standard-parts": ("inventor",), "rhino-modeling": ("rhino",),
}

def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))

def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)

def sha256(path):
    with open(path, "rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()

def within(root, relative):
    target = (Path(root) / relative).resolve()
    if not target.is_relative_to(Path(root).resolve()) or target == Path(root).resolve():
        raise ValueError("路徑超出管理範圍")
    return target

def extract_zip(archive, destination):
    with zipfile.ZipFile(archive) as z:
        for item in z.infolist():
            within(destination, item.filename.replace("\\", "/"))
            if (item.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError("壓縮檔含符號連結")
        z.extractall(destination)

def download(url, path, expected=None):
    if not url.startswith("https://"):
        raise ValueError("下載必須使用 HTTPS")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".part")
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "cad-toolkit"})
        with urllib.request.urlopen(request, timeout=120) as response, temp.open("wb") as out:
            while chunk := response.read(1024 * 1024):
                out.write(chunk)
        if expected and sha256(temp) != expected.lower():
            raise ValueError("下載檔案 SHA-256 不符")
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)

def run(args, *, env=None, cwd=None, timeout=600):
    result = subprocess.run([str(x) for x in args], cwd=cwd, env=env, text=True,
                            encoding="utf-8", errors="replace", capture_output=True,
                            timeout=timeout, creationflags=0x08000000 if os.name == "nt" else 0)
    if result.returncode:
        raise RuntimeError(f"指令失敗 ({result.returncode}): {args[0]}\n{result.stderr[-5000:]}\n{result.stdout[-2000:]}")
    return result.stdout

@contextlib.contextmanager
def install_lock(root):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    file = (root / "operation.lock").open("a+b")
    try:
        if os.name == "nt":
            import msvcrt
            file.seek(0); file.write(b"0"); file.flush(); file.seek(0)
            try:
                msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                raise RuntimeError("另一個安裝或更新作業正在進行")
        yield
    finally:
        file.close()
