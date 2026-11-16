# CAD Toolkit 0.2.0-preview.3

這版更新安裝包與完整安裝說明，納入 AutoCAD MCP 3.2.0 及 RhinoMCP 0.5.2 自動連線版。

## 使用流程

1. 下載並開啟 `CadToolkitSetup.exe`，選擇要使用的 CAD。
2. 準備 Codex 與固定版本連線工具；可只安裝其中一套 CAD。
3. 在「設定 CAD」的 Rhino 頁按「安裝 Rhino 自動連線外掛」。程式會呼叫已安裝 Rhino 8 的套件管理工具，不需要拖曳 `.rhp`。
4. 若 Rhino 已開啟，先自行儲存並重開；文件準備好後會自動啟動橋接，日常不需輸入 `mcpstart` 或設定啟動命令。
5. AutoCAD 先直接檢查連線，新版會嘗試自動載入派送器；載入受阻或舊版仍在回應時，才使用 APPLOAD 備用圖解。Inventor 可以停留首頁確認應用程式連線。
6. 安裝整合 Plugin，逐套檢查並啟用，再到 Codex 建立對話完成唯讀核對。

## 更新內容

- AutoCAD 固定來源為 `8fdd2a2`，包含中文圖層 JSON 回覆修正。
- Rhino 固定來源為 `6ad258e`，Python 與原生外掛皆為 0.5.2。
- Rhino 原生安裝包使用固定 GitHub Release 產物，下載與安裝前核對 SHA-256，保留完整相依檔案。
- 內建教學、GitHub 文件、日常狀態提示與診斷指引同步改為自動連線流程。
- 建置快取依來源 commit 分開，完整 payload 每次重新建立，避免新舊版本檔案混用。
- 安裝外掛不會啟用新的 Codex MCP，也不會關閉、儲存或修改 CAD 文件；連線仍須診斷通過後才逐套切換。

## 限制

仍為 Windows x64 預覽版。Rhino 正在使用舊外掛時須自行儲存並重開；多個 CAD 程序時仍要求確認唯一目標。完整乾淨 Windows、所有 CAD GUI 步驟與真人新手測試尚未全部完成，依[驗收紀錄](https://github.com/allen2123231/cad-toolkit/blob/main/docs/validation.md)判讀。

Toolkit 的「還原」只處理管理的環境與設定。較早版本的 Rhino 外掛仍須依該版本指引重新安裝／註冊，不能將 Python 環境還原當作已切換 Rhino 中載入的外掛。
