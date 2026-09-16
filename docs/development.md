# 開發與發布

## 結構

- `content/guides.json`：安裝程式與 GitHub 教學共用文字、真實截圖步驟與練習。
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

`state.json` 沿用 schema 1。UI schema 2 會將舊版第 6、7 步遷移到新增 Plugin 步驟之後。新 UI 狀態另存 `ui-state.json`，不覆寫原本安裝／啟用／備份結構。啟動時核對元件檔案與版本，所有即時連線檢查均重新建立。顯示的就緒結果有檢查時間，5 分鐘後要求重查；切換文件應立即重查。

下載以 CancellationToken 停止並清除本次 `.part`。安裝透過 `--cancel-file` 合作式停止，在安全邊界檢查標記；個別 `*.complete.json` 記錄已完成環境。設定交易發出 `cancellable=false`，介面暫時停用取消。

## 畫面驗證

`CadToolkitSetup.exe --render-preview=絕對路徑.png --page=0 --root=隔離路徑` 可渲染測試介面。頁面為 `0` 到 `7`、`home`、`guides`、`settings`、`updates`、`restore`、`uninstall`、`help`、`complete`；`--size=640x540` 指定邏輯尺寸；`--dpi=144` 或 `192` 測試高密度點陣輸出。這不等同真實 Windows DPI 切換測試。

CAD 教學使用去除個人資訊後的真實截圖；Codex 入門目前以文字和示意補充。公開畫面禁止含個人文件名稱或路徑。新增畫面或狀態時，應重新驗證鍵盤焦點、文字換行與底部主要操作可及性。

## 0.2.0-preview.2 流程分離

GUI 使用 `install --defer-plugin` 準備元件，再於獨立頁呼叫 `configure_plugin`。舊 CLI `install` 預設行為保持相容。`plugin_candidate_path` 記錄已註冊的候選組合；啟用仍重新執行實際診斷。

Inventor 無文件時，只有確認 COM `hwnd`、`version` 與橋接成功才可啟用；模型操作仍需另外建立或選取文件。

圖片位於 `docs/images/guides/` 並嵌入 EXE。`content/guides.json` 同時驅動 WPF 分頁及 GitHub 圖文。原尺寸檢視不放大重繪圖片。
