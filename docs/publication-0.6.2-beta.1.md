# 0.6.2-beta.1 發布紀錄

2026-11-23 使用者確認本機原視窗恢復可用，授權合併與發布，並明確同意本次以「未簽章 Beta 0.6.2-beta.1」公開。此例外僅適用本版，未放寬 `.github/workflows/release.yml` 的預設簽章門檻，也不宣稱通過 Smart App Control 驗收。

- 分支由 `feature/ai-block-library` 改名為 `fix/autocad-recovery`，本機與 GitHub 均完成；沒有加入圖塊庫功能。
- 修正已合併並推送 `main`。版本標籤 `v0.6.2-beta.1` 指向 `bce91fa`。
- [公開 Beta Release](https://github.com/allen2123231/cad-toolkit/releases/tag/v0.6.2-beta.1) 包含安裝 EXE、同內容的主程式 EXE、payload、發布清單、SHA256SUMS 與簽章盤點，共六個附件。
- 原先暫定的 0.6.1-beta.2 草稿已撤除，沒有公開；改用 0.6.2-beta.1，確保版本順序高於本機 0.6.1-dev.2。
- 169 項 Python、32 項一般桌面、8 項原視窗恢復 UI、10 項既有恢復 UI、28 項更新／清理檢查通過。打包後驗證 3,056 個 manifest 檔案、native guard 與獨立 relay 匯入成功。
- 首輪 Python 檢查因開發機有使用者正在執行的 Rhino 而使兩個安裝 fixture 失敗；僅補足該兩個 fixture 的程序隔離，未關閉使用者 Rhino，未更改產品的開啟中禁止替換規則。完整重跑通過。

## 公開下載與更新驗證

以免登入的公開下載網址重新下載發布清單、安裝程式及 payload，檔案大小與 SHA-256 均符合發布清單；沒有執行下載的安裝程式。

| 檔案 | 位元組 | SHA-256 |
|---|---:|---|
| McpToolkitSetup.exe | 72134692 | `46322b2ca372db2155f8f51a7869a1fa26e6c3ba7dce3bdb6047d1fe2c12a910` |
| cad-toolkit-payload.zip | 138854972 | `58982353613e2ab59ea62e1ada7b5c8ffc5f246280db31035bbd0907fddb8ddf` |

以實際 `ToolkitService.CheckUpdate` 存取公開 GitHub API 與 manifest，僅替換測試客戶端的目前版本 metadata：0.6.1-beta.1 與 0.6.1-dev.2 均偵測到 0.6.2-beta.1；關閉 Beta 接收時不會收到此版。沒有套用更新、修改使用者設定或關閉 CAD。

本機證據：`test-results/062beta1-published.json`、`062beta1-public-downloads.json`、`062beta1-public-feed.json`、`062beta1-package.json`、`062beta1-python-final.txt`（完整通過記錄另為 `062beta1-python.txt`）、`dist/signature-audit.json`。原生及本機恢復測試範圍見 [原視窗恢復驗證](validation-inplace-recovery.md)；LT 2027 尚未完成 LT 實機驗證。

本次沒有覆蓋任何已公開版本的附件，沒有把本機開發安裝自動切換為公開版本。
