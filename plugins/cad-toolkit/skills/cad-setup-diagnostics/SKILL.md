---
name: cad-setup-diagnostics
description: 檢查 CAD Toolkit 安裝、AutoCAD／Inventor／Rhino MCP 連線與目前文件，處理安裝及橋接問題。
---

# CAD 安裝與診斷

檢查是否可操作時，先用 `get_application_state(wait_seconds=0)` 確認可見主視窗；背景程序或舊橋接回應不代表可以使用。若使用者要求建模或開啟軟體，呼叫該軟體的 `open_application`，再用 `get_application_state(wait_seconds=45)` 等待 window_open；starting 時繼續有界等待，不要再啟動第二個程序。純診斷時不自動開啟軟體。不要自行以 shell 或隱藏視窗方式啟動 CAD。

先區分「已安裝」「MCP 可啟動」「CAD 已開啟」「橋接已連線」。工具沒有出現在對話中，不等於未安裝；檢查 Plugin 是否啟用，必要時在新對話驗證。

在 MCP Toolkit 新介面的「安裝與版本」按安裝／修復，程式會準備原生外掛、Plugin 與待啟用設定。Rhino 文件準備好後自動橋接；AutoCAD 的每份圖面由 ApplicationPlugins 套件載入；Toolkit 管理的 Inventor MCP 會附加到已正常開啟的軟體，使用者不需要輸入連線或啟動指令。初次安裝後若 Rhino／AutoCAD 已開啟，由使用者儲存並重開一次。

使用安裝管理程式的唯讀診斷。AutoCAD 必須是 `file_ipc` 並能讀取圖面資訊；離線 `ezdxf` 不能代表實機連線。Python 與 LISP 的 IPC 路徑必須相同。

Rhino 若尚未綁定，先呼叫一次 `request_window_binding`，讓使用者在 Toolkit 彈出面板選窗；使用 `get_window_binding(request_id)` 取得這段對話的 `binding_id`。接著帶著該識別呼叫 `describe_capabilities`、`get_document_summary`，確認外掛與服務版本一致。等待選擇時不要重複要求或密集輪詢。

Inventor 先確認現有程序與文件。Toolkit 管理的版本只附加既有實例；其他獨立安裝版本的 `connect` 仍可能啟動軟體。授權元件異常時回報阻擋原因，避免重複啟動。

診斷不得改動、儲存或關閉文件。回報文件路徑、類型、單位及未儲存狀態；取不到的欄位標示未知。Rhino 依獨立視窗名稱選擇，不以檔案、PID 或端口命名。文件切換時由使用者在 Toolkit 確認後才繼續修改。AutoCAD、Inventor 此階段的多視窗清單僅提供命名與定位，尚未支援多視窗對話路由；不能聲稱選取清單已切換 MCP 目標。
