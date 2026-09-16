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
        if 'pages' in g:
            if 'first_time' in g:
                lines += ['## 只有第一次或更新外掛時', ''] + [f'{i}. {text}' for i, text in enumerate(g['first_time'], 1)] + ['']
            lines += ['## 依序操作', '']
            for i, step in enumerate(g['pages'], 1):
                lines += [f"### {i}. {step['title']}", '', '操作位置：'+step['location'], '', step['text'], '', f"![{step['caption']}](images/guides/{step['image']})", '', step['caption'], '', '完成後：'+step['success'], '']
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
    files['docs/getting-started.md'] = '''# 第一次使用 CAD Toolkit

## 先準備

Windows x64、自己的 AutoCAD／Inventor／Rhino 8 授權、網路及約 3 GB 可用空間。只需要其中一套 CAD。

1. 到 [下載頁](https://github.com/allen2123231/cad-toolkit/releases/tag/v0.2.0-preview.1) 取得 `CadToolkitSetup.exe`。
2. 開啟 EXE。七步精靈會記住進度，下次可繼續。只勾選要使用的軟體。
3. 依 [AI 助手圖解](codex.md) 完成桌面應用程式安裝、登入及 Codex 對話入口。
4. 按「安裝並繼續」，等待下載、驗證與工具安裝。中斷時已完成的元件會保留。
5. 按你使用的軟體閱讀：[AutoCAD](autocad.md)／[Inventor](inventor.md)／[Rhino](rhino.md)。圖解也已內建於 EXE，可離線閱讀。
6. 在「確認可以使用」逐套重新檢查，再按「啟用這套工具」。通過一套就能先使用，其他套可以稍後設定。
7. 在 Codex 新增本機對話，貼上下方唯讀指令。核對 AI 實際讀取的文件與 CAD 分頁名稱相同，再按「我已核對唯讀結果」。

> '''+data['readonly_prompt']+'''

如果 AI 只提供一般操作教學，沒有實際讀取文件，不算成功。回第 6 步檢查連線與啟用狀態。

## 每次使用

1. 開啟 CAD 與要使用的文件。
2. Rhino 在指令列執行 `mcpstart`；AutoCAD 確認已載入 Toolkit 的 dispatcher；Inventor 開啟正確分頁。
3. 在 Toolkit 首頁重新檢查，再到 Codex 新增對話，先執行唯讀指令。
4. 確認文件後才提出建模需求。另建空白文件做練習，不使用工作文件。

歷史成功紀錄不代表目前已連線。切換文件、重啟 CAD 或開多個程序後都要重新確認。

## 更新、還原與解除安裝

首頁「檢查新版」只尋找 Toolkit 已發布的版本。不在背景自動更新。
下載並更新會先建立新環境，再引導你檢查及逐套啟用。失敗保留原有設定。
「設定」內提供還原及解除安裝。Rhino 載入外掛時需自行保存、重新啟動後再切换；不會強制結束 CAD。
解除安裝保留版本與備份，只移除 Toolkit 管理的項目。安裝路徑在設定頁可開啟。

## 沒有網路時

預先下載同一版本的 EXE 和 `cad-toolkit-payload.zip`，放在同一個資料夾再啟動。
教學隨 EXE 提供；CAD 授權與 ChatGPT 登入仍可能需要網路。

## 尚未實測的部分

完整乾淨 Windows、實際 CAD GUI 全流程及真人新手測試尚未完成；詳見 [驗收紀錄](validation.md)。
'''
    version = json.loads((ROOT / 'sources.json').read_text(encoding='utf-8'))['version']
    files['docs/getting-started.md'] = files['docs/getting-started.md'].replace('v0.2.0-preview.1', 'v'+version).replace('七步精靈', '八步精靈').replace('6. 在「確認可以使用」', '6. 在「安裝 Plugin」按安裝，再到「確認可以使用」').replace('回第 6 步', '回「確認可以使用」').replace('Inventor 開啟正確分頁', 'Inventor 可以停留首頁；有文件時確認正確分頁').replace('切换', '切換')
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
