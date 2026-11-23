# Rhino 單一系統匣整合：本機測試

2026-11-23，測試分支 `fix/rhino-single-tray`，Toolkit `0.6.3-dev.1`、Toolkit 管理版 RhinoMCP `0.5.4`。僅本機測試，未合併 main、建立版本標籤、公開 Release 或修改自動更新通道；須使用者確認後才發布。

## 行為

- Toolkit 的 Rhino 套件內含不可變 `net8.0/toolkit-integration.json`，明確標記管理模式。不依賴環境變數或 Toolkit 是否正在執行。
- 管理模式的 `StatusTray.Launch(false)` 不啟動任何程式。原生服務、自動載入、InstanceStatusFile、視窗內部識別、文件保護及 TCP 連線均保留。
- 原本的 `mcpwindow` 狀態入口改為開啟 Toolkit 的 MCP 管理頁；管理程式關閉時會開啟，已存在時透過該安裝根目錄專屬事件顯示同一個管理程式，不建立第二個系統匣。找不到管理程式時提供可理解的提示，不嘗試開啟已移除的 Tray。
- 安裝後 locator 位於 `%LOCALAPPDATA%/RhinoMCP/toolkit-manager.json`，支援自訂 Toolkit 根目錄。外掛只組合並啟動該根目錄下的 `McpToolkit.exe`，參數以 ArgumentList 傳遞，不接受任意可執行檔或命令列。
- Toolkit 建置使用 `ToolkitManagedBuild=true`，不建置／封裝 RhinoMCPTray.exe；清除先前建置模式留下的已知 Tray 輸出。未指定管理模式的獨立版仍建置 Tray，不複製管理標記，並移除先前管理建置留下的輸出標記。
- 安裝只在 Rhino 關閉後替換外掛。若舊 Tray 尚未結束，只允許處理既有 RhinoMCP 套件版本目錄內的確切 EXE；從同一個 kernel handle 核對程序映像路徑並結束該 GUI，避免 PID 重用及同名外部程式誤殺。其他 CAD 與文件不受影響。
- 管理套件若仍包含 Tray EXE 或模式標記無效，拒絕安裝。舊版套件依既有交易備份／還原，不直接刪除使用者的其他外掛。

## 驗證

| 測試 | 結果 | 本機證據 |
|---|---:|---|
| Python 全套，含清理範圍、Rhino 開啟時拒絕、管理套件驗證、locator | 175 通過 | `test-results/rhino-tray-python.txt` |
| 實際共用 C# 管理模式／StatusTray 程式，缺少管理程式、自訂路徑與參數 | 8 通過 | `test-results/rhino-tray-policy.txt` |
| 打包後 Rhino Python 的原生視窗／文件守衛 | 4 通過 | `test-results/rhino-tray-server-guards.txt` |
| 桌面介面 | 32 通過 | `test-results/rhino-tray-desktop.txt` |
| 更新與清理回歸 | 28 通過 | `test-results/rhino-tray-updates.txt` |
| 兩個真實 Rhino 8 視窗與已安裝 MCP 路由 | 22 通過 | `test-results/rhino-single-tray-native/report.json` |
| 獨立模式建置 | Tray EXE 存在、管理標記不存在 | `test-results/rhino-tray-standalone.txt` |
| 已安裝 runtime／EXE 與測試來源一致；其他 MCP 路徑保留 | 通過 | `test-results/rhino-tray-installed-consistency.json` |

原生驗收以全新空白視窗進行。第一個由正式 request_window_binding 工具開啟，第二個為明確由測試工具持有的可見程序；選窗使用與 Toolkit 按鈕相同的 Store.bind API，僅選擇已核對 PID／instance ID 的測試視窗。沒有要求使用者輸入 mcpstart 或拖入 RHP。

兩個視窗回報管理模式、原生版本 0.5.4、guard protocol 1，得到不同的 instance ID、HWND 與 binding ID。各自建立一個不同位置的點，兩個文件皆只有一個物件並可從對應綁定讀回。第三個要求不能占用已綁定視窗。只刪除該次建立的 GUID，讀回兩文件為空，再解除測試綁定。

在 Rhino 與已綁定 worker 保持執行時，只停止本安裝的 Toolkit GUI，再經 Rhino 的狀態入口開啟管理程式；重複開啟仍只有一個 Toolkit，原綁定仍可讀取。全程沒有 RhinoMCPTray 程序。另以真實 Windows UI Automation 驗證既有 Toolkit 可透過管理頁事件顯示「MCP 管理」。

測試完成關閉第二個自有空白視窗，保留第一個空白 Rhino 供使用者試用。測試物件已移除，沒有保存測試 3DM，也沒有修改使用者文件。空白測試文件可能仍有未儲存標記／復原紀錄。

## 本機安裝

首次替換前雖偵測 Rhino 已關閉，但準備環境期間 Rhino 又開啟，原生替換因而拒絕並保留原外掛。使用者明確回覆儲存並關閉全部 Rhino 後，完成 Yak 安裝、locator 與正式啟用；沒有強制關閉 Rhino 或替使用者處理未儲存文件。

舊原生套件備份位於 `%LOCALAPPDATA%/McpToolkitBackups/rhino-replace-20261123-100247-1d84ec12`，Toolkit 設定及 EXE 另備份在安裝根目錄的 `backups/rhino-single-tray-*`。舊 Tray 在替換時已自行退出，因此該次 retired_trays 為空；清理範圍另有測試，未誤稱實際強制結束了舊程序。

只替換／啟用 Rhino。AutoCAD 與 Inventor 的 active 路徑與安裝前相同。Codex 現有對話不會熱替換已啟動的 MCP 服務，後續使用請重新開啟 Codex／新對話載入測試 Plugin。

## Beta 公開發布驗證（2026-11-23）

使用者完成本機試用並確認可用後，將 `fix/rhino-single-tray` 合併至 `main`，發布標籤 `v0.6.4-beta.1` 指向合併提交 `28fe8f4f26799f9bd18b5d860b78fbd5c74c724b`。版本刻意高於本機 `0.6.3-dev.1`，避免測試機收不到公開更新。

公開版本：https://github.com/allen2123231/cad-toolkit/releases/tag/v0.6.4-beta.1

本版簽章稽核仍有未簽章／未受信任項目；先完成建置與六個草稿附件，再取得使用者僅針對 `0.6.4-beta.1` 的明確未簽章 Beta 公開例外。既有工作流程簽章門檻未被移除或放寬；版本說明保留 Smart App Control／SmartScreen 可能阻擋的提示。

發布前重跑：175 項 Python、32 項桌面、28 項更新、8 項共用 C# 管理模式及 4 項 Rhino 服務守衛全部通過；3059 個封裝檔案通過 manifest 核對。發布包中的 Rhino 原生外掛與使用者已測試的本機外掛位元組相同，管理標記存在且不含 RhinoMCPTray.exe。證據為 `test-results/064beta1-*.txt`、`test-results/064beta1-package.json`、`test-results/064beta1-rhino-package.json`。

公開後使用匿名下載核對安裝程式及 payload 的大小與 SHA-256：

| 項目 | 位元組 | SHA-256 |
| --- | ---: | --- |
| McpToolkitSetup.exe | 72136128 | `54086dd983a86486ff12938d845cf0a64037e802c335640769ba450db991baef` |
| cad-toolkit-payload.zip | 138827475 | `96610acd56b961c64110f1ddc231b32c47a292624e890a22bc94476bb16da54b` |

使用真正的 ToolkitService.CheckUpdate 連到公開 GitHub，僅替換測試用目前版本資訊：`0.6.2-beta.1`、`0.6.3-dev.1` 在接收 Beta 時都找到 `0.6.4-beta.1`；關閉 Beta 時都不收到此測試版。沒有執行更新安裝或變更使用者設定。證據：`test-results/064beta1-public-feed.json`、`test-results/064beta1-public-downloads.json`、`test-results/064beta1-published.json`。
