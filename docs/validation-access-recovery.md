# AutoCAD 唯讀與中斷恢復：本機測試版

2026-11-21，分支 `feature/ai-block-library`，版本 `0.6.1-dev.1`。僅安裝開發者本機，未合併 main、未建立 Release 或標籤，未修改公開自動更新通道。需使用者確認後才另行發布。

## 修正內容

- MCP 的已審核唯讀操作使用獨立 `autocad_mcp_read_*.json` 與原生 `c:mcp-read`。仍通過同一 Toolkit 入口、OS 通道鎖、程序與文件身分檢查；不使用外部 COM 直接盤點幾何。
- 原生外掛再次核對白名單。僅 ping、圖面資訊／變數、實體數量／清單／資料、圖層清單、圖塊清單／屬性可進入唯讀入口。另存、刪除、任意 LISP、縮放等均不視為唯讀；不採信呼叫者的 readOnlyHint。
- 唯讀入口不執行修改收件匣、不改繪圖系統變數。修改結果不明時仍可查圖，但查詢失敗不建立修改恢復屏障；查詢成功也不解除原有修改屏障。CAD 忙碌時查詢仍會被拒絕。
- 遲到的查詢通知只呼叫唯讀入口，不能落入舊修改。死亡讀取端留下的查詢檔會在下一個持鎖讀取前歸檔。
- 僅可證明在通知前失敗的情況回傳 NotSent：視窗身分不符、附加失敗、COM 預檢忙碌等。歸檔未送出的要求，不要求重開 CAD，也不自動重送。
- 全版 AutoCAD 的 COM 預檢最多等待三秒，只重試被拒絕的唯讀預檢；SendCommand 永不重試。LT 仍使用 Win32 通知，不使用外部 COM；任何已嘗試傳送字元的失敗仍屬結果不明。
- 呼叫 SendCommand 後的錯誤、修改逾時、CAD 關閉、未完成互動指令仍需中斷確認；新修改不排隊，重開且確認圖面後才接受明確的新要求。
- 紀錄保留錯誤類型、有限長度的原始錯誤與階段，不將完整操作參數加入命令歷史。舊版可證明為唯讀的 drawing-info 中斷可歸檔，絕不重播；未知修改不適用。
- 原生唯讀通道要求 guard_protocol 3，舊版必須修復／重開，不能靜默改用外部 COM。修改請求保留原有協定與原生身分檢查。
- 恢復介面分開顯示「唯讀查詢可用／尚未就緒」及「修改已暫停」。服務指引禁止 AI 以外部 COM、shell、原始收件匣或任意 LISP 繞過恢復流程。Toolkit 只管理自身通道，不能封鎖第三方程式直接操作 CAD。

## 驗證

| 驗證 | 最終結果 | 證據 |
|---|---:|---|
| Python 全套（包含通知前失敗、只重試預檢、SendCommand 單次呼叫、唯讀／修改分類、獨立收件匣、服務路由） | 159 通過 | `test-results/access-all-python-verified.txt` |
| Windows 桌面一般檢查 | 32 通過 | `test-results/access-desktop.log` |
| 中斷恢復介面、唯讀與修改狀態、原始錯誤、換圖重設確認 | 10 通過 | `test-results/access-ui-final/report.json` |
| 更新與清理回歸檢查（模擬網路，不發布） | 28 通過 | `test-results/access-updates.log` |
| AutoCAD 2026 原生整合，正式 COM 通知實作 | 30 通過 | `test-results/access-native-com-04/report.json` |
| 安裝到實際本機後，從 Plugin 的 NDJSON stdio 啟動 CAD、查圖、建立一次、存檔、讀回 | 9 通過 | `test-results/access-installed/report.json` |
| 實際本機恢復屏障下查圖、阻擋修改、新程序確認、確認後無重播 | 通過 | `test-results/access-installed-recovery.json` |

原生測試在新建、明確擁有的 CAD 程序與測試 DWG 進行，包含：執行中儲存部分結果後關閉程序；下一批被阻擋；重開檢查路徑與單位後確認；遲到回覆不自動解除；修改結果不明時仍可查圖；偽裝成查詢的修改被原生拒絕；遲到通知不補執行；指令停在互動提示不自動 ESC。原生測試工具的確認僅用於它自己建立並驗證的圖面。

正式 COM 實測曾重現呼叫被拒絕（RPC_E_CALL_REJECTED）與啟動期間 HWND 屬性暫不可讀。這些發生於通知前，舊實作會升級為修改結果不明。原先那一筆 drawing-info 未保存原始例外，無法回溯證明它與此次重現完全同因。

最初 WM_CHAR 測試的「原使用者 CAD 視窗仍存在」檢查，在使用者依提示自行關閉視窗後失敗，未列為最終通過證據。後續無其他使用者 CAD 程序的完整 COM 測試全部通過。全套 Python 曾於並行建置負載下出現既有 Rhino 測試的 SQLite 清理／時序失敗，最終重跑 159 項全數通過，未修改 Rhino 路由。

本機安裝後曾因測試程式將 drawing.save 的 path 放在錯誤層級而觸發 QSAVE 互動提示；修改屏障有正確啟動。修正測試呼叫為 data.path，僅對該次新建測試程序重開、核對空圖面並透過同一確認 API 恢復；後續完整測試通過，沒有補送舊要求。

## 本機安裝與限制

已透過正常 Manager.update 路徑安裝全部既有三個 MCP，保留設定與啟用政策；備份位於 `%LOCALAPPDATA%/McpToolkit/backups/update-20261121-214756-148767`。AutoCAD、Inventor 與 Rhino 的上游套件版本沒有變更，新增內容為 Toolkit 服務、AutoCAD 原生橋接及介面。本機 EXE 版本、candidate 與 active 路徑均為 dev 測試版本。

測試結束保留已儲存的 `test-results/access-installed/installed-access-test.dwg`（一個測試圓），DBMOD=0；沒有修改 GM_Template_01.dwg。Codex 需重新啟動或開啟新對話，讓既有 MCP 程序重新載入新版 Plugin。

本次真實 CAD 為 AutoCAD 2026。AutoCAD LT 2027 的白名單、非 COM 通知與守衛有程式層級覆蓋，尚未在 LT 2027 實機重跑，不視為已認證。禁止在未確認圖面的情況下替使用者解除未知修改的恢復屏障。
