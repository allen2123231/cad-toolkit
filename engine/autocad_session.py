"""Route the pinned file-IPC backend to exactly one verified CAD main frame."""
import window_scan

def find_managed_window():
    frames=[w for w in window_scan.scan() if w['kind']=='autocad' and w.get('visible',True)]
    if len(frames)!=1:return None
    # The backend rechecks this selection before dispatching. Never choose by title.
    return int(frames[0]['hwnd'])

def guarded_backend(base,CommandResult):
    class ManagedBackend(base):
        def _post_text(self,text):
            frame=self._toolkit_frame
            current=[w for w in window_scan.scan() if w['kind']=='autocad' and w.get('visible',True)]
            if len(current)!=1 or any(frame[k]!=current[0][k] for k in ('pid','hwnd','processStart')):raise RuntimeError('AutoCAD／LT 目標已變更，此次指令未傳送。')
            if frame.get('product')=='AutoCAD LT':
                return super()._post_text(text)
            # Full AutoCAD supports native automation. LT never takes this branch.
            import pythoncom,win32com.client
            pythoncom.CoInitialize()
            try:
                app=win32com.client.GetActiveObject('AutoCAD.Application')
                if int(app.HWND)!=int(frame['hwnd']):raise RuntimeError('AutoCAD 視窗身分不符，已停止傳送。')
                if app.ActiveDocument.GetVariable('CMDACTIVE')!=0:raise RuntimeError('AutoCAD 有進行中的指令，請完成後再重試；不會自動取消。')
                app.ActiveDocument.SendCommand(text+'\n')
            finally:pythoncom.CoUninitialize()
        async def initialize(self):
            frames=[w for w in window_scan.scan() if w['kind']=='autocad' and w.get('visible',True)]
            self._toolkit_frame=frames[0] if len(frames)==1 else None
            result=await super().initialize()
            if not result.ok and ('APPLOAD' in (result.error or '') or 'load it by hand' in (result.error or '')):
                return CommandResult(ok=False,error='AutoCAD／LT 自動連線尚未完成。請在 Toolkit 按「設定／修復」，自行儲存並重新開啟軟體，再重新檢查；不需要輸入連線指令。')
            return result
        async def _dispatch(self,command,params,timeout=None):
            frames=[w for w in window_scan.scan() if w['kind']=='autocad' and w.get('visible',True)]
            initial=getattr(self,'_toolkit_frame',None)
            if not initial or len(frames)!=1 or any(initial[k]!=frames[0][k] for k in ('pid','hwnd','processStart')):
                return CommandResult(ok=False,error='AutoCAD／LT 視窗已變更或有多個候選視窗，已停止此次操作。請保留唯一目標後重新連線。')
            import win32gui
            if not win32gui.IsWindowEnabled(self._hwnd):
                return CommandResult(ok=False,error='AutoCAD／LT 正在顯示對話框，或尚未開啟可操作的圖面；請完成後重新檢查。')
            if initial.get('product')=='AutoCAD LT':
                import os
                from pathlib import Path
                from autocad_context import read_context
                try:
                    doc=read_context(Path(os.environ['AUTOCAD_MCP_IPC_DIR']).parent,initial)['document']
                    if doc['busy']:return CommandResult(ok=False,error='AutoCAD LT 有進行中的指令，請完成後重試；不會自動取消。')
                except (RuntimeError,KeyError) as exc:return CommandResult(ok=False,error=str(exc))
            return await super()._dispatch(command,params,timeout=timeout)
    return ManagedBackend

def main():
    from autocad_mcp.backends import file_ipc
    from autocad_mcp.backends.base import CommandResult
    file_ipc.find_autocad_window=find_managed_window
    file_ipc.FileIPCBackend=guarded_backend(file_ipc.FileIPCBackend,CommandResult)
    from autocad_mcp.server import main as run
    run()

if __name__=='__main__':main()
