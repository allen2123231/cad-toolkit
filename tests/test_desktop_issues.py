"""Regressions for hidden CAD processes being presented as usable windows."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"engine"))
import runtime


class HiddenWindowStatusTests(unittest.TestCase):
    def test_closed_window_discards_an_inflight_successful_probe(self):
        frame={'kind':'rhino','pid':12,'hwnd':22,'processStart':1,'instance_id':'first'}
        row={'id':'rhino','code':'READY','document':{'name':'closed model'},'verified_windows':[runtime.window_identity(frame)]}
        value=runtime.visible_status(row,[],[])
        self.assertEqual(value['code'],'CAD_NOT_RUNNING');self.assertIsNone(value['document'])
        value=runtime.visible_status({**row,'code':'READY','verified_windows':[runtime.window_identity(frame)]},[frame],[])
        self.assertEqual(value['code'],'CAD_NOT_RUNNING')
    def test_reopened_window_cannot_reuse_old_readiness(self):
        before={'kind':'inventor','pid':12,'hwnd':22,'processStart':1}
        after={**before,'processStart':2}
        row={'id':'inventor','code':'READY','document':{'name':'old'},'verified_windows':[runtime.window_identity(before)]}
        self.assertNotEqual(runtime.visible_status(row,[after],[12])['code'],'READY')
    def test_hidden_inventor_must_not_be_ready_or_expose_old_document(self):
        with tempfile.TemporaryDirectory() as root, patch('runtime.version',return_value='0.1.0'), patch('runtime.native',return_value={'ready':True,'hwnd':456,'document':{'name':'old document'}}), patch('window_scan.scan',return_value=[]):
            value=runtime.row('inventor',{'python':sys.executable,'enabled':True},[123],root,{}, {})
        self.assertNotEqual(value['code'],'READY')
        self.assertIsNone(value['document'])

    def test_hidden_rhino_bridge_must_not_be_ready(self):
        native={'pid':123,'hwnd':456,'guard_protocol':1,'version':'0.5.3','port':1999}
        with tempfile.TemporaryDirectory() as root, patch('runtime.version',return_value='0.5.3'), patch('runtime.collect',return_value=[native]), patch('runtime.probe',return_value={'code':'READY','document':{'name':'old model'}}), patch('window_scan.scan',return_value=[]):
            value=runtime.row('rhino',{'python':sys.executable,'command':[sys.executable],'enabled':True},[123],root,{}, {})
        self.assertNotEqual(value['code'],'READY')
        self.assertIsNone(value['document'])


if __name__=='__main__':unittest.main()
