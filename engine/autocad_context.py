"""Validate LT's passive, per-main-window native context before probing MCP."""
import json
from pathlib import Path
import time

def read_context(root,frame):
    path=Path(root)/'ipc'/('toolkit-context-'+str(int(frame['hwnd']))+'.json')
    try:
        stamp=path.stat().st_mtime
        if stamp<float(frame['processStart']) or stamp>time.time()+5:raise ValueError('stale context')
        value=json.loads(path.read_text(encoding='utf-8-sig'))
        if value.get('schema')!=1 or int(value.get('hwnd',0))!=int(frame['hwnd']) or value.get('product','').casefold()!='acadlt':raise ValueError('wrong context')
        doc=value.get('document')
        if not isinstance(doc,dict) or not isinstance(doc.get('name'),str) or not isinstance(doc.get('busy'),bool) or not isinstance(doc.get('dirty'),bool):raise ValueError('incomplete context')
        return {'version':value.get('version'),'hwnd':int(frame['hwnd']),'document':doc,'product':'AutoCAD LT'}
    except (OSError,ValueError,KeyError,TypeError) as exc:
        raise RuntimeError('AutoCAD LT 自動連線尚未就緒。請先儲存並重新開啟 LT，再按「重新檢查」；不需要輸入 APPLOAD。') from exc
