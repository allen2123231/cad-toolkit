---
name: autocad-drafting
description: 透過 AutoCAD MCP 建立或修改圖面、圖層、物件及標註，並讀回驗證 CAD 實體。
---

# AutoCAD 圖面操作

先用 `system` status 與 `drawing` info 確認 backend、文件與單位；實機操作需 `file_ipc`。工具參數以目前暴露的 schema 為準。

修改前辨識使用者指定的物件、圖層及範圍；既有圖面做大範圍修改時先建立備份。尺寸從實際幾何取得，不從畫面像素推估。

使用 `entity`、`layer`、`block`、`annotation`、`view` 等工具完成請求。必要時使用 `system` 的 `execute_lisp`；目前封裝使用 `data.code`，先確認 schema，不套用其他版本的 `code_file` 參數。

先讀回物件數量、座標、尺寸、圖層與必要的版面；有出圖要求時檢查比例、遮擋及文字。成功回應不等於圖面正確；交付時說明實際修改與驗證結果。
