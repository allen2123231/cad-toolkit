---
name: autocad-drafting
description: 透過 AutoCAD MCP 建立或修改圖面、圖層、物件及標註，並讀回驗證 CAD 實體。
---

# AutoCAD 圖面操作

Toolkit 同時辨識 Windows AutoCAD 與 AutoCAD LT；LT 使用 `acadlt.exe`。依 `get_application_state` 回傳視窗的 product 確認版本，不把 MCP 安裝成功當成軟體已連線。LT 透過每份圖面自動載入的 AutoLISP／file IPC 連線，不能使用外部 COM 附加，也不提供完整 AutoCAD 的 3D 實體、曲面或 .NET 能力。自動偵測找不到非預設安裝位置時，引導使用者在 Toolkit 按「選擇程式」，不要要求輸入路徑或 APPLOAD 指令。完整版與 LT 同時開啟時，先保留唯一目標再執行，不能以檔名或前景視窗猜測。

建模前先以 `get_application_state(wait_seconds=0)` 確認可見主視窗。尚未開啟或只有背景視窗時，呼叫 `open_application`，再用 `get_application_state(wait_seconds=45)` 等待 window_open；starting 時繼續等待，不啟動第二個程序。不要自行使用 shell 或隱藏模式啟動軟體。視窗出現後再檢查 MCP 橋接與目前文件。

先用 `system` status 與 `drawing` info 確認 backend、文件與單位；實機操作需 `file_ipc`。工具參數以目前暴露的 schema 為準。

修改前辨識使用者指定的物件、圖層及範圍；既有圖面做大範圍修改時先建立備份。尺寸從實際幾何取得，不從畫面像素推估。

使用 `entity`、`layer`、`block`、`annotation`、`view` 等工具完成請求。必要時使用 `system` 的 `execute_lisp`；目前封裝使用 `data.code`，先確認 schema，不套用其他版本的 `code_file` 參數。

先讀回物件數量、座標、尺寸、圖層與必要的版面；有出圖要求時檢查比例、遮擋及文字。成功回應不等於圖面正確；交付時說明實際修改與驗證結果。
