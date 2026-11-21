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
                # Validate the child still belongs to the exact main frame. A
                # failed PostMessage is an interruption, never a successful send.
                import ctypes
                from ctypes import wintypes as W
                u=ctypes.WinDLL('user32',use_last_error=True)
                u.PostMessageW.argtypes=[W.HWND,W.UINT,W.WPARAM,W.LPARAM];u.PostMessageW.restype=W.BOOL
                u.IsChild.argtypes=[W.HWND,W.HWND];u.IsChild.restype=W.BOOL
                target=self._command_hwnd or self._hwnd
                if target!=self._hwnd and not u.IsChild(self._hwnd,target):raise RuntimeError('AutoCAD LT 收件視窗已變更。')
                for ch in text+'\r':
                    if not u.PostMessageW(target,0x0102,ord(ch),0):raise ctypes.WinError(ctypes.get_last_error())
                return
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
            # Initialization must not replay a ping or hide recovery behind a
            # cached failed backend. Native loading belongs to the owned bundle.
            self._channel()
            return await self.status()

        def _attach(self,frame):
            changed=getattr(self,'_toolkit_frame',None)!=frame
            self._toolkit_frame=frame;self._hwnd=int(frame['hwnd'])
            self._command_hwnd=self._find_command_line_hwnd()
            if changed or self._screenshot_provider is None:
                try:
                    from autocad_mcp.screenshot import Win32ScreenshotProvider
                    self._screenshot_provider=Win32ScreenshotProvider(self._hwnd)
                except Exception:self._screenshot_provider=None

        def _channel(self):
            if not hasattr(self,'_toolkit_channel'):
                from autocad_channel import local_channel
                self._toolkit_channel=local_channel(self._ipc_dir.parent)
            return self._toolkit_channel

        async def status(self):
            state=self._channel().state()
            frames=[w for w in window_scan.scan() if w['kind']=='autocad' and w.get('visible',True)]
            if len(frames)==1:self._attach(frames[0])
            return CommandResult(ok=True,payload={'backend':'file_ipc','hwnd':(state.get('current_frame') or {}).get('hwnd'),
                                                  'recovery':state,'ready':state['code']=='READY',
                                                  'capabilities':self.capabilities.__dict__})

        async def get_screenshot(self):
            from autocad_channel import identity
            frames=[w for w in window_scan.scan() if w['kind']=='autocad' and w.get('visible',True)]
            if len(frames)!=1 or identity(frames[0])!=identity(getattr(self,'_toolkit_frame',None)):
                return CommandResult(ok=False,error='AutoCAD 截圖目標已變更，請重新檢查視窗。')
            return await super().get_screenshot()

        async def _dispatch(self,command,params,timeout=None):
            import os
            from autocad_channel import identity
            def post(request):
                frames=[w for w in window_scan.scan() if w['kind']=='autocad' and w.get('visible',True)]
                if len(frames)!=1 or identity(frames[0])!=request['toolkit_frame']:raise RuntimeError('AutoCAD 目標已變更。')
                self._attach(frames[0])
                self._type_dispatch_trigger()
            try:
                value=await self._channel().dispatch(command,params,post,timeout=timeout if timeout is not None else float(os.environ.get('AUTOCAD_MCP_IPC_TIMEOUT','8')))
                return CommandResult(ok=value.get('ok',False),payload=value.get('payload'),error=value.get('error'))
            except (RuntimeError,OSError,ValueError) as exc:
                return CommandResult(ok=False,error='此次指令已停止；請查看 Toolkit 中斷恢復狀態。'+str(exc))
    return ManagedBackend

def main():
    from autocad_mcp.backends import file_ipc
    from autocad_mcp.backends.base import CommandResult
    file_ipc.find_autocad_window=find_managed_window
    file_ipc.FileIPCBackend=guarded_backend(file_ipc.FileIPCBackend,CommandResult)
    from autocad_mcp.server import main as run
    run()

if __name__=='__main__':main()
