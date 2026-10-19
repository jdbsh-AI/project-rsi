"""Run every adapter against isolated projects; no installed harness is required."""
import tempfile
import unittest
from pathlib import Path

import project_rsi as rsi
from harness_adapters import profiles, policy_for, CONFIG


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='rsi-adapters-')
        self.base = Path(self.tmp.name).resolve()

    def tearDown(self):
        self.tmp.cleanup()

    def submit_demo(self, info):
        run = Path(info['run'])
        spec = rsi.read_json(run / 'form-binding.json')['spec']
        payload = {key: spec[key] for key in ['form_id', 'run', 'manifest_sha256', 'submission_id']}
        payload.update(schema=1, answers=[{'id': 'A1', 'value': 'approve', 'comment': ''},
                                        {'id': 'R1', 'value': 'reject', 'comment': ''},
                                        {'id': 'C1', 'value': 'change', 'comment': 'Please simplify this.\n请保留这条多行备注。'}])
        path = run / 'submission.json'
        path.write_bytes(rsi.encoded(payload))
        return rsi.consume(run, path, 'isolated adapter test', session_id=info['session_id'])

    def test_all_profiles_apply_only_the_approved_target(self):
        for name in profiles():
            with self.subTest(harness=name):
                info = rsi.demo(self.base / name, name)
                result = self.submit_demo(info)
                policy = policy_for(name)
                self.assertEqual([i['decision'] for i in result['items']], ['ADOPTED_STATIC_ONLY', 'REJECTED', 'REVISION_REQUESTED'])
                self.assertEqual([c['path'] for c in result['changes']], [policy['instruction_files'][0]])
                root = Path(info['fixture_project'])
                text = (root / policy['instruction_files'][0]).read_text()
                self.assertIn('Verify the full result', text)
                if name == 'cursor':
                    self.assertTrue(text.startswith('---\n'))
                    self.assertIn('alwaysApply: true\n---\n', text)
                self.assertFalse((root / policy['skill_roots'][0] / 'learned-rejected').exists())
                self.assertIn('\n请保留', result['items'][2]['comment'])
                if policy['instruction_files'][0] != 'AGENTS.md':
                    self.assertFalse((root / 'AGENTS.md').exists())

    def test_install_each_harness_without_writing_instructions(self):
        for name in profiles():
            with self.subTest(harness=name):
                root = self.base / name
                root.mkdir()
                info = rsi.initialize(root, name, install_skill=True)
                installed = Path(info['skill_directory'])
                self.assertTrue((installed / 'SKILL.md').is_file())
                self.assertTrue((installed / 'scripts/project_rsi.py').is_file())
                self.assertTrue((installed / 'assets/harnesses.json').is_file())
                self.assertFalse((installed / '.git').exists())
                self.assertFalse((root / policy_for(name)['instruction_files'][0]).exists())
                with self.assertRaisesRegex(ValueError, 'already exists'):
                    rsi.initialize(root, name, install_skill=True)

    def test_custom_name_and_nested_skill_root_are_bound(self):
        info = rsi.demo(self.base / 'custom', 'generic')
        run = Path(info['run']); root = Path(info['fixture_project'])
        rsi.initialize(root, 'generic', ['docs/PROJECT_RULES.md'], ['tools/custom/skills'], 'local')
        plan = rsi.read_json(run / 'plan.json')
        plan['items'] = [plan['items'][0]]
        plan['items'][0]['changes'][0]['path'] = 'docs/PROJECT_RULES.md'
        (run / 'plan.json').write_bytes(rsi.encoded(plan)); (run / 'manifest.json').unlink()
        rsi.build(run / 'plan.json', run / 'form.html', info['session_id'])
        manifest = rsi.read_json(run / 'manifest.json')
        self.assertEqual(manifest['target_policy']['instruction_files'], ['docs/PROJECT_RULES.md'])
        spec = rsi.read_json(run / 'form-binding.json')['spec']
        payload = {key: spec[key] for key in ['form_id', 'run', 'manifest_sha256', 'submission_id']}
        payload.update(schema=1, answers=[{'id': 'A1', 'value': 'approve', 'comment': ''}])
        path = run / 'submission.json';path.write_bytes(rsi.encoded(payload))
        result = rsi.consume(run, path, 'synthetic custom target', info['session_id'])
        self.assertEqual(result['changes'][0]['path'], 'docs/PROJECT_RULES.md')

    def test_config_mutation_blocks_application(self):
        info = rsi.demo(self.base / 'config', 'claude')
        root = Path(info['fixture_project']);run = Path(info['run'])
        rsi.initialize(root, 'claude')
        (run / 'manifest.json').unlink()
        rsi.build(run / 'plan.json', run / 'form.html', info['session_id'])
        config = rsi.read_json(root / CONFIG);config['instruction_files'] = ['OTHER.md']
        (root / CONFIG).write_bytes(rsi.encoded(config))
        with self.assertRaisesRegex(ValueError, 'configuration changed'):
            self.submit_demo(info)

    def test_cursor_existing_frontmatter_is_preserved(self):
        info = rsi.demo(self.base / 'cursor', 'cursor')
        root = Path(info['fixture_project']);run = Path(info['run'])
        path = root / '.cursor/rules/project-rsi.mdc';path.parent.mkdir(parents=True)
        original = '---\ndescription: Existing custom rule\nglobs: "src/**"\nalwaysApply: false\n---\n\nKeep existing instructions.\n'
        path.write_text(original);(run / 'manifest.json').unlink()
        rsi.build(run / 'plan.json', run / 'form.html', info['session_id'])
        self.submit_demo(info)
        self.assertTrue(path.read_text().startswith(original.rstrip()))

    def test_profile_detection_does_not_guess_between_harnesses(self):
        root = self.base / 'ambiguous';root.mkdir()
        (root / 'CLAUDE.md').touch();(root / 'GEMINI.md').touch()
        with self.assertRaisesRegex(ValueError, 'multiple harnesses'):
            rsi.initialize(root)
        self.assertFalse((root / CONFIG).exists())

    def test_existing_override_and_fallback_are_selected(self):
        for name, existing in [('codex', 'AGENTS.override.md'), ('claude', '.claude/CLAUDE.md'), ('opencode', 'CLAUDE.md'), ('dsh', 'CLAUDE.md'), ('workbuddy', '.codebuddy/CODEBUDDY.md')]:
            root = self.base / name;root.mkdir();path = root / existing;path.parent.mkdir(parents=True, exist_ok=True);path.touch()
            self.assertEqual(rsi.initialize(root, name)['instruction_files'], [existing])

    def test_instruction_overwrite_and_unlisted_targets_are_rejected(self):
        policy = policy_for('claude')
        for path, operation in [('CLAUDE.md', 'write'), ('AGENTS.md', 'append_lesson'), ('../CLAUDE.md', 'append_lesson'), ('C:\\CLAUDE.md', 'append_lesson'), ('.git/CLAUDE.md', 'append_lesson')]:
            with self.subTest(path=path):
                with self.assertRaises(ValueError):rsi.target_kind(path, operation, policy)

    def test_demo_refuses_existing_real_directory(self):
        with self.assertRaisesRegex(ValueError, 'must not exist'):
            rsi.demo(self.base)

    def test_concurrent_consumer_is_blocked(self):
        info = rsi.demo(self.base / 'concurrent')
        with rsi.run_lock(Path(info['run'])):
            with self.assertRaisesRegex(ValueError, 'already processing'):
                self.submit_demo(info)

    def test_local_session_is_explicit(self):
        info = rsi.demo(self.base / 'identity')
        with self.assertRaisesRegex(ValueError, 'session mismatch'):
            rsi.check_session(info['session_id'], 'local', 'wrong')

    def test_synthetic_mode_requires_fixture_identity(self):
        info = rsi.demo(self.base / 'synthetic-boundary')
        root = Path(info['fixture_project']);run = Path(info['run'])
        (run / 'manifest.json').unlink();(root / '.project-rsi-fixture.json').unlink()
        original = (root / 'AGENTS.md').read_bytes()
        with self.assertRaisesRegex(ValueError, 'synthetic fixture marker'):
            rsi.build(run / 'plan.json', run / 'form.html', info['session_id'])
        self.assertEqual((root / 'AGENTS.md').read_bytes(), original)

    def test_review_output_cannot_replace_active_instructions(self):
        info = rsi.demo(self.base / 'output-boundary')
        root = Path(info['fixture_project']);run = Path(info['run'])
        (run / 'manifest.json').unlink()
        original = (root / 'AGENTS.md').read_bytes()
        with self.assertRaisesRegex(ValueError, 'cannot overwrite active'):
            rsi.build(run / 'plan.json', root / 'AGENTS.md', info['session_id'])
        self.assertEqual((root / 'AGENTS.md').read_bytes(), original)


if __name__ == '__main__':
    unittest.main()
