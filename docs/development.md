# 開發與發布

0.3 使用新安裝視窗及常駐程式，舊八步 WPF 精靈不再編入 EXE。CAD 檔案與原有設定保留，安裝交易仍共用生命週期後端。

## 程式結構

- `installer/ToolkitApplication.cs`：單一實例、系統匣、視窗及結束生命週期。
- `InstallWindow.cs`：選擇 MCP、安裝進度、完成／重試。一次 setup 完成外掛與 Plugin 設定。
- `ManagerWindow.cs`、`TrayPanel.cs`：完整管理及小型狀態面板。
- `RuntimeHost.cs`：從封裝資源取得後端、執行有界狀態檢查及安裝後自動啟用。
- `ToolkitVisuals.cs`：插頭標誌、設定齒輪及軟體／文件原生圖示。
- `engine/runtime.py`、`native_status.py`：唯讀狀態與程序隔離，背景檢查不啟動 CAD。
- `engine/rhino_instances.py`：以 PID 及建立時間驗證實例，目標存於 targets.json。
- `engine/relay.py`、`history.py`：透明 stdio 訊息轉送及 SQLite 命令收據，最多 2,000 筆、7 天。
- `engine/inventor_session.py`：包裝固定 Inventor 服務，僅附加現有實例，不以 COM 建立應用程式。
- `engine/autocad_setup.py`：使用者層級 ApplicationPlugins 套件，PerDocument=True。
- `engine/manager.py`：setup／install／diagnose／activate／rollback／uninstall。setup 把成功設定的元件列入 auto_enable_pending，通過橋接檢查後才啟用。
- `sources.json`、`locks/`：固定來源與套件依賴。相容版本使用套件 metadata，不把 SDK 的 serverInfo.version 當套件版本。

## 建置

開發機需要 Windows、Python 3.12+、.NET 8 SDK；使用者不需要開發工具。

```powershell
python -m pip install tomlkit==0.13.3
python scripts/create_content.py
python scripts/build_guides.py
python -m unittest discover -s tests -v
python scripts/build_payload.py
dotnet run --project tests/desktop/DesktopChecks.csproj -c Release -- test-results/desktop
dotnet publish installer/CadToolkitSetup.csproj -c Release -o dist/setup
python scripts/finalize_release.py
```

來源、原生套件及 runtime 沒有改變時可使用 `scripts/repack_payload.py` 更新後端與文件。輸出 `McpToolkitSetup.exe`、`McpToolkit.exe`、`cad-toolkit-payload.zip`、release-manifest.json 及 SHA256SUMS.txt。兩個 EXE 使用相同程式；首次安裝或傳入 `--setup` 會開新安裝視窗，安裝後預設進入管理視窗。`--background` 只開系統匣。

## 驗證

`scripts/smoke_install.py` 以隔離 CODEX_HOME 執行七種真實安裝組合、重複安裝與中斷續作，保留使用者 Codex 設定。不啟用元件或呼叫 CAD。介面測試使用 fixture 狀態，真實 CAD 驗證範圍另記於 validation.md。

公開圖片使用 fixture 文件名稱，不含使用者文件或帳號。原生圖示來源位於 installer/assets/icons/README.md；齒輪授權位於 installer/assets/lucide-LICENSE.txt 並嵌入 EXE。

AutoCAD 套件格式依 [Autodesk Components 參考](https://help.autodesk.com/cloudhelp/2024/ENU/AutoCAD-Customization/files/GUID-3C25E517-8660-4BB7-9447-2310462EF06F.htm)，不降低 SECURELOAD／TRUSTEDPATHS。無法載入時由使用者／管理員處理。
