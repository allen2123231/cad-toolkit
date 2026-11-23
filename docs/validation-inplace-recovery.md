# AutoCAD 原視窗恢復：本機測試版

2026-11-21；`fix/autocad-recovery`；`0.6.1-dev.2`。僅本機安裝，未合併 main、建立標籤、發布 Release 或修改公開更新通道。需使用者確認後才另行發布。

## 使用方式

在「AutoCAD 中斷恢復」按 **檢查並恢復連線**。檢查通過後會顯示「原視窗已恢復連線，舊指令已隔離」，並啟用「我已檢查目前圖面」選項。使用者檢查圖面、勾選，再按 **確認圖面並解除暫停**。準備恢復不等於解除暫停；解除只允許新的明確操作，不重送舊要求，也不表示上一批成功。

AutoCAD 正在執行或等待輸入時，先由使用者完成／取消目前操作。視窗、圖面不符、存在其他未知收件匣、舊版外掛不支援或原生驗證失敗時，仍禁止原視窗恢復；保留儲存並重開的備援方式。單純「重新檢查」只更新狀態。

## 安全條件與架構

- OS lease 將恢復準備、讀取與修改共用序列化。按鈕帶入確切 recovery request ID 和 target token，不依檔名或前景視窗猜測。
- 新增獨立 `autocad_mcp_recover_*.json` 與 `c:mcp-recover`；不能在恢復入口執行任意繪圖程式。
- 原生外掛要求 guard_protocol 4，重新檢查 HWND、內部文件 ID、CMDACTIVE 與忙碌狀態；同一主執行緒進入恢復入口，才證明先前同步 dispatcher 已離開執行／輸入流程。僅憑被動閒置資訊或結果檔不啟用確認。
- 外掛先持久化 `toolkit-revoked-<old-request-id>.json`，再回覆一次性 probe ID。Python 驗證 probe ID、舊要求 ID、文件 ID、撤銷檔與新鮮 target token 後，才隔離對應 pending 與舊指令檔。
- 原生修改入口在所有繪圖操作之前檢查永久撤銷標記。因此無論舊 sender 是否仍活著、其通知是否遲到，該 request ID 均不得再執行；不必任意終止其他對話的服務程序。
- native revocation 及 Python 準備紀錄都成功才開放勾選。撤銷檔保留在確認後，不以刪除恢復屏障取代原生隔離。其他未知指令檔會使準備或確認失敗。
- 文件切換次數以 native blackboard 計數，加入 target token；切走再切回原文件也會使先前準備失效。Toolkit 重啟仍能讀回原有證據，但缺少撤銷檔不能確認。
- UI 背景執行檢查，有進行中文字並停用重複按鈕；技術錯誤收在展開區，不用完整堆疊擠掉操作按鈕。

這個保護針對 Toolkit 管理的指令與通知，不撤銷指令已經造成的圖面變更，也不封鎖第三方程式或任意 LISP 在 Toolkit 之外建立的後續工作。使用者仍需檢查圖面。

## 安裝與相容性

本機使用明確的開發者 `--live-autocad` 安裝路徑；僅允許相同 MCP 元件、Python／uv 與依賴鎖、唯一且閒置的 AutoCAD、相符圖面與中斷紀錄。Rhino／Inventor 開著時仍拒絕更新。一般公開更新 UI 的關閉 CAD 規則沒有放寬。

原視窗若仍載入 protocol 3，維護程式會在恢復屏障及 lease 都保留的情況下，載入安裝目錄中已驗證 SHA256 的 Toolkit 原生套件。這是固定的安裝維護動作，不接受呼叫者提供程式碼或路徑，不透過任意 COM 繪圖繞過屏障。protocol 2 或無法驗證的套件不採此途徑。protocol 4 的日後恢復不需要再載入套件。

本機安裝備份：`%LOCALAPPDATA%/McpToolkit/backups/update-20261121-221003-275983`。三套上游 MCP 套件版本未變更；已保留啟用政策與其他設定。

## 驗證結果

| 驗證 | 通過 | 證據 |
|---|---:|---|
| Python 全套 | 169 | `test-results/inplace-python-final.txt` |
| AutoCAD 2026 原生整合，WM_CHAR 通知，另開自有測試程序 | 33 | `test-results/inplace-native-01/report.json` |
| 原視窗恢復按鈕與確認 UI | 8 | `test-results/inplace-ui/report.json` |
| 既有重開恢復 UI | 10 | `test-results/inplace-recovery-ui/report.json` |
| 一般桌面 UI | 32 | `test-results/inplace-desktop.log` |
| 更新／清理回歸，模擬網路、不發布 | 28 | `test-results/inplace-updates.log` |

原生測試包括：中途關閉／重開、逾時、遲到完成回覆、準備原視窗恢復但尚不解除、確認後無重播、確認後重新出現的舊 request ID 被原生拒絕、圖元數不變、遲到通知、未完成互動指令與原使用者視窗保留。

單元測試另驗證：忙碌與換圖不發出恢復通知、probe 失敗不清舊檔、偽造 ACK 缺原生撤銷檔不能確認、切走切回失效、過期 target token 不發出通知、其他未知指令檔保留、舊 protocol 不假裝支援、Toolkit 重啟保留證據、撤銷檔遺失使確認失效。

## 真實本機驗收現場

使用者已重開並解除上一個中斷。後續在目前空白、未修改的 `Drawing1.dwg` 中，僅執行短暫延遲並中斷本測試建立的 MCP worker，沒有修改圖元。

安裝及恢復前後均為 **PID 52360、HWND 1775196、相同內部文件 ID**；由已安裝 EXE 解出的 runtime 經 AutoCAD venv 子程序執行與 UI 相同的 `prepare-autocad-recovery` 動作，透過真正 COM 通知完成 protocol 3 → 4 維護載入與原生恢復握手。沒有關閉 AutoCAD，也沒有替使用者確認解除暫停。

讀回驗證：圖元數 0、DBMOD=0、`recovery_mode=in_place`、`can_confirm=true`、修改仍暫停；經已安裝 MCP stdio 的唯讀操作成功，修改要求回覆 RECOVERY_REQUIRED。實際 Windows UI Automation 讀回確認：勾選框已啟用，解除暫停按鈕在使用者尚未勾選時仍停用。

證據：`test-results/inplace-installed-stage.json`、`inplace-installed-ready.json`、`inplace-installed-stdio.json`、`inplace-install.log`。介面截圖為 fixture，不含使用者文件。

本次實機為 AutoCAD 2026。LT 2027 的原生入口與 Win32 通知沒有完成 LT 實機驗證，不視為已認證。公開發布仍等待使用者本機試用確認。
