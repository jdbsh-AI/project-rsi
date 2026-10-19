"""Onboarding state tests use temporary projects; no real scheduler is invoked."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import project_rsi as rsi
import schedule_setup as setup


class ScheduleSetupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='rsi-setup-')
        self.root = Path(self.tmp.name).resolve()

    def tearDown(self):
        self.tmp.cleanup()

    def enable(self, **values):
        return setup.decide(self.root, 'enable', 'synthetic user choice', **values)

    def complete(self):
        return self.enable(frequency='weekly on Tuesday and Thursday', timing='16:35', zone='Asia/Shanghai')

    def test_first_status_is_read_only_and_offers_opt_in_without_defaults(self):
        status = setup.status(self.root)
        self.assertTrue(status['should_ask_opt_in'])
        self.assertEqual(status['next_action'], 'ask_opt_in')
        self.assertEqual(status['preferences'], {})
        self.assertFalse(status['scheduler_called'])
        self.assertFalse((self.root / '.project-rsi').exists())

    def test_init_reports_onboarding_but_creates_no_setup_state_or_timer(self):
        info = rsi.initialize(self.root, 'generic')
        self.assertTrue(info['schedule_onboarding']['should_ask_opt_in'])
        self.assertEqual(info['schedule_onboarding']['preferences'], {})
        self.assertFalse((self.root / setup.STATE).exists())
        self.assertFalse((self.root / 'AGENTS.md').exists())

    def test_reinitialization_preserves_a_saved_refusal(self):
        setup.decide(self.root, 'decline', 'synthetic prior user answer')
        path = self.root / setup.STATE
        before = path.read_bytes()
        info = rsi.initialize(self.root, 'generic')
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(info['schedule_onboarding']['state'], 'declined')
        self.assertFalse(info['schedule_onboarding']['should_ask_opt_in'])
        self.assertEqual(info['schedule_onboarding']['next_action'], 'continue_without_new_schedule')

    def test_yes_alone_requires_all_details_and_confirmation(self):
        result = self.enable()
        self.assertEqual(result['next_action'], 'ask_schedule_details')
        self.assertEqual(result['missing_preferences'], ['frequency', 'timing', 'timezone'])
        with self.assertRaisesRegex(ValueError, 'must all come from the user'):
            setup.record(self.root, 'created', 'synthetic-host', 'fixture-job', 'fixture readback')

    def test_partial_answers_ask_only_missing_fields(self):
        self.enable(frequency='weekdays')
        result = self.enable(timing='07:15')
        self.assertEqual(result['missing_preferences'], ['timezone'])
        self.assertEqual(result['preferences']['frequency'], 'weekdays')
        self.assertEqual(result['preferences']['timing'], '07:15')

    def test_complete_user_preferences_are_preserved_exactly(self):
        result = self.complete()
        self.assertEqual(result['next_action'], 'check_host_and_create')
        self.assertEqual(result['preferences'], {'frequency': 'weekly on Tuesday and Thursday',
                                                'timing': '16:35', 'timezone': 'Asia/Shanghai'})
        self.assertFalse(result['scheduler_called'])
        self.assertFalse(result['live_schedule_verified'])

    def test_interval_and_custom_schedules_have_no_fixed_daily_hour(self):
        result = self.enable(frequency='every 6 hours', timing='start after the next explicit launch', zone='UTC')
        self.assertEqual(result['next_action'], 'check_host_and_create')
        self.assertEqual(result['preferences']['frequency'], 'every 6 hours')
        self.assertEqual(result['preferences']['timing'], 'start after the next explicit launch')

    def test_decline_and_later_are_remembered_without_reprompting(self):
        for choice in ['decline', 'later']:
            with self.subTest(choice=choice):
                setup.decide(self.root, choice, 'synthetic user answer')
                result = setup.status(self.root)
                self.assertFalse(result['should_ask_opt_in'])
                self.assertEqual(result['next_action'], 'continue_without_new_schedule')
                self.assertEqual(result['preferences'], {})

    def test_scheduled_invocations_skip_questions_and_write_nothing(self):
        result = setup.status(self.root, 'scheduled')
        self.assertEqual(result['next_action'], 'skip_onboarding_for_scheduled_run')
        self.assertFalse(result['should_ask_opt_in'])
        self.assertFalse((self.root / '.project-rsi').exists())

    def test_outcome_cannot_be_recorded_without_opt_in(self):
        with self.assertRaisesRegex(ValueError, 'actual user opt-in'):
            setup.record(self.root, 'created', 'synthetic-host', 'fixture-job', 'fixture readback')
        self.assertFalse((self.root / setup.STATE).exists())

    def test_empty_confirmation_and_preference_fields_are_rejected(self):
        with self.assertRaises(ValueError):setup.decide(self.root, 'enable', '')
        with self.assertRaises(ValueError):self.enable(frequency=' ')
        self.assertFalse((self.root / setup.STATE).exists())

    def test_success_requires_actual_host_identity_and_readback_reference(self):
        self.complete()
        for provider, ident, reference in [('', 'id', 'ref'), ('host', '', 'ref'), ('host', 'id', '')]:
            with self.subTest(provider=provider, ident=ident, reference=reference):
                with self.assertRaises(ValueError):setup.record(self.root, 'created', provider, ident, reference)
        self.assertEqual(setup.status(self.root)['state'], 'requested')

    def test_registered_schedule_is_verified_not_recreated_on_next_activation(self):
        self.complete()
        result = setup.record(self.root, 'created', 'synthetic-host', 'fixture-job', 'synthetic readback result')
        self.assertEqual(result['next_action'], 'verify_existing_schedule')
        self.assertFalse(result['should_ask_opt_in'])
        self.assertFalse(result['live_schedule_verified'])
        self.assertEqual(result['automation']['id'], 'fixture-job')

    def test_existing_host_schedule_can_be_recorded_without_an_extra_create(self):
        self.complete()
        result = setup.record(self.root, 'existing', 'synthetic-host', 'already-there', 'synthetic existing lookup')
        self.assertEqual(result['state'], 'configured')
        self.assertFalse(result['scheduler_called'])

    def test_unsupported_and_failed_results_preserve_preferences(self):
        for outcome in ['unsupported', 'failed']:
            with self.subTest(outcome=outcome):
                self.complete()
                result = setup.record(self.root, outcome, reason='synthetic unavailable host or error')
                self.assertEqual(result['state'], outcome)
                self.assertEqual(result['preferences']['timing'], '16:35')
                self.assertEqual(result['next_action'], 'continue_without_new_schedule')
                self.assertFalse(result['scheduler_called'])

    def test_empty_unsupported_reason_is_not_recorded(self):
        self.enable()
        with self.assertRaises(ValueError):setup.record(self.root, 'unsupported', reason='')
        self.assertEqual(setup.status(self.root)['state'], 'requested')

    def test_repeated_decision_and_readback_do_not_rewrite_state(self):
        self.complete();path = self.root / setup.STATE
        before = path.stat().st_mtime_ns
        self.complete();self.assertEqual(path.stat().st_mtime_ns, before)
        setup.record(self.root, 'created', 'synthetic', 'job-id', 'synthetic ref')
        before = path.stat().st_mtime_ns
        setup.record(self.root, 'created', 'synthetic', 'job-id', 'synthetic ref')
        self.assertEqual(path.stat().st_mtime_ns, before)

    def test_oversized_receipt_cannot_make_existing_state_unreadable(self):
        value = '\u65e5' * 1800
        self.enable(frequency=value, timing=value, zone=value)
        path = self.root / setup.STATE
        before = path.read_bytes()
        with self.assertRaisesRegex(ValueError, 'exceeds 24 KiB'):
            setup.record(self.root, 'created', value, value, value)
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(setup.status(self.root)['state'], 'requested')

    def test_explicit_user_change_preserves_id_for_update_instead_of_new_task(self):
        self.complete();setup.record(self.root, 'created', 'synthetic', 'old-id', 'synthetic ref')
        result = self.enable(frequency='monthly', timing='first business day at 09:10')
        self.assertEqual(result['next_action'], 'verify_or_update_existing')
        self.assertEqual(result['automation']['id'], 'old-id')
        self.assertEqual(result['preferences']['timezone'], 'Asia/Shanghai')
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            setup.record(self.root, 'created', 'synthetic', 'another-id', 'synthetic ref')

    def test_declining_does_not_pretend_to_stop_an_existing_host_task(self):
        self.complete();setup.record(self.root, 'created', 'synthetic', 'old-id', 'synthetic ref')
        with self.assertRaisesRegex(ValueError, 'inspect/manage'):
            setup.decide(self.root, 'decline', 'synthetic cancel request')
        self.assertEqual(setup.status(self.root)['state'], 'configured')

    def test_foreign_project_state_is_not_reused(self):
        self.complete();path = self.root / setup.STATE
        state = rsi.read_json(path);state['project_root'] = str(self.root / 'other')
        path.write_bytes(rsi.encoded(state))
        with self.assertRaisesRegex(ValueError, 'foreign-project'):setup.status(self.root)

    def test_invalid_choices_and_context_are_rejected(self):
        with self.assertRaises(ValueError):setup.decide(self.root, 'yes-maybe', 'synthetic ref')
        with self.assertRaises(ValueError):setup.status(self.root, 'unknown')
        with self.assertRaises(ValueError):setup.decide(self.root, 'later', 'synthetic ref', timing='09:00')

    def test_installed_skill_cli_can_report_first_activation(self):
        info = rsi.initialize(self.root, 'workbuddy', install_skill=True)
        script = Path(info['skill_directory']) / 'scripts/schedule_setup.py'
        output = subprocess.check_output([sys.executable, str(script), 'status', '--project', str(self.root)], text=True, encoding='utf-8')
        self.assertEqual(json.loads(output)['next_action'], 'ask_opt_in')
        self.assertFalse((self.root / setup.STATE).exists())


if __name__ == '__main__':
    unittest.main()
