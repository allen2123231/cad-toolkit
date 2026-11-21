"""One fenced CAD mailbox; interruption is evidence, never a retry instruction.

The OS lease is shared with older servers. Recovery confirmation only releases
the barrier: no request arguments or executable work are queued for replay.
"""
import asyncio
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import queue
import threading
import time
import uuid
from autocad_access import READ_COMMANDS


class NotSent(RuntimeError):
    """Only raised before ANY native notification call/character was attempted."""
    def __init__(self,code,message):
        super().__init__(message);self.code=code


def error_details(exc):
    # Only the exception, never request parameters or executable LISP.
    return dict(error_type=type(exc).__name__,error=str(exc)[:1600])


def atomic(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        tmp.write_text(json.dumps(value, ensure_ascii=True), encoding='utf-8')
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def read(path, default=None):
    try: return json.loads(Path(path).read_text(encoding='utf-8-sig'), strict=False)
    except FileNotFoundError: return default
    # Malformed evidence must not silently become an empty mailbox.


@contextmanager
def lease(directory):
    path = Path(directory)/'pcad-desktop.lock'; path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+b') as stream:
        stream.seek(0, 2)
        if not stream.tell(): stream.write(b'0'); stream.flush()
        stream.seek(0)
        if os.name == 'nt':
            import msvcrt
            acquire = lambda: msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            release = lambda: msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            acquire = lambda: fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            release = lambda: fcntl.flock(stream, fcntl.LOCK_UN)
        try: acquire()
        except OSError as exc: raise RuntimeError('DESKTOP_BUSY_OTHER_CLIENT') from exc
        try: yield
        finally: stream.seek(0); release()


def identity(frame):
    return {key:frame[key] for key in ('pid','hwnd','processStart')} if frame else None


def failed(code):
    messages = {
        'RECOVERY_REQUIRED':'上一批指令結果待確認。請在 Toolkit「中斷恢復」重新開啟並檢查圖面；確認後重新提出新操作。此次要求未排入執行，也不會自動重送上一批。',
        'CAD_CLOSED':'AutoCAD／LT 已關閉。可使用 open_application 重新開啟；未傳送繪圖指令。',
        'SELECT_TARGET':'請保留唯一且可見的 AutoCAD／LT 目標視窗，再重新提出操作。',
        'CAD_BUSY':'AutoCAD／LT 正忙碌或有對話框。此次操作未傳送，請完成後重新提出。',
        'BRIDGE_UPDATE_REQUIRED':'AutoCAD／LT 外掛需要更新。請在 Toolkit 修復並儲存、重新開啟軟體，不需要輸入載入指令。',
        'DESKTOP_BUSY_OTHER_CLIENT':'另一個要求正在使用 AutoCAD 通道。此次要求未排入執行，稍後請重新提出。',
        'READ_FAILED':'唯讀查詢未完成，沒有解除修改暫停，也沒有重送操作。',
    }
    return dict(ok=False, code=code, error=code+': '+messages.get(code, code), retry_automatically=False)


class Channel:
    def __init__(self, root, frames, context, alive=None):
        self.root=Path(root); self.ipc=self.root/'ipc'; self.frames=frames; self.context=context
        self.alive=alive or (lambda frame:any(identity(w)==frame for w in self.frames()))
        self.pending=self.ipc/'pcad-pending.json'; self.recovery=self.ipc/'toolkit-recovery.json'

    def target(self):
        frames=[w for w in self.frames() if w.get('kind')=='autocad' and w.get('visible',True)]
        if not frames: return None, None, 'CAD_CLOSED'
        if len(frames)!=1: return None, None, 'SELECT_TARGET'
        frame=frames[0]
        try: context=self.context(frame)
        except (RuntimeError, ValueError, OSError): return frame, None, 'BRIDGE_UPDATE_REQUIRED'
        if context.get('guard_protocol') not in (2,3) or not context.get('document',{}).get('id'):
            return frame, context, 'BRIDGE_UPDATE_REQUIRED'
        if context['document'].get('busy') or context.get('modal'):
            return frame, context, 'CAD_BUSY'
        return frame, context, None

    def _token(self, frame, context):
        if not frame or not context: return ''
        value=[identity(frame),context.get('document',{}).get('id')]
        return hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()

    def _id(self, value):
        key=value.get('request_id')
        if not isinstance(key,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',key):
            raise ValueError('中斷紀錄識別無效，已保留原檔，請檢查安裝。')
        return key

    def _journal(self, record):
        atomic(self.ipc/'toolkit-journal'/(self._id(record)+'.json'),record)

    def _unknown(self, pending, reason):
        record=read(self.ipc/'toolkit-journal'/(self._id(pending)+'.json'), {})
        record.update(request_id=pending['request_id'], command=pending.get('command','unknown'),
                      stage='unknown', reason=reason, interrupted_at=time.time())
        record.setdefault('ts',pending.get('ts',record['interrupted_at']))
        # Legacy metadata lacks a trustworthy target; require a subsequent restart.
        if 'frame' not in record:
            frames=[w for w in self.frames() if w.get('kind')=='autocad']
            record['frame']=identity(frames[0]) if len(frames)==1 else None
            record['legacy']=True
            record['closed_observed']=not frames
        atomic(self.recovery, record); self._journal(record)
        return record

    def _quarantine(self, record):
        key=self._id(record); folder=self.ipc/'toolkit-interrupted'/key
        folder.mkdir(parents=True,exist_ok=True)
        # Used only for OS-proven death, an audited query, or proven pre-send
        # failure. Keep evidence locally for diagnosis; never load it again.
        for path in (self.pending,self.ipc/f'autocad_mcp_cmd_{key}.json'):
            if path.exists(): os.replace(path,folder/path.name)

    def _reconcile(self):
        record=read(self.recovery)
        pending=read(self.pending)
        # An audited query cannot partially modify geometry. Retire its old mail
        # without replay, even if its caller died. Never apply this to arbitrary LISP.
        if record and record.get('command') in READ_COMMANDS:
            key=self._id(record)
            if (not pending or (pending.get('request_id')==key and pending.get('command')==record['command'])):
                self._quarantine(record)
                record.update(stage='archived_readonly',archived_at=time.time())
                self._journal(record);self.recovery.unlink();record=None;pending=None
        if not pending and not record:
            orphans=sorted(self.ipc.glob('autocad_mcp_cmd_*.json'))
            if orphans:
                pending=read(orphans[0])
                atomic(self.pending,pending)
        if pending and not record:
            key=self._id(pending)
            frames=[w for w in self.frames() if w.get('kind')=='autocad']
            # This is the one provably harmless legacy exception: no runnable
            # command, empty ping, and the only CAD process postdates the ping.
            if (pending.get('command')=='ping' and pending.get('params')=={} and len(frames)==1
                and float(frames[0]['processStart'])>float(pending.get('ts',float('inf')))
                and not list(self.ipc.glob('autocad_mcp_cmd_*.json'))):
                atomic(self.ipc/'toolkit-journal'/(key+'.json'),dict(request_id=key,command='ping',stage='archived_readonly',ts=time.time()))
                self._quarantine(pending)
            else: record=self._unknown(pending,'previous_sender_interrupted')
        if record:
            key=self._id(record)
            result=read(self.ipc/f'autocad_mcp_result_{key}.json')
            record['completion_received']=bool(result and result.get('request_id')==key)
            if record.get('frame'):
                dead=not self.alive(record['frame'])
            else:
                dead=not any(w.get('kind')=='autocad' for w in self.frames())
            if dead:
                record['closed_observed']=True
                # Do not move a different request if an obsolete client wrote it.
                if pending and pending.get('request_id')==key: self._quarantine(record)
            atomic(self.recovery,record)
        return record

    def _state(self):
        record=self._reconcile()
        frame,context,error=self.target()
        return dict(recovery=record,current_frame=identity(frame),current_document=(context or {}).get('document'),
                    read_available=bool(not error and (context or {}).get('guard_protocol')==3),
                    write_available=bool(not error and not record),
                    access_scope='toolkit_managed_only',
                    target_token=self._token(frame,context),code=error or ('RECOVERY_REQUIRED' if record else 'READY'),
                    can_confirm=bool(record and record.get('closed_observed') and not error and frame
                                     and float(frame['processStart'])>float(record.get('ts',float('inf')))
                                     and not self.pending.exists() and not list(self.ipc.glob('autocad_mcp_cmd_*.json'))))

    def state(self):
        try:
            with lease(self.ipc): return self._state()
        except RuntimeError as exc:
            if str(exc)!='DESKTOP_BUSY_OTHER_CLIENT':raise
            pending=read(self.pending,{})
            active=None
            if pending:
                key=self._id(pending)
                active=read(self.ipc/'toolkit-journal'/(key+'.json'),{})
                native=read(self.ipc/f'toolkit-receipt-{key}.json',{})
                if native.get('request_id')==key:active={**active,'native_phase':native.get('phase')}
            return dict(recovery=read(self.recovery),active=active,code=str(exc),can_confirm=False,target_token='')

    def confirm(self, request_id, target_token):
        with lease(self.ipc):
            state=self._state(); record=state['recovery']
            if not record or record['request_id']!=request_id or not state['can_confirm'] or not target_token or state['target_token']!=target_token:
                raise ValueError('請先重新開啟 CAD、完成載入並檢查目前圖面。視窗或文件再次變更時需重新確認。')
            record.update(stage='confirmed_no_replay',confirmed_at=time.time(),confirmed_target=state['current_frame'],confirmed_document=state['current_document'])
            self._journal(record)
            self.recovery.unlink()
            return dict(ok=True,message='已確認目前圖面。請回對話重新提出後續操作；先前指令不會自動重送。')

    async def dispatch(self, command, params, post, timeout=8):
        try:
            with lease(self.ipc):
                recovery=self._reconcile()
                readonly=command in READ_COMMANDS
                if recovery and not readonly:return failed('RECOVERY_REQUIRED')
                frame,context,error=self.target()
                if error:return failed(error)
                if readonly:
                    if context.get('guard_protocol')!=3:return failed('BRIDGE_UPDATE_REQUIRED')
                    # An earlier reader can die without its finally block. The
                    # lease proves no managed request is still using these files.
                    # Late read notifications have no path into the write inbox.
                    for stale in self.ipc.glob('autocad_mcp_read_*.json'):
                        folder=self.ipc/'toolkit-interrupted-reads';folder.mkdir(exist_ok=True)
                        os.replace(stale,folder/(uuid.uuid4().hex+'-'+stale.name))
                    return await self._read_dispatch(command,params,post,timeout,frame,context)
                key=uuid.uuid4().hex
                record=dict(request_id=key,command=command,frame=identity(frame),document=context['document'],stage='prepared',ts=time.time())
                self._journal(record)
                request=dict(request_id=key,command=command,toolkit_protocol=2,toolkit_hwnd=frame['hwnd'],
                             toolkit_document=context['document']['id'],toolkit_frame=identity(frame),
                             params={k:v for k,v in params.items() if v is not None},ts=record['ts'])
                atomic(self.pending,request)
                atomic(self.ipc/f'autocad_mcp_cmd_{key}.json',request)
                try:
                    record['stage']='notifying';self._journal(record)
                    # COM SendCommand may itself block while CAD runs a command.
                    # A daemon notifier keeps MCP responsive and process exit
                    # independent of a wedged COM call. The mailbox is never resent.
                    notices=queue.Queue()
                    def notify():
                        try:post(request)
                        except BaseException as exc:notices.put(exc)
                    threading.Thread(target=notify,daemon=True,name='cad-notify-'+key[:8]).start()
                    deadline=time.monotonic()+timeout
                    while True:
                        result_path=self.ipc/f'autocad_mcp_result_{key}.json'
                        result=read(result_path)
                        if result and result.get('request_id')==key:
                            record.update(stage='completed',finished_at=time.time(),ok=result.get('ok',False))
                            self._journal(record)
                            atomic(self.ipc/'pcad-receipts'/(key+'.json'),result)
                            self.pending.unlink(missing_ok=True)
                            (self.ipc/f'autocad_mcp_cmd_{key}.json').unlink(missing_ok=True)
                            result_path.unlink(missing_ok=True)
                            return result
                        if not notices.empty():raise notices.get_nowait()
                        native=read(self.ipc/f'toolkit-receipt-{key}.json',{})
                        if native.get('request_id')==key and native.get('phase')=='waiting_input':
                            self._unknown(request,'native_waiting_for_input')
                            return failed('RECOVERY_REQUIRED')
                        if not self.alive(identity(frame)):
                            self._unknown(request,'cad_process_closed');self._reconcile()
                            return failed('RECOVERY_REQUIRED')
                        if time.monotonic()>=deadline:
                            self._unknown(request,'completion_timeout')
                            return failed('RECOVERY_REQUIRED')
                        await asyncio.sleep(.1)
                except NotSent as exc:
                    record.update(stage='not_sent',finished_at=time.time(),**error_details(exc))
                    self._journal(record)
                    self._quarantine(record)
                    return failed(exc.code)
                except BaseException as exc:
                    # Includes cancellation/relay termination. OS death is handled
                    # from durable pending+journal by the next observer.
                    unknown=self._unknown(request,'sender_or_notification_interrupted')
                    unknown.update(**error_details(exc));atomic(self.recovery,unknown);self._journal(unknown)
                    self._reconcile()
                    raise
        except RuntimeError as exc:
            if str(exc)=='DESKTOP_BUSY_OTHER_CLIENT':return failed(str(exc))
            raise

    async def _read_dispatch(self,command,params,post,timeout,frame,context):
        key=uuid.uuid4().hex
        request=dict(request_id=key,command=command,params=params,toolkit_protocol=3,
                     toolkit_hwnd=frame['hwnd'],toolkit_frame=identity(frame),
                     toolkit_document=context['document']['id'],access='read',ts=time.time())
        mail=self.ipc/f'autocad_mcp_read_{key}.json'
        result_path=self.ipc/f'autocad_mcp_result_{key}.json'
        record=dict(request_id=key,command=command,access='read',frame=identity(frame),ts=request['ts'],stage='prepared')
        self._journal(record);atomic(mail,request)
        notices=queue.Queue()
        def notify():
            try:post(request)
            except BaseException as exc:notices.put(exc)
        threading.Thread(target=notify,daemon=True,name='cad-read-'+key[:8]).start()
        deadline=time.monotonic()+timeout
        try:
            while True:
                result=read(result_path)
                if result and result.get('request_id')==key:
                    record.update(stage='completed',ok=result.get('ok',False));return result
                if not notices.empty():raise notices.get_nowait()
                if not self.alive(identity(frame)):raise RuntimeError('CAD_CLOSED')
                if time.monotonic()>=deadline:raise TimeoutError('read completion timeout')
                await asyncio.sleep(.05)
        except Exception as exc:
            record.update(stage='read_failed',**error_details(exc))
            result=failed(exc.code if isinstance(exc,NotSent) else 'READ_FAILED')
            result.update(error_type=type(exc).__name__,error_detail=str(exc)[:1600]);return result
        finally:
            # A delayed c:mcp-read can only inspect the read inbox. It can NEVER
            # fall through to an abandoned write, even after recovery is cleared.
            mail.unlink(missing_ok=True);result_path.unlink(missing_ok=True)
            record['finished_at']=time.time();self._journal(record)


def local_channel(root):
    import window_scan
    from autocad_context import read_context
    from rhino_instances import process_start
    def alive(frame):
        # Creation time can remain readable after termination while ANY handle
        # references the process object. Check the OS signalled state first.
        import ctypes
        from ctypes import wintypes as W
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.OpenProcess.argtypes=[W.DWORD,W.BOOL,W.DWORD];kernel.OpenProcess.restype=W.HANDLE
        kernel.WaitForSingleObject.argtypes=[W.HANDLE,W.DWORD];kernel.CloseHandle.argtypes=[W.HANDLE]
        handle=kernel.OpenProcess(0x101000,False,int(frame['pid']))
        if not handle:return ctypes.get_last_error()!=87
        try:
            if kernel.WaitForSingleObject(handle,0)==0:return False
            start=process_start(frame['pid'])
            return start is None or abs(start-float(frame['processStart']))<.001
        finally:kernel.CloseHandle(handle)
    def context(frame):
        value=read_context(root,frame)
        u,_=window_scan.api();value['modal']=not bool(u.IsWindowEnabled(int(frame['hwnd'])))
        return value
    return Channel(root,lambda:window_scan.scan(include_hidden=True),context,alive)
