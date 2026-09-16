---
name: cad-setup-diagnostics
description: 檢查 CAD Toolkit 安裝、AutoCAD／Inventor／Rhino MCP 連線與目前文件，處理安裝及橋接問題。
---

# CAD 安裝與診斷

先區分「已安裝」「MCP 可啟動」「CAD 已開啟」「橋接已連線」。工具沒有出現在對話中，不等於未安裝；檢查 Plugin 是否啟用，必要時在新對話驗證。

只有第一次需要執行安裝精靈、註冊 Rhino 外掛及設定 AutoCAD LISP。每次使用時開啟 CAD；Rhino 執行 `mcpstart`，AutoCAD 確認已載入 `mcp_dispatch.lsp`，Inventor 重新確認 COM 連線。

使用安裝管理程式的唯讀診斷。AutoCAD 必須是 `file_ipc` 並能讀取圖面資訊；離線 `ezdxf` 不能代表實機連線。Python 與 LISP 的 IPC 路徑必須相同。

Rhino 呼叫 `describe_capabilities`、`get_document_summary`，確認外掛與服務版本一致。Inventor 先確認現有程序與文件，注意 `connect` 在沒有現有連線時可能啟動軟體。

診斷不得改動、儲存或關閉文件。回報文件路徑、類型、單位及未儲存狀態；取不到的欄位標示未知。多個視窗時先確認目標，避免猜測。
