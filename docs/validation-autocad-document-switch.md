# AutoCAD 跨圖面中斷恢復（本機測試版）

分支：`fix/autocad-recovery-document-switch`。本機版本：`0.6.5-dev.1`。

## 問題與修正

舊流程要求作用中圖面的內部識別與中斷紀錄相同。使用者切到另一個分頁後，按「檢查並恢復連線」會在傳送維護要求前回傳 `RECOVERY_TARGET_CHANGED`；切回原圖後可恢復。

同一程序與主視窗現在可從另一份作用中圖面執行恢復。外掛先檢查所有開啟文件的 CMDACTIVE；只有作用中文件可忽略本次維護 LISP 自己的 bit 32。其他文件有指令、懸置的 LISP 或無法查證狀態時，保留中斷保護與原始郵件。

查詢非作用中文件會產生 AutoCAD 內部文件切換事件。維護回覆必須帶檢查開始與結束的切換序號；服務核對開始序號、程序身分、文件內部識別、結束序號與原生撤銷憑證，再將確認綁定到新的目標指紋。檢查後再切圖（包括切走再切回）會使確認失效。

恢復檢查只隔離並撤銷舊要求，不重送、補執行或解除修改保護。使用者仍須檢查中斷時及目前圖面並明確確認。新修改要求不排隊；確認後要重新提出。舊外掛未提供跨文件證明時拒絕跨圖面放行，提示切回原圖或更新。

介面同時顯示中斷時圖面、目前圖面、位置與跨圖面檢查說明；恢復錯誤留在面板內，不因週期性狀態刷新消失。

## 驗證（2026-11-23）

- Python：`python -X utf8 -m unittest discover -s tests`，182 項通過。
- WPF：`DesktopChecks.exe test-results/recovery-document-switch-ui --repro-autocad-inplace`，12 項通過；包含兩份圖面提示、使用者確認、切圖失效、錯誤持續顯示。
- 真實 AutoCAD 2026：`tests/native_autocad_recovery.py`，37 項通過。測試僅啟動與終止其擁有的獨立程序，保留使用者既有視窗。
- 原生案例包含兩份真正文件的內部識別、跨圖面恢復且不重送、錯誤目標拒絕、通道占用、部分修改後程序終止、重開圖面、遲到回覆、唯讀不解除修改保護、撤銷後遲到通知、等待輸入。
- 單元案例另驗證非作用中文件忙碌、缺少原生證明、舊外掛、檢查後切圖、舊目標指紋與其他待處理郵件均不能放行。

證據：`test-results/native-document-switch-final-20261123/report.json`、同目錄 `cross-document-probe.json`、`test-results/recovery-document-switch-ui/`、`test-results/document-switch-python-tests-final.log`。

範圍限制：原生測試使用完整 AutoCAD 2026；沒有以此宣稱通過 AutoCAD LT 2027 實機驗收。尚未公開發布。

## 本機安裝驗證（2026-11-23）

使用者儲存並關閉 AutoCAD 後，以正式更新流程安裝 `0.6.5-dev.1`。已核對執行檔雜湊、ApplicationPlugins 外掛雜湊、三套元件的啟用路徑、上一版還原資訊與更新偏好設定。安裝前備份位於 `%LOCALAPPDATA%/McpToolkit/backups/update-20261123-193920-814246`。

使用新安裝 Plugin 的 MCP stdio 入口呼叫 `open_application`，AutoCAD 2026 自動載入外掛後回報 `backend=file_ipc`、`ready=true`、`code=READY`、`recovery=null`。唯讀讀回新開的 `Drawing1.dwg`：0 個圖元、圖層 0、DBMOD 0。沒有打載入指令、開啟或修改工作圖面。主視窗出現早於外掛完成載入，因此驗證會等待橋接 ready，而非僅以視窗存在判定成功。

已安裝驗證證據：`test-results/local-document-switch-verification.json`、`test-results/local-document-switch-install.log`。本機安裝及連線驗證完成；跨圖面恢復的使用者操作驗收仍待確認。分支未合併、未公開到自動更新。
