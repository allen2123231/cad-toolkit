import contextlib
import io
import itertools
import json
from pathlib import Path
import sys
from unittest.mock import patch
import unittest
from test_lifecycle import Fixture
from manager import Manager, emit
from experience import outcome, Cancelled, friendly_error
from common import atomic_json, sha256

class ExperienceTests(Fixture):
    def test_raw_errors_stay_out_of_primary_hint(self):
        self.assertNotIn('Traceback', friendly_error(RuntimeError('Traceback\nprivate path details'))[1])
        self.assertNotIn('C:/', friendly_error(RuntimeError('指令失敗 (1): C:/private/python.exe\nraw output'))[1])

    def test_all_readiness_stages(self):
        base=dict(installed=True,mcp=True,cad=True,bridge=True,document={'name':'練習'},processes=[{'pid':1}])
        for c in ('autocad','inventor','rhino'):
            doc={'document':{'name':'練習'}} if c=='inventor' else base['document']
            value={**base,'document':doc}
            self.assertEqual(outcome(c,value,True)['code'],'READY')
            self.assertFalse(outcome(c,value,False)['ready'])
            for change,code in [({'installed':False},'NOT_INSTALLED'),({'cad':False},'CAD_NOT_RUNNING'),({'mcp':False},'MCP_START_FAILED'),({'bridge':False},'BRIDGE_NOT_CONNECTED'),({'document':None},'NO_DOCUMENT'),({'processes':[{},{}]},'MULTIPLE_PROCESSES')]:
                result=outcome(c,{**value,**change},True)
                self.assertEqual(result['code'],code);self.assertFalse(result['ready']);self.assertTrue(result['next_action'])
        self.assertEqual(outcome('inventor',{**base,'document':{'document':None}},True)['code'],'NO_DOCUMENT')
        self.assertEqual(outcome('autocad',{**base,'bridge':False,'document_missing':True},True)['code'],'NO_DOCUMENT')

    def test_missing_component_emits_event_and_preserves_old_state(self):
        manager=Manager(self.base/'Toolkit')
        manager.state['active']={'inventor':'old'};manager.save()
        capture=io.StringIO()
        with contextlib.redirect_stdout(capture): result=manager.diagnose(['rhino'])
        event=json.loads(capture.getvalue())
        self.assertEqual(event['error_code'],'NOT_INSTALLED');self.assertEqual(event['outcome'],'needs_action')
        self.assertFalse(result['rhino']['ready']);self.assertEqual(manager.state['active'],{'inventor':'old'})

    def test_event_schema_ascii_transport(self):
        capture=io.StringIO()
        with contextlib.redirect_stdout(capture): emit('安裝中',step='install',component='rhino',progress=20)
        raw=capture.getvalue();self.assertTrue(raw.isascii());value=json.loads(raw)
        self.assertTrue(set(['schema','step','component','outcome','progress','error_code','next_action']).issubset(value))

    def test_cancel_before_install_never_changes_active(self):
        payload=self.base/'payload';payload.mkdir();(payload/'test').write_text('test')
        atomic_json(payload/'bundle.json',{'version':'0.2.0-preview.1','files':{'test':sha256(payload/'test')}})
        manager=Manager(self.base/'Toolkit');manager.state['active']={'rhino':'old'}
        manager.cancel_file=self.base/'cancel';manager.cancel_file.touch()
        with self.assertRaises(Cancelled): manager.install(payload,['rhino'])
        self.assertEqual(manager.state['active'],{'rhino':'old'})
        self.assertEqual(friendly_error(Cancelled())[0],'CANCELLED')

    def test_no_document_blocks_activation(self):
        manager=Manager(self.base/'Toolkit');manager.state['candidate']={'selected':['inventor'],'path':'new'}
        with patch.object(manager,'diagnose',return_value={'inventor':{'bridge':True,'code':'NO_DOCUMENT'}}),patch.object(manager,'register_plugin') as register:
            with self.assertRaises(RuntimeError):manager.activate(['inventor'])
            register.assert_not_called()

    def test_partial_success_activates_only_requested_component(self):
        manager=Manager(self.base/'Toolkit');manager.state['candidate']={'selected':['inventor','rhino'],'path':'new'}
        with patch.object(manager,'diagnose',return_value={'inventor':{'bridge':True,'code':'NOT_ENABLED'}}),patch.object(manager,'register_plugin'):
            manager.activate(['inventor'])
        self.assertEqual(manager.state['active'],{'inventor':'new'})

    def test_generated_guides_match_offline_source(self):
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
        from build_guides import outputs, ROOT
        for file,text in outputs().items():self.assertEqual((ROOT/file).read_text(encoding='utf-8'),text)

    def test_cancel_resume_keeps_completed_component_for_seven_choices(self):
        for n in range(1,4):
            for selected in itertools.combinations(['autocad','inventor','rhino'],n):
                with self.subTest(selected=selected):
                    root=self.base/('-'.join(selected));payload=root/'source';payload.mkdir(parents=True)
                    manifest={'version':'0.2.0-preview.1','files':{},'components':{c:{'wheel':c+'.whl'} for c in selected}}
                    atomic_json(payload/'bundle.json',manifest)
                    key=manifest['version']+'-'+'-'.join(sorted(selected))+'-'+sha256(payload/'bundle.json')[:12]
                    target=root/'versions'/key
                    first=selected[0];python=target/'envs'/first/'Scripts/python.exe';python.parent.mkdir(parents=True);python.write_bytes(b'kept')
                    atomic_json(target/(first+'.complete.json'),{'tools':8})
                    manager=Manager(root)
                    def stop_after_reuse(message,**values):
                        if values.get('component')==first and values.get('outcome')=='completed':raise Cancelled()
                    with patch('manager.emit',side_effect=stop_after_reuse),patch('manager.run') as run:
                        with self.assertRaises(Cancelled):manager.install(payload,list(selected))
                    run.assert_not_called();self.assertEqual(python.read_bytes(),b'kept')

if __name__=='__main__':unittest.main()
