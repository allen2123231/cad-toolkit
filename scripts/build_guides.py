"""Generate offline GitHub instructions from the installer's shared content."""
import argparse
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def outputs():
    data = json.loads((ROOT / 'content/guides.json').read_text(encoding='utf-8'))
    files = {}
    for key in ('codex', 'autocad', 'rhino', 'inventor'):
        g = data[key]
        image = f'images/{key}-guide.svg'
        labels = ''.join(f'<rect x="24" y="{72+i*82}" width="692" height="62" rx="8" fill="white" stroke="#006967"/><text x="44" y="{109+i*82}" font-size="18">{html.escape(line)}</text>' for i, line in enumerate(g['diagram']))
        files['docs/'+image] = f'<svg xmlns="http://www.w3.org/2000/svg" width="740" height="344" viewBox="0 0 740 344"><rect width="740" height="344" fill="#ecf6f6"/><g font-family="Microsoft JhengHei, sans-serif" fill="#18313d"><text x="24" y="38" font-size="17">操作位置示意・非實際截圖</text>{labels}</g></svg>\n'
        lines = [f"# {g['title']}", '', g['purpose'], '', '## 操作位置', '', g['location'], '', g['version'], '']
        if key == 'rhino':
            lines += ['![MCP Toolkit 新安裝介面實際渲染](images/mcp-install.png)', '']
        if 'pages' in g:
            if 'first_time' in g:
                lines += ['## 只有第一次或更新外掛時', ''] + [f'{i}. {text}' for i, text in enumerate(g['first_time'], 1)] + ['']
            lines += ['## 依序操作', '']
            for i, step in enumerate(g['pages'], 1):
                lines += [f"### {i}. {step['title']}", '', '操作位置：'+step['location'], '', step['text'], '']
                if step.get('image'):
                    lines += [f"![{step['caption']}](images/guides/{step['image']})", '', step['caption'], '']
                lines += ['完成後：'+step['success'], '']
        else:
            lines += [f"![{g['title']}：操作示意]({image})", '', '## 只有第一次需要執行', '']
            lines += [f'{i}. {step}' for i, step in enumerate(g['steps'], 1)]
        if g['command']: lines += ['', '可複製指令：', '', '```text', g['command'], '```']
        lines += ['', '## 完成後會看到', '', g['success'], '', '## 常見問題', ''] + ['- '+v for v in g['problems']]
        if key in data['exercises']:
            e=data['exercises'][key]
            lines += ['', '## 自選練習：'+e['title'], '', e['prepare'], '', '貼到 Codex：', '', '> '+e['prompt'], '', '預期結果：'+e['expect'], '', e['save']]
        if key == 'codex': lines += ['', '[官方下載與入門](https://learn.chatgpt.com/docs/quickstart)']
        lines += ['', '[回第一次使用](getting-started.md)', '']
        files[f'docs/{key}.md'] = '\n'.join(lines)
    files['docs/getting-started.md'] = '# 第一次使用 MCP Toolkit\n\n1. 開啟 `McpToolkitSetup.exe`，勾選 Rhino、AutoCAD 或 Inventor MCP，並確認安裝位置（預設為 AppData/Local/McpToolkit，可直接輸入或瀏覽變更）。\n2. 按「安裝所選 MCP」。程式會準備必要環境、自動連線套件及 Codex 工具設定。\n3. 若安裝時 Rhino／AutoCAD 已開啟，先自行儲存工作並重新開啟一次。Inventor 可以停在首頁。\n4. 點右下角 MCP Toolkit 圖示，等待顯示「可以使用」。工具會在通過連線檢查後自動啟用。\n5. 到 Codex 開啟新對話，以自然語言提出需求。先核對軟體與目前文件，再進行建模。\n\n不需要輸入 `mcpstart`、`APPLOAD`，也不用拖曳 `.rhp`。首次仍需要安裝自己的 CAD 軟體、完成合法授權及 Codex 登入。\n\n## 每次使用\n\n可以正常開啟軟體，或直接在 AI 對話提出需求，由 Toolkit 顯示或啟動軟體。軟體啟動中會等待，不重複開啟。Toolkit 在背景自動檢查；點系統匣圖示查看小面板，按「完整管理」查看所有設定。\n關閉管理視窗會縮到系統匣。要完整結束，右鍵圖示選「結束 MCP Toolkit」。Windows 登入時自動啟動可在設定中開啟。\n\n## 狀態與指令\n\n- Rhino 顯示實際 TCP 端口；AutoCAD 顯示檔案 IPC；Inventor 顯示 COM，後兩者沒有網路端口。\n- Rhino 新對話首次操作時，Toolkit 自動彈出選窗面板；選擇獨立視窗名稱後，這段對話只操作該視窗。切換文件後需先確認，不會自動重播舊指令。\n- 最近指令只記錄 Toolkit 管理的 MCP 新對話，保留最近 7 天，不記錄參數、提示詞或完整輸出。\n- 「符合 Toolkit 相容版本」表示與固定測試組合一致，不代表網路上沒有其他新版。\n\n## 安裝、修復與解除安裝\n\n「MCP 管理」分為「已安裝／未安裝」，可分別安裝或修復各套 MCP，連線設定會一起完成。更新採用 Toolkit 的相容組合，不追蹤各 MCP 最新分支。\nBeta 版啟動時及每天自動檢查新版，從「設定與更新」按「立即更新（保留設定）」即可沿用原安裝位置、MCP 選擇與啟用狀態。可設定通知、稍後提醒及略過版本。0.4.1 及更早版本需先手動安裝本 Beta 一次。\n「設定與更新 → 完整解除安裝 MCP Toolkit」會移除 Toolkit 管理的 MCP、外掛與連線註冊，保留 CAD 本體、工作文件及其他 MCP。設定備份保留於 AppData/Local/McpToolkitBackups。更新或解除安裝前請自行儲存並關閉 CAD。\n\n沒有網路時，把同版本的 EXE 與 `cad-toolkit-payload.zip` 放在同一個資料夾。CAD 授權及帳號登入可能仍需要網路。\n\n實際驗證範圍與限制見 [驗收紀錄](validation.md)。\n'
    return files

if __name__ == '__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--check', action='store_true');args=parser.parse_args()
    for path, text in outputs().items():
        dest=ROOT/path
        if args.check:
            assert dest.exists() and dest.read_text(encoding='utf-8') == text, f'Generated guide differs: {path}'
        else:
            dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(text,encoding='utf-8')
    print('Guides match shared content.' if args.check else 'Guides generated.')
