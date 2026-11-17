# 視窗與連線介面

`window_scan` 只列出 CAD 主框架，排除文件 MDI 子視窗、對話框、DDE、繪圖管理及浮動輔助視窗。OS 程序啟動時間、HWND 與 Rhino 原生 instance UUID 組成身分；標題、文件和端口不參與身分計算。名稱與綁定保存於 Toolkit 根目錄的 `windows.sqlite3`，舊 `targets.json` 不再讀取。

## MCP

- `request_window_binding(label?)`：建立五分鐘有效的選窗要求，啟動已安裝 Toolkit 的背景程式，回傳 request_id、連線名稱及配對辨識碼。
- `get_window_binding(request_id, wait_seconds=30)`：最多等待 45 秒，回傳 pending／bound／cancelled／expired／disconnected。bound 包含 binding_id。等待既有要求，不建立重複要求。
- `release_window_binding(binding_id)`：取得該視窗的跨程序鎖後撤銷，不關閉 CAD 文件。
- 原有 Rhino 操作工具增加必要字串 `binding_id`；五個本機建模指引／RhinoScript 文件工具除外。資源介面僅轉送原有靜態文件資源。

路由不推定 MCP 程序或連線等於 Codex 對話，也不讀取對話標題。每個 binding 有獨立的 Rhino 子服務、TCP 端口設定及 guard 檔案；同一 binding 的多個 MCP 程序共用同一視窗 OS 檔案鎖。請求及回應保留原 MCP 工具內容，包括影像。

## 執行邊界

原生 Rhino 主執行緒在派送前核對 instance UUID、HWND；修改操作另外核對 document serial 與單調增加的 document epoch。切出去再切回也需要確認，改名／另存不影響文件身分。能力握手失敗或缺少保護協定時，不得繼續送出修改。

確認與轉交都取得同一視窗鎖，再重新驗證資料；轉交的占用檢查、舊綁定撤銷及新綁定建立在同一 SQLite 交易中。確認只更新文件身分，沒有延後執行的指令佇列。逾時或傳輸結果未知以 busy=-1 隔離該視窗，解除連線不清除隔離；新視窗身分才可再次綁定。

唯一擁有者規則適用於同一 Toolkit 安裝根目錄的管理連線，不阻止其他獨立 Rhino 外掛或手動操作 Rhino。最近指令資料表採可追加欄位的遷移，保留原資料與七天保留政策。

## 開發驗證

標準 Toolkit 測試使用 `python -m unittest discover -s tests -v`。建置 payload 後，用其中的 Rhino wheels 建立隔離環境，執行 `python -m unittest discover -s tests -p rhino_server_guard_checks.py -v`。原生畫面使用 `tests/desktop`，產出 96／144／192 DPI PNG。

Rhino 自訂來源由 `scripts/sync_rhino_patch.py <checkout>` 擷取允許修改的檔案，核對 checkout HEAD 與固定來源一致後更新補丁雜湊。補丁變更必須重新執行 `build_payload.py`；`repack_payload.py` 拒絕補丁與既有原生建置不同的組合。
