"""Generate matching portable and compatibility metadata from one definition."""
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
plugin = ROOT / "plugins/cad-toolkit"
version = json.loads((ROOT / "sources.json").read_text())["version"]
interface = {"displayName": "CAD Toolkit", "shortDescription": "AutoCAD、Inventor、Rhino 整合工具與中文工作流程",
    "longDescription": "搭配 Windows 安裝程式管理三套 CAD MCP、獨立執行環境及六套中文 Skills。",
    "developerName": "allen2123231", "category": "Productivity", "capabilities": ["Read", "Write"],
    "websiteURL": "https://github.com/allen2123231/cad-toolkit",
    "defaultPrompt": ["檢查我的 CAD 連線與目前文件", "協助我使用 CAD 工具完成建模"]}
base = {"name": "cad-toolkit", "version": version, "description": interface["shortDescription"],
        "author": {"name": "allen2123231"}, "license": "MIT", "repository": interface["websiteURL"]}
def write(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
write(plugin / "plugin.json", {"$schema": "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json", **base,
                               "extensions": {"com.openai": {"interface": interface}}})
write(plugin / ".codex-plugin/plugin.json", {**base, "interface": interface, "skills": "./skills/", "mcpServers": "./.mcp.json"})
# Source package is skills-only. Installer materializes local executable paths after installation.
write(plugin / "mcp.json", {"$schema": "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json", "mcpServers": {}})
write(plugin / ".mcp.json", {"mcpServers": {}})
