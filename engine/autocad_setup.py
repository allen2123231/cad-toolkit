"""Per-user, per-document AutoCAD application bundle; no APPLOAD or profile edits."""
import os
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET
from common import atomic_json, read_json, sha256

PRODUCT = "{DAF198E8-24CA-49A9-8931-5F292A0A3D31}"


def install_bundle(target, appdata=None):
    target = Path(target).resolve()
    source = target / "autocad"
    if not (source / "mcp_dispatch.lsp").is_file():
        raise RuntimeError("請先安裝 AutoCAD 連線工具。")
    base = Path(appdata or os.environ["APPDATA"]) / "Autodesk/ApplicationPlugins"
    bundle = base / "McpToolkit.bundle"
    if bundle.exists():
        try:
            if ET.parse(bundle / "PackageContents.xml").getroot().get("ProductCode") != PRODUCT:
                raise ValueError("同名 AutoCAD 套件不屬於 Toolkit，已保留原檔。")
        except ET.ParseError as exc:
            raise ValueError("AutoCAD 套件清單不可讀，請先保留檔案再修復。") from exc
    bundle.mkdir(parents=True, exist_ok=True)
    contents = bundle / "Contents"
    contents.mkdir(exist_ok=True)
    # Only this owned bundle is touched. Never changes SECURELOAD/TRUSTEDPATHS.
    for file in source.glob("*.lsp"):
        shutil.copy2(file, contents / file.name)
    version = read_json(target / "ready.json").get("version", "0.0.0").split("-")[0]
    package = ET.Element("ApplicationPackage", SchemaVersion="1.0", AppVersion=version,
                         Name="MCP Toolkit", Description="AutoCAD MCP automatic bridge",
                         ProductCode=PRODUCT, UpgradeCode=PRODUCT, Author="allen2123231")
    components = ET.SubElement(package, "Components")
    ET.SubElement(components, "RuntimeRequirements", OS="Win64", Platform="AutoCAD*", SeriesMin="R24.1")
    # Default load reasons, with PerDocument, are the documented LISP bundle behavior.
    ET.SubElement(components, "ComponentEntry", AppName="McpToolkitBridge", AppDescription="MCP Toolkit bridge",
                  ModuleName="./Contents/mcp_dispatch.lsp", PerDocument="True")
    xml = bundle / "PackageContents.xml"
    temp = xml.with_suffix(".xml.tmp")
    ET.ElementTree(package).write(temp, encoding="utf-8", xml_declaration=True)
    os.replace(temp, xml)
    receipt = {"bundle": str(bundle), "target": str(target), "dispatcher_sha256": sha256(contents / "mcp_dispatch.lsp"),
               "method": "ApplicationPlugins", "per_document": True}
    atomic_json(target / "autocad-plugin.json", receipt)
    return receipt


def remove_bundle(target, appdata=None):
    receipt = Path(target) / "autocad-plugin.json"
    if not receipt.exists():
        return
    bundle = Path(appdata or os.environ["APPDATA"]) / "Autodesk/ApplicationPlugins/McpToolkit.bundle"
    if bundle.exists() and ET.parse(bundle / "PackageContents.xml").getroot().get("ProductCode") == PRODUCT:
        shutil.rmtree(bundle)
