---
name: rhino-modeling
description: 使用 Rhino MCP 建立、編輯與檢查曲線、曲面、Brep 和圖層，並確認 Rhino 文件及物件身分。
---

# Rhino 建模

先呼叫 `describe_capabilities` 與 `get_document_summary`，確認連線、版本、文件、單位與公差。切換檔案後重新辨識物件，不沿用之前的 GUID 或幾何判斷。

依工作主題使用 `get_modeling_guidance` 讀取 transforms、planar_regions、organization、verification 或 recovery 指引。此指引本身不能證明 Rhino 已連線。

修改前確認使用者指定的 GUID、名稱、圖層與選取範圍。建立或刪除幾何時只影響要求的物件；大量修改先備份文件或受影響物件。

幾何完成後檢查 validity、連通性及 solid 狀態。開放 Brep 不視為封閉實體；布林失敗時先檢查相交、公差與方向，避免重複盲目執行。

以實際讀回與必要的視圖驗證完成狀態；未儲存狀態取不到時明確標示未知。
