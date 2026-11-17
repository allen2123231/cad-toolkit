# 個人發行者簽章方案確認

查核日期：2026-11-17。需求為台灣個人、可簽商業／閉源程式、不以開源專案審核為前提。尚未購買、開帳戶、送出申請或身分資料。

## 優先評估：SSL.com IV + eSigner

- IV Code Signing 明確允許個人申請，不要求公司登記；可用於一般發行的 Windows 程式。
- 官方可接受國家代碼列有 Taiwan / TW，台灣不在其公開禁發清單。這支持台灣申請途徑，但不等於已通過個案身分驗證；核發仍由 SSL.com 決定。
- 一年期 IV 牌價 US$129。eSigner 雲端簽章另外收費，頁面最低級顯示 US$15／月；以此費率換算，一年合計約 US$309。這是未稅估算，實際帳單週期、額度與首月優惠需在訂單確認。
- eSigner 支援 GitHub Actions 等 CI/CD。預期較容易接進目前的發布流程，不必把私人金鑰放進 GitHub。
- 需要有效政府證件，並可能需要補件及電話驗證；Windows 會顯示驗證過的個人姓名，不能只填 GitHub 暱稱。

來源：[IV 方案與價格](https://www.ssl.com/products/software-integrity/code-signing/iv/)、[eSigner 方案與費用](https://www.ssl.com/products/software-integrity/signing-service/)、[可接受及受限制國家](https://www.ssl.com/country-codes/)、[身分驗證流程](https://www.ssl.com/how-to/validation-process-for-document-signing-code-signing-and-ev-code-signing-certificates/)。

## 比較方案：Certum Standard Code Signing in the Cloud

- Standard 方案支援自然人，與有開源用途限制的 Open Source 方案不同。
- 商店標示 €209 起，含 SimplySign 雲端方案；確切期間及稅額須在訂單確認。頁面列有每月 5,000 次簽章限制。
- 需 SimplySign 手機及桌面程式。是否適合完全自動的 GitHub hosted runner，需要在選定方案後確認；不能只依價格視為可直接取代 eSigner。
- 官方商店列台灣配送，歷史身分文件支援表也列台灣護照；但這兩點不等於目前每種遠端驗證流程都受理台灣個人。購買前仍應取得供應商對台灣個人與目前護照／身分文件的確認。

來源：[Standard 雲端方案](https://shop.certum.eu/standard-code-signing-in-the-cloud.html)、[個人所需文件](https://support.certum.eu/en/code-signing-required-documents/)、[配送地區](https://shop.certum.eu/payment-shipping)。

## 其他方案

- **Cloudflare：**公開憑證服務為 SSL/TLS；沒有找到可供客戶申請的 Windows Authenticode 程式碼簽章服務。網站憑證不能代用。
- **Azure Artifact Signing Public Trust：**官方目前的個人資格限美國及加拿大，不適用台灣個人。Private Trust 不等於任意用戶電腦會信任的公開發行簽章。
- **SignPath Foundation：**免費但要求 OSS 專案審核，也限制第三方程式碼簽署範圍，不符合此處「閉源亦可、不採專案審核」方向。

來源：[Cloudflare SSL/TLS](https://developers.cloudflare.com/ssl/edge-certificates/)、[Azure 公開信任申請資格](https://learn.microsoft.com/en-us/azure/artifact-signing/quickstart)、[SignPath 條件](https://signpath.org/terms)。

## 尚未完成的項目

選定並申請憑證後，仍須整合實際簽章、處理未簽章依賴、重新打包並更新雜湊，最後到開啟 SAC 的另一台 Windows 驗證安裝、更新、CAD 載入與解除安裝。現有 0.5.0-beta.1 尚未因此獲得簽章，不能宣稱已修復 SAC 攔截。SmartScreen 信譽提示與 SAC 是不同機制，也不能保證購買憑證後立即消失。
