---
name: cad-setup-diagnostics
description: 檢查 CAD Toolkit 安裝、AutoCAD／Inventor／Rhino MCP 連線與目前文件，處理安裝及橋接問題。
---

# CAD 安裝與診斷

先區分「已安裝」「MCP 可啟動」「CAD 已開啟」「橋接已連線」。工具沒有出現在對話中，不等於未安裝；檢查 Plugin 是否啟用，必要時在新對話驗證。

在 MCP Toolkit 新介面的「安裝與版本」按安裝／修復，程式會準備原生外掛、Plugin 與待啟用設定。Rhino 文件準備好後自動橋接；AutoCAD 的每份圖面由 ApplicationPlugins 套件載入；Toolkit 管理的 Inventor MCP 會附加到已正常開啟的軟體，使用者不需要輸入連線或啟動指令。初次安裝後若 Rhino／AutoCAD 已開啟，由使用者儲存並重開一次。

使用安裝管理程式的唯讀診斷。AutoCAD 必須是 `file_ipc` 並能讀取圖面資訊；離線 `ezdxf` 不能代表實機連線。Python 與 LISP 的 IPC 路徑必須相同。

Rhino 呼叫 `describe_capabilities`、`get_document_summary`，確認外掛與服務版本一致。Inventor 先確認現有程序與文件。Toolkit 管理的版本只附加既有實例；其他獨立安裝版本的 `connect` 仍可能啟動軟體。授權元件異常時回報阻擋原因，避免重複啟動。

診斷不得改動、儲存或關閉文件。回報文件路徑、類型、單位及未儲存狀態；取不到的欄位標示未知。多個 Rhino 時在 Toolkit 選擇 PID／端口與文件，開啟新的 MCP 對話後才操作。其他軟體遇多程序時先確認唯一目標，避免猜測。
