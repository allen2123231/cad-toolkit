"""Read existing Autodesk state; LT reports from inside its LISP bridge."""
import argparse
import json

def read(root=None):
    import window_scan
    frames=[w for w in window_scan.scan() if w['kind']=='autocad' and w.get('visible',True)]
    if len(frames)!=1:raise RuntimeError('請保留唯一的 AutoCAD／LT 主視窗後重新檢查，避免誤連。')
    if frames[0].get('product')=='AutoCAD LT':
        if not root:raise RuntimeError('LT 診斷缺少 Toolkit 安裝位置。')
        from autocad_context import read_context
        doc=read_context(root,frames[0])['document']
        return {'path':doc['path'],'name':doc['name'],'dbmod':doc.get('dbmod',int(doc['dirty'])),'units':doc.get('units'),'cmdactive':doc.get('cmdactive',int(doc['busy']))}
    import pythoncom
    import win32com.client
    pythoncom.CoInitialize()
    try:
        app=win32com.client.GetActiveObject('AutoCAD.Application')
        if int(app.HWND)!=frames[0]['hwnd']:raise RuntimeError('AutoCAD 診斷視窗身分不符，已停止檢查。')
        if app.Documents.Count==0:return {'document_missing':True}
        doc=app.ActiveDocument
        return {'path':doc.FullName,'name':doc.Name,'dbmod':doc.GetVariable('DBMOD'),'units':doc.GetVariable('INSUNITS'),'cmdactive':doc.GetVariable('CMDACTIVE')}
    finally:pythoncom.CoUninitialize()

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--root');args=parser.parse_args()
    print(json.dumps(read(args.root),ensure_ascii=True))
