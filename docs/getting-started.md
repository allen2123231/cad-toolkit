# 第一次使用 MCP Toolkit

1. 開啟 `McpToolkitSetup.exe`，勾選 Rhino、AutoCAD 或 Inventor MCP，並確認安裝位置（預設為 AppData/Local/McpToolkit，可直接輸入或瀏覽變更）。
2. 按「安裝所選 MCP」。程式會準備必要環境、自動連線套件及 Codex 工具設定。
3. 若安裝時 Rhino／AutoCAD 已開啟，先自行儲存工作並重新開啟一次。Inventor 可以停在首頁。
4. 點右下角 MCP Toolkit 圖示，等待顯示「可以使用」。工具會在通過連線檢查後自動啟用。
5. 到 Codex 開啟新對話，以自然語言提出需求。先核對軟體與目前文件，再進行建模。

不需要輸入 `mcpstart`、`APPLOAD`，也不用拖曳 `.rhp`。首次仍需要安裝自己的 CAD 軟體、完成合法授權及 Codex 登入。

## 每次使用

可以正常開啟軟體，或直接在 AI 對話提出需求，由 Toolkit 顯示或啟動軟體。軟體啟動中會等待，不重複開啟。Toolkit 在背景自動檢查；點系統匣圖示查看小面板，按「完整管理」查看所有設定。
關閉管理視窗會縮到系統匣。要完整結束，右鍵圖示選「結束 MCP Toolkit」。Windows 登入時自動啟動可在設定中開啟。

## 狀態與指令

- Rhino 顯示實際 TCP 端口；AutoCAD 顯示檔案 IPC；Inventor 顯示 COM，後兩者沒有網路端口。
- Rhino 新對話首次操作時，Toolkit 自動彈出選窗面板；選擇獨立視窗名稱後，這段對話只操作該視窗。切換文件後需先確認，不會自動重播舊指令。
- 最近指令只記錄 Toolkit 管理的 MCP 新對話，保留最近 7 天，不記錄參數、提示詞或完整輸出。
- 「符合 Toolkit 相容版本」表示與固定測試組合一致，不代表網路上沒有其他新版。

## 安裝、修復與解除安裝

「MCP 管理」分為「已安裝／未安裝」，可分別安裝或修復各套 MCP，連線設定會一起完成。更新採用 Toolkit 的相容組合，不追蹤各 MCP 最新分支。
Beta 版啟動時及每天自動檢查新版，從「設定與更新」按「立即更新（保留設定）」即可沿用原安裝位置、MCP 選擇與啟用狀態。可設定通知、稍後提醒及略過版本。0.4.1 及更早版本需先手動安裝本 Beta 一次。
「設定與更新 → 完整解除安裝 MCP Toolkit」會移除 Toolkit 管理的 MCP、外掛與連線註冊，保留 CAD 本體、工作文件及其他 MCP。設定備份保留於 AppData/Local/McpToolkitBackups。更新或解除安裝前請自行儲存並關閉 CAD。

沒有網路時，把同版本的 EXE 與 `cad-toolkit-payload.zip` 放在同一個資料夾。CAD 授權及帳號登入可能仍需要網路。

實際驗證範圍與限制見 [驗收紀錄](validation.md)。
