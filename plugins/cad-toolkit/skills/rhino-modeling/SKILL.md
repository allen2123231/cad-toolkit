---
name: rhino-modeling
description: 使用 Rhino MCP 建立、編輯與檢查曲線、曲面、Brep 和圖層，並確認 Rhino 文件及物件身分。
---

# Rhino 建模

第一次使用這段對話時，呼叫一次 `request_window_binding`（會自動開啟或顯示 Rhino，不需要另開軟體），告知使用者到 Toolkit 的選窗面板選擇視窗。保存 `request_id`，呼叫 `get_window_binding(request_id, wait_seconds=45)` 等待選擇，選定後即可自動繼續。仍為 pending 時用同一要求繼續有界等待，不重複建立要求或密集輪詢。取得 `binding_id` 後，每個 Rhino 操作都帶上這個識別。

不要自行以 shell 或隱藏模式啟動 Rhino。軟體啟動中時保留原 request_id 等待，不能重開第二個程序。

接著呼叫 `describe_capabilities` 與 `get_document_summary`，確認連線、版本、文件、單位與公差。視窗名稱與檔名分開；不得依檔名、端口或另一段對話的識別切換目標。

文件切換遭阻擋時，請使用者在 Toolkit 確認目前文件，確認後再重新送出操作；不自動重播先前的修改。重新辨識物件，不沿用之前的 GUID 或幾何判斷。視窗關閉或綁定失效時重新要求選窗。只有使用者要求結束或轉交時才解除綁定。

依工作主題使用 `get_modeling_guidance` 讀取 transforms、planar_regions、organization、verification 或 recovery 指引。此指引本身不能證明 Rhino 已連線。

修改前確認使用者指定的 GUID、名稱、圖層與選取範圍。建立或刪除幾何時只影響要求的物件；大量修改先備份文件或受影響物件。

幾何完成後檢查 validity、連通性及 solid 狀態。開放 Brep 不視為封閉實體；布林失敗時先檢查相交、公差與方向，避免重複盲目執行。

以實際讀回與必要的視圖驗證完成狀態；未儲存狀態取不到時明確標示未知。
