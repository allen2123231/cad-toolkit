# MCP Toolkit 0.5.0-beta.5 — AutoCAD LT 2027 偵測與連線適配

本版為未簽章 Beta 測試版，依維護者本次要求發布到 Beta 自動更新通道；後續版本預設簽章門檻保持不變。Smart App Control／SmartScreen 仍可能阻擋安裝，不宣稱通過 SAC 相容性驗收，也不要求關閉 Windows 保護。

## 修正

- AutoCAD 偵測納入 `acadlt.exe`、AutoCAD LT 2027 安裝資料夾及 32／64 位元 App Paths 登錄。自訂位置可按「選擇程式」記住主程式，不必輸入路徑或指令。
- 啟動、背景程序、視窗列舉、安裝／更新阻擋均辨識 LT，避免 LT 已開啟卻被當成未安裝或再次啟動。
- LT 自動載入套件明確宣告 `ACADLT` 平台，包含根層 RuntimeRequirements 與逐圖面 LISP。套件版本與產品碼隨 Toolkit Beta 版本更新，保留固定升級識別及舊套件移除相容性。
- 每份圖面的原生 LISP 回報目前文件、單位、DBMOD、忙碌狀態與主視窗。LT 診斷不使用外部 COM 附加，狀態檔必須符合視窗身分與程序啟動時間。
- Managed file-IPC 啟動器使用程序與原生主視窗辨識，不依英文 drawing 或 `.dwg` 標題搜尋。視窗改變或有多個候選時停止操作；選定 LT 卻開著完整 AutoCAD 時不自動改連。
- 完整 AutoCAD 使用核對主視窗後的原生 SendCommand 觸發 file-IPC；LT 沿用其 Windows 訊息觸發途徑，不建立外部 COM 物件。
- 狀態卡片與開啟按鈕顯示 AutoCAD LT。Skills 與服務指引區分 LT 的 2D 功能與完整版本的 3D／.NET 能力。

## 更新方式

儲存並關閉 AutoCAD／AutoCAD LT，在 Toolkit 開啟「接收 Beta 測試版更新」，按「檢查更新」更新至本版；完成後正常開啟 LT 與圖面，等待 Toolkit 診斷。安裝位置、其他 MCP 與既有設定保留。沒有偵測到非預設位置時，按「選擇程式」選取 `acadlt.exe`。不需要 APPLOAD、mcpstart 或端口設定。

## 已驗證與限制

119 項 Python 測試（含 19 項 LT 專項）、32 項一般 WPF、3 項 LT 介面、5 項更新介面及 28 項更新／移除檢查通過。LT 專項涵蓋安裝探索、中文／非預設位置、程序漏判、忙碌阻擋、外部 COM 禁用、過期狀態、橋接視窗核對、完整版本混開與逐圖面套件內容。

完整 AutoCAD 2026 在獨立測試圖面與通訊目錄中完成真正 MCP `file_ipc` 狀態與圖面資訊讀回，原工作圖面的路徑、DBMOD 與單位前後一致，測試圖面已關閉。遇到既有未確認指令紀錄時未清除或重送。

**開發機沒有 AutoCAD LT 2027；尚未完成該版本的實機啟動、訊息觸發、載入與建圖驗收。** LT 相關測試為隔離測試，不把完整 AutoCAD 實測當成 LT 實測。請在原問題電腦更新後確認「開啟 AutoCAD LT」與連線結果；LT 不支援完整 AutoCAD 的 3D 實體／曲面與 .NET 外掛能力。

依據：[LT 2027 套件元件](https://help.autodesk.com/cloudhelp/2027/ENU/AutoCAD-LT-Customization/files/GUID-3C25E517-8660-4BB7-9447-2310462EF06F.htm)、[平台與版本需求](https://help.autodesk.com/cloudhelp/2027/ENU/AutoCAD-LT-Customization/files/GUID-1591CA01-EF87-48CD-952B-772FE26037F1.htm)、[AutoLISP 支援限制](https://help.autodesk.com/cloudhelp/2027/ENU/AutoCAD-LT-AutoLISP/files/GUID-037BF4D4-755E-4A5C-8136-80E85CCEDF3E.htm)。
