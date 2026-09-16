# CAD Toolkit

將 AutoCAD、Inventor、Rhino 的 MCP 與中文 Skills 集中安裝、診斷及更新。

**首版為 Windows x64／Codex 預覽版。** 各項驗證結果請見 [驗收紀錄](docs/validation.md)，尚未通過的項目不視為支援承諾。

## 下載

前往 [GitHub Releases](https://github.com/allen2123231/cad-toolkit/releases)，下載 `CadToolkitSetup.exe`。
安裝程式會下載同一版本的環境套件；也可將該版本的 `cad-toolkit-payload.zip` 放在 EXE 旁供本機安裝。

## 只有第一次需要執行

1. 安裝並啟用自己的 AutoCAD、Inventor 或 Rhino 8，以及 Codex。
2. 開啟 `CadToolkitSetup.exe`，選取需要的軟體，執行「環境檢查」及「安裝所選元件」。
3. 按「CAD 端設定」，依畫面指引載入 AutoCAD LISP、註冊 Rhino 外掛。Inventor 不需要額外外掛。
4. 執行「連線診斷」。多程序或版本不一致時先處理畫面提示。
5. 按「切換 Plugin」。只有通過診斷的所選元件才會切換；相關舊設定先備份，其他設定保留。
6. 在 Codex 開啟新對話，確認 CAD Toolkit Skills 與工具載入。

安裝於 `%LOCALAPPDATA%\CadToolkit`，不更動全域 Python。使用者不用安裝 Git、Python 或 .NET SDK。

## 每次使用

1. 開啟 CAD 及欲操作的文件。
2. Rhino 執行 `mcpstart`；AutoCAD 確認 dispatcher 已載入；Inventor 重新確認連線。
3. 需要時開啟 CAD Toolkit 管理程式執行診斷。
4. 請 Codex 先確認文件路徑、單位及未儲存狀態，再執行建模或出圖。

**Plugin 安裝完成不等於 CAD 已連線。** AutoCAD 必須是 `file_ipc`；Rhino 必須通過外掛能力與文件摘要檢查。

## 更新與還原

使用「檢查新版」及「一鍵更新」。更新來源是 Toolkit 的 Release，採用完整鎖版組合，不直接追蹤各 MCP 最新分支。
預覽版接收預覽與穩定更新；穩定版只接收穩定更新。不在背景自動下載或替換。

先建立新環境，再診斷並切換；失敗保留原設定。Rhino 外掛需自行儲存、關閉軟體並重新註冊，程式不強制關閉 CAD。
「還原上一版」恢復前一組啟用設定。Rhino 涉及不同外掛版本時，先關閉 Rhino 並依舊版本目錄重新註冊。

解除安裝移除 Toolkit 的 Plugin、來源及捷徑，還原由 Toolkit 停用且仍維持停用狀態的舊 MCP。版本檔案與備份保留，確認不再使用後可手動刪除安裝目錄。

## 中文 Skills

- 安裝診斷：`cad-setup-diagnostics`
- AutoCAD 圖面：`autocad-drafting`
- Inventor 建模：`inventor-modeling`
- Inventor 標準件：`inventor-standard-parts`
- Rhino 建模：`rhino-modeling`
- 跨軟體交接：`cad-file-handoff`

Skills 位於 Plugin 內，依安裝元件產生，不另散佈到個人全域 skills 資料夾。
原始碼內 Plugin 是無本機路徑的技能模板；安裝程式才會產生實際 MCP 路徑。

## 專案結構與開發

三套 MCP 保持獨立維護：[AutoCAD](https://github.com/allen2123231/autocad-mcp)、[Inventor](https://github.com/allen2123231/inventor-mcp)、[Rhino](https://github.com/allen2123231/rhinomcp)。

本專案的 `sources.json` 鎖定來源 commit；`locks/` 鎖定 Python 依賴；`engine/` 管理生命週期；`installer/` 提供中文 WPF 介面。

Windows 開發環境需要 Python 3.12+、.NET 8 SDK。建置指令：

```powershell
python scripts/create_content.py
python scripts/build_payload.py
dotnet publish installer/CadToolkitSetup.csproj -c Release -o dist/setup
python scripts/finalize_release.py
python -m unittest discover -s tests -v
```

有意更新依賴時才使用 `python scripts/build_payload.py --refresh-locks`。重新驗證後增加 Toolkit 版本，發布 `v版本號` 標籤。

## 後續開發方向（尚未完成）

1. 補齊乾淨 Windows、Codex 新對話及各 CAD 版本實測矩陣。
2. 更精確的多程序選擇及 CAD 外掛註冊整合。
3. 安裝程式簽章與更完整的解除安裝清理。
4. 支援其他 AI 用戶端，以及獨立的鋁板製造 Skills。

Toolkit 使用 MIT 授權；安裝套件保留各元件與依賴的必要授權內容。
