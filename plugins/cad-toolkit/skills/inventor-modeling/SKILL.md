---
name: inventor-modeling
description: 使用 Inventor MCP 建立或修改零件與組合、草圖及特徵，適用一般參數建模與幾何檢查。
---

# Inventor 建模

先確認已連接的應用程式、文件完整路徑、文件類型、單位及 Dirty 狀態。多個 Inventor 程序且無法確定目標時停止對文件的修改。

先確認目前 MCP 的工具 schema。高階建模工具以毫米為單位；`execute_python` 操作 Inventor COM 時長度通常為公分，毫米需除以 10。

建立草圖與特徵前確認文件類型及目標平面。`ComponentDefinition` 並非所有文件都有；無文件時先依要求建立零件，再存取定義。

複雜修改可用 `transaction` 包成可復原的一組操作；失敗時中止交易並讀回文件，不沿用 RPC 錯誤前的 COM 參照。

完成後檢查特徵健康狀態、幾何與關鍵尺寸，依使用者指定路徑儲存。只在確實完成讀回或重新開啟驗證時，才宣稱已驗證儲存結果。
