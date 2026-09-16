# 預覽版驗收紀錄

此檔記錄已實際執行的驗證，不以程式碼存在代替驗收。

## 建置與自動測試

- 2026-09-16：Windows x64 自包含 WPF EXE 建置成功，已渲染檢查中文介面。
- 自動測試涵蓋七種元件組合的 Plugin／Skills 生成、中文空白路徑、設定保留、損毀下載、失敗切換、回退、多程序判斷、MCP NDJSON 協定，以及初次安裝時三套新 MCP 保持停用。
- 官方 Plugin 檢查器及六套 Skill 檢查器通過。
- 實際離線 wheel 安裝與 MCP 初始化：AutoCAD 8、Inventor 36、Rhino 70 個工具。
- 固定依賴：Python 3.12.11、uv 0.8.17；AutoCAD／Inventor 使用 MCP SDK 1.30.0，Rhino 使用 2.2.0。
- 以隔離的 CODEX_HOME 實際執行 marketplace add、plugin add、plugin list，成功安裝 Plugin；未更動使用者既有 Codex 設定。
- Inventor 2027.1：唯讀 COM 連線、視窗及現有圖面資訊讀取成功，未儲存、關閉或修改文件。
- AutoCAD 2026：現有 dispatcher 未完成相容連線，圖面資訊檢查未通過；前後文件路徑、DBMOD 與指令狀態一致。修正診斷器，將 SDK 包裝的 error 正確視為失敗。
- Rhino 8：偵測到三個執行程序，診斷正確停在「待確認唯一目標」，未發出 CAD 操作。

## 需要實機完成的項目

- 沒有預裝 Python、Git、.NET SDK 的乾淨 Windows。
- Codex 新對話載入 Plugin、所選 MCP 與 Skills。
- AutoCAD 2026：載入 Toolkit dispatcher，唯讀圖面資訊成功。
- Inventor 2027：建模功能與更多文件類型的相容性測試。
- Rhino 8：註冊配套外掛並執行 mcpstart，能力與文件摘要成功。
- 真實新版 Release 的下載、切換與 Rhino 外掛回退。
- 七種組合的完整 GUI 安裝實測（目前已驗證七種設定生成與三套元件一起安裝）。

未列出的 CAD 版本均未驗證。程式可診斷環境，但不保證不同 CAD 版本的所有建模工具相容。
AutoCAD 診斷目前先以 COM 確認指令閒置；不提供 COM 的 LT 版本尚未支援這項完整診斷。
