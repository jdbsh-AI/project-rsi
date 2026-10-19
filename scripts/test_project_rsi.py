#!/usr/bin/env python3
"""Deterministic guard tests. Native-host E2E must be tested separately."""
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('project_rsi',Path(__file__).with_name('project_rsi.py'))
rsi=importlib.util.module_from_spec(spec);spec.loader.exec_module(rsi)

def fixture(base,thread='synthetic-thread',form_id='synthetic-review'):
    root=base/'project';root.mkdir();run=base/'run';run.mkdir()
    (root/'.project-rsi-fixture.json').write_bytes(rsi.encoded({'synthetic':True,'project_root':str(root)}))
    (root/'AGENTS.md').write_text('Governance must survive.\n\n<!-- PROJECT_RSI_LESSONS_BEGIN -->\nExisting lesson.\n<!-- PROJECT_RSI_LESSONS_END -->\n')
    (run/'review.md').write_text('Synthetic review; no real project or human approval.\n')
    (run/'probe.json').write_text(json.dumps({'level':'OFFLINE_SYNTHETIC','checks':[{'name':'fixture behavior','passed':True,'evidence':'synthetic fixture only'}]}))
    (run/'lesson.md').write_text('- Check the complete result before claiming success.\n')
    for name in ['rejected','revised']:
        (run/(name+'.md')).write_text('---\nname: learned-'+name+'\ndescription: Synthetic example only.\n---\nKeep project boundaries.\n')
    items=[]
    for ident,title,path,op,candidate in [
        ('A1','Approve the lesson','AGENTS.md','append_lesson','lesson.md'),
        ('R1','Reject this skill','.agents/skills/learned-rejected/SKILL.md','write','rejected.md'),
        ('C1','Revise this skill','.agents/skills/learned-revised/SKILL.md','write','revised.md')]:
        items.append({'id':ident,'title':title,'summary':'Synthetic proposal.','impact':'Only isolated fixture files.','evidence':['synthetic-fixture:event-1'],'changes':[{'path':path,'operation':op,'candidate':candidate,'probe':'probe.json'}]})
    plan={'schema':1,'form_id':form_id,'project_root':str(root),'thread_id':thread,'review_file':'review.md','items':items,'test_mode':True,'test_choices':{'A1':'approve','R1':'reject','C1':'change'},'test_note':'E2E_LONG_NOTE: 请把这个建议写得更简短一些，同时保留对范围和权限的说明。\n第二行用于验证多行中文备注能够完整传回当前对话，并被记录为待调整，而不是直接修改。'}
    (run/'plan.json').write_text(json.dumps(plan))
    rsi.build(run/'plan.json',run/'form.html')
    binding=rsi.read_json(run/'form-binding.json')['spec']
    submission={'schema':1,'form_id':plan['form_id'],'run':str(run),'manifest_sha256':binding['manifest_sha256'],'submission_id':binding['submission_id'],'answers':[{'id':'A1','value':'approve','comment':''},{'id':'R1','value':'reject','comment':''},{'id':'C1','value':'change','comment':'Please revise this wording.\nKeep the original scope.'}]}
    return root,run,submission

class GuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='project-rsi-');self.base=Path(self.tmp.name).resolve()
        self.env=patch.dict(os.environ,{'CODEX_THREAD_ID':'synthetic-thread'});self.env.start()
        self.root,self.run,self.payload=fixture(self.base)
    def tearDown(self):self.env.stop();self.tmp.cleanup()
    def consume(self):
        p=self.run/'submission.json';p.write_bytes(rsi.encoded(self.payload));return rsi.consume(self.run,p,'synthetic unit test, not human approval')
    def test_mixed_decisions_and_exact_readback(self):
        result=self.consume()
        self.assertEqual([i['decision'] for i in result['items']],['ADOPTED_STATIC_ONLY','REJECTED','REVISION_REQUESTED'])
        self.assertEqual(result['changes'][0]['kind'],'AGENTS.md')
        self.assertIn('complete result',(self.root/'AGENTS.md').read_text())
        self.assertFalse((self.root/'.agents/skills/learned-rejected').exists())
        self.assertFalse((self.root/'.agents/skills/learned-revised').exists())
        self.assertIn('\nKeep the original scope.',result['items'][2]['comment'])
    def test_duplicate_is_idempotent(self):
        first=self.consume();data=(self.root/'AGENTS.md').read_bytes();mtime=(self.root/'AGENTS.md').stat().st_mtime_ns
        second=self.consume();self.assertTrue(second['duplicate']);self.assertEqual(first['changes'],second['changes'])
        self.assertEqual(data,(self.root/'AGENTS.md').read_bytes());self.assertEqual(mtime,(self.root/'AGENTS.md').stat().st_mtime_ns)
    def test_approved_skill_is_written_and_classified(self):
        self.payload['answers'][1]['value']='approve'
        result=self.consume();self.assertTrue((self.root/'.agents/skills/learned-rejected/SKILL.md').is_file())
        self.assertEqual(result['changes'][1]['kind'],'skill')
    def test_reused_id_cannot_change_decision(self):
        self.consume();self.payload['answers'][1]['value']='approve'
        with self.assertRaisesRegex(ValueError,'reused'):self.consume()
    def test_foreign_thread_and_manifest_rejected(self):
        with patch.dict(os.environ,{'CODEX_THREAD_ID':'other-thread'}):
            with self.assertRaisesRegex(ValueError,'conversation'):self.consume()
        self.payload['manifest_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'binding'):self.consume()
    def test_missing_revision_note_blocks_before_writes(self):
        original=(self.root/'AGENTS.md').read_bytes();self.payload['answers'][2]['comment']=''
        with self.assertRaisesRegex(ValueError,'comment'):self.consume()
        self.assertEqual(original,(self.root/'AGENTS.md').read_bytes())
    def test_candidate_tampering_defers_affected_item(self):
        (self.run/'lesson.md').write_text('changed after review')
        result=self.consume();self.assertEqual(result['items'][0]['decision'],'DEFERRED_CONFLICT');self.assertFalse(result['changes'])
    def test_concurrent_governance_is_preserved(self):
        p=self.root/'AGENTS.md';p.write_text('New governance.\n'+p.read_text())
        self.consume();self.assertTrue(p.read_text().startswith('New governance.\nGovernance must survive.'))
    def test_concurrent_lesson_conflict_preserves_current(self):
        p=self.root/'AGENTS.md';p.write_text(p.read_text().replace('Existing lesson.','Another writer changed this lesson.'));current=p.read_bytes()
        result=self.consume();self.assertEqual(result['items'][0]['decision'],'DEFERRED_CONFLICT');self.assertEqual(current,p.read_bytes())
    def test_approval_note_is_not_ignored(self):
        self.payload['answers'][0]['comment']='But change the scope first.'
        result=self.consume();self.assertEqual(result['items'][0]['decision'],'APPROVAL_NOTES_NEED_INTERPRETATION');self.assertFalse(result['changes'])
    def test_path_and_symlink_escape_rejected(self):
        with self.assertRaises(ValueError):rsi.inside(self.root,'../escape.md')
        (self.root/'linked').symlink_to(self.run,target_is_directory=True)
        with self.assertRaises(ValueError):rsi.inside(self.root,'linked/lesson.md')
    def test_full_agents_overwrite_not_supported(self):
        with self.assertRaises(ValueError):rsi.target_kind('AGENTS.md','write')
    def test_two_approved_items_create_only_one_new_lesson_section(self):
        (self.root/'AGENTS.md').write_text('Original governance without a lesson section.\n')
        plan=rsi.read_json(self.run/'plan.json');first=plan['items'][0]
        second=json.loads(json.dumps(first));second['id']='A2';second['title']='Second independent lesson';second['changes'][0]['candidate']='second-lesson.md'
        (self.run/'second-lesson.md').write_text('- Preserve failures and unknown outcomes.\n')
        plan['items']=[first,second];(self.run/'plan.json').write_bytes(rsi.encoded(plan))
        (self.run/'manifest.json').unlink()
        rsi.build(self.run/'plan.json',self.run/'form.html')
        binding=rsi.read_json(self.run/'form-binding.json')['spec']
        self.payload.update(manifest_sha256=binding['manifest_sha256'],submission_id=binding['submission_id'],answers=[{'id':'A1','value':'approve','comment':''},{'id':'A2','value':'approve','comment':''}])
        result=self.consume();text=(self.root/'AGENTS.md').read_text()
        self.assertEqual(text.count('<!-- PROJECT_RSI_LESSONS_BEGIN -->'),1)
        self.assertEqual(text.count('<!-- PROJECT_RSI_LESSONS_END -->'),1)
        self.assertIn('complete result',text);self.assertIn('Preserve failures',text)
        self.assertEqual(result['changes'][0]['item_ids'],['A1','A2'])
    def test_generic_engine_cannot_bypass_project_guard(self):
        plan=rsi.read_json(self.run/'plan.json');plan['application_adapter']={'plan':'project-guard.json'}
        (self.run/'project-guard.json').write_text('{"approved_scope":"fixture only"}')
        (self.run/'plan.json').write_bytes(rsi.encoded(plan));(self.run/'manifest.json').unlink()
        rsi.build(self.run/'plan.json',self.run/'form.html');binding=rsi.read_json(self.run/'form-binding.json')['spec']
        self.payload.update(manifest_sha256=binding['manifest_sha256'],submission_id=binding['submission_id'])
        with self.assertRaisesRegex(ValueError,'project-specific'):self.consume()

if __name__=='__main__':unittest.main()
