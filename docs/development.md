# 開發與發布

## 結構

- `content/guides.json`：安裝程式與 GitHub 教學共用文字、示意與練習。
- `scripts/build_guides.py`：產生文件與 SVG；`--check` 確認沒有內容漂移。
- `installer/SetupWindow.cs`：視窗導覽與長作業狀態。
- `installer/WizardPages.cs`、`Dashboard.cs`：首次設定、教學與日常卡片。
- `installer/ExperienceState.cs`：UI 進度、安裝狀態讀取與環境偵測。
- `installer/ToolkitService.cs`：下載、驗證、後端事件與更新。
- `engine/manager.py`：原有 CLI 安裝／診斷／啟用／還原／解除安裝介面。
- `engine/experience.py`：穩定診斷代碼、結果與可執行提示。
- `sources.json`、`locks/`：來源 commit 與依賴完整鎖版。

三套 MCP 工具名稱與參數未改動：[AutoCAD](https://github.com/allen2123231/autocad-mcp)、[Inventor](https://github.com/allen2123231/inventor-mcp)、[Rhino](https://github.com/allen2123231/rhinomcp)。

## 建置

開發機需要 Windows、Python 3.12+ 與 .NET 8 SDK；使用者不需要。

```powershell
python -m pip install tomlkit==0.13.3
python scripts/create_content.py
python scripts/build_guides.py
python -m unittest discover -s tests -v
python scripts/build_payload.py
dotnet publish installer/CadToolkitSetup.csproj -c Release -o dist/setup
python scripts/finalize_release.py
```

僅當刻意更新依賴時使用 `build_payload.py --refresh-locks`。相同來源 commit 與 runtime 可使用 `repack_payload.py` 更新應用內容；此腳本會拒絕來源／runtime 改動。

GitHub Actions 會驗證內容一致性、執行測試、建置獨立環境與 Rhino 外掛、產生自包含 EXE 與 SHA-256。`v*` 標籤發布同版本 Release。

## 事件與狀態

標準輸出為逐行 JSON：`schema`、`step`、`component`、`outcome`、`progress`、`error_code`、`next_action`、`message`。診斷保留原有 `result`，另加 `code`、`ready`、`enabled`、`checked_at`。

`outcome=needs_action` 不是成功。CLI `diagnose` 正常完成讀取時仍可能回傳 0；呼叫端必須看元件的 `ready`／`code`，不能只看程序結束碼。

`state.json` 沿用 schema 1。新 UI 狀態另存 `ui-state.json`，不覆寫原本安裝／啟用／備份結構。啟動時核對元件檔案與版本，所有即時連線檢查均重新建立。顯示的就緒結果有檢查時間，5 分鐘後要求重查；切換文件應立即重查。

下載以 CancellationToken 停止並清除本次 `.part`。安裝透過 `--cancel-file` 合作式停止，在安全邊界檢查標記；個別 `*.complete.json` 記錄已完成環境。設定交易發出 `cancellable=false`，介面暫時停用取消。

## 畫面驗證

`CadToolkitSetup.exe --render-preview=絕對路徑.png --page=0 --root=隔離路徑` 可渲染測試介面。頁面為 `0` 到 `6`、`home`、`guides`、`settings`；`--size=640x540` 指定邏輯尺寸；`--dpi=144` 或 `192` 測試高密度點陣輸出。這不等同真實 Windows DPI 切換測試。

教學圖皆明確標記為示意。公開畫面禁止含個人文件名稱或路徑。新增畫面或狀態時，應重新驗證鍵盤焦點、文字換行與底部主要操作可及性。
