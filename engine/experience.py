"""Stable, additive events and diagnostic outcomes for GUI and CLI consumers."""
import datetime as dt

class Cancelled(RuntimeError):
    pass

def outcome(component, status, enabled=False):
    code = 'BRIDGE_NOT_CONNECTED'
    action = {'autocad': '切換到 AutoCAD，依圖解用 APPLOAD 載入指定檔案，再重新檢查。',
              'rhino': '切換到 Rhino，在指令列輸入 mcpstart，再重新檢查。',
              'inventor': '切換到 Inventor，開啟要使用的文件，再重新檢查。'}[component]
    if not status.get('installed'):
        code, action = 'NOT_INSTALLED', '回到「安裝連線工具」，安裝這套軟體的元件。'
    elif not status.get('cad'):
        code, action = 'CAD_NOT_RUNNING', '先開啟這套 CAD 與一份文件，再按「重新檢查」。'
    elif len(status.get('processes', [])) > 1:
        code, action = 'MULTIPLE_PROCESSES', '找到要使用的視窗。自行保存其他視窗後關閉多餘程序，再重新檢查；Toolkit 不會替你關閉。'
    elif not status.get('mcp'):
        code, action = 'MCP_START_FAILED', '回到「安裝連線工具」重試修復；若仍失敗，展開詳細資料。'
    elif status.get('document_missing'):
        code, action = 'NO_DOCUMENT', '請先在 CAD 開啟或新增一份文件，再重新檢查。'
    elif not status.get('bridge') and '版本' in status.get('message', ''):
        code, action = 'VERSION_MISMATCH', '依圖解重新註冊此版本外掛。若 Rhino 已載入舊外掛，請自行保存並重新啟動後再檢查。'
    elif status.get('bridge'):
        document = status.get('document')
        if component == 'inventor' and isinstance(document, dict): document = document.get('document')
        if not document:
            code, action = 'NO_DOCUMENT', '連線已建立。請在 CAD 開啟或新增一份文件，再重新檢查。'
        else:
            code, action = ('READY', '到 Codex 新增對話，貼上唯讀檢查指令。') if enabled else ('NOT_ENABLED', '連線已通過。按「啟用這套工具」，再到 Codex 新增對話。')
    return {**status, 'code': code, 'next_action': action, 'enabled': enabled,
            'ready': code == 'READY', 'checked_at': dt.datetime.now(dt.timezone.utc).isoformat()}

def friendly_error(error):
    message = str(error)
    if isinstance(error, Cancelled): return 'CANCELLED', '已在安全步驟停止。下次安裝會接續已完成的元件。'
    if getattr(error, 'errno', None) == 28 or 'space' in message.lower(): return 'DISK_FULL', '磁碟空間不足。請釋放至少 3 GB 空間，再重試安裝。'
    if 'Codex' in message and ('找不到' in message or '未找到' in message): return 'CODEX_MISSING', '找不到 Codex。請先完成「準備 AI 助手」，重新檢查後再安裝。'
    if any(s in message.lower() for s in ('timeout', 'timed out', 'connection', 'network', 'urlopen')): return 'CONNECTION_FAILED', '連線沒有完成。請確認網路或 CAD 連線狀態後重試；詳細原因在「詳細資料」。'
    if '損毀' in message or 'SHA' in message: return 'CHECKSUM_FAILED', '檔案驗證失敗。請重新下載同一版本的安裝套件後重試。'
    if message.startswith('指令失敗'):
        return 'COMPONENT_SETUP_FAILED', '元件設定未完成。請確認 Codex 已安裝、磁碟仍有空間，再按原本操作重試；技術原因保留在詳細資料。'
    if '\n' not in message and len(message) < 180 and any('\u4e00' <= c <= '\u9fff' for c in message):
        return 'ACTION_REQUIRED', message
    return 'ACTION_REQUIRED', '作業未完成。請確認軟體已開啟且完成設定，再重試；仍失敗時展開詳細資料查看原因。'
