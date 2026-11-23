"""Prove notification preflight can retry reads but never retry SendCommand."""
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'engine'))
from autocad_session import guarded_backend
from autocad_channel import NotSent


class NotifyTests(unittest.TestCase):
    def setUp(self):
        self.frame=dict(kind='autocad',product='AutoCAD',pid=1,hwnd=42,processStart=1)
        self.sender=guarded_backend(object,None)();self.sender._toolkit_frame=self.frame
        self.app=Mock();self.app.HWND=42;self.app.ActiveDocument.GetVariable.return_value=0
        self.client=Mock();self.client.GetActiveObject.return_value=self.app
        com=types.ModuleType('win32com');com.__path__=[];com.client=self.client
        self.co=Mock()
        self.modules=patch.dict(sys.modules,{'pythoncom':self.co,'win32com':com,'win32com.client':self.client})
        self.modules.start();self.addCleanup(self.modules.stop)
        scan=patch('autocad_session.window_scan.scan',return_value=[self.frame]);scan.start();self.addCleanup(scan.stop)

    def test_busy_preflight_does_not_send_or_create_uncertainty(self):
        self.app.ActiveDocument.GetVariable.return_value=1
        with self.assertRaises(NotSent) as error:self.sender._post_text('(c:mcp-dispatch)')
        self.assertEqual(error.exception.code,'CAD_BUSY')
        self.app.ActiveDocument.SendCommand.assert_not_called()
        self.co.CoUninitialize.assert_called_once()

    def test_hwnd_failure_is_proven_not_sent_with_phase(self):
        self.app.HWND=99
        with self.assertRaises(NotSent):self.sender._post_text('(c:mcp-dispatch)')
        self.app.ActiveDocument.SendCommand.assert_not_called()

    def test_failed_send_is_uncertain_and_is_never_retried(self):
        self.app.ActiveDocument.SendCommand.side_effect=OSError('connection lost after invocation')
        with self.assertRaises(OSError):self.sender._post_text('(c:mcp-dispatch)')
        self.app.ActiveDocument.SendCommand.assert_called_once_with('(c:mcp-dispatch)\n')

    def test_temporary_property_failure_only_retries_preflight(self):
        class Application:
            calls=0
            @property
            def HWND(self):
                self.calls+=1
                if self.calls==1:raise AttributeError('busy lookup')
                return 42
        app=Application();app.ActiveDocument=self.app.ActiveDocument
        self.client.GetActiveObject.return_value=app
        with patch('time.sleep'):
            self.sender._post_text('(c:mcp-read)')
        self.assertEqual(app.calls,2)
        self.app.ActiveDocument.SendCommand.assert_called_once_with('(c:mcp-read)\n')


if __name__=='__main__':unittest.main()
