#!/usr/bin/env python3
"""Remember optional scheduling onboarding; never create or launch a schedule."""
import argparse
from datetime import datetime, timezone
from pathlib import Path

from project_rsi import LIMIT, atomic, bounded, encoded, inside, read_json

STATE = '.project-rsi/schedule-setup.json'
PREFERENCES = ('frequency', 'timing', 'timezone')


def text(value, name):
    if not isinstance(value, str) or not value.strip() or len(value) > 2000:
        raise ValueError(name + ' must be nonempty text, at most 2000 characters')
    return value.strip()


def load(project):
    project = Path(project).resolve(strict=True)
    if not project.is_dir():
        raise ValueError('project must be an existing directory')
    path = inside(project, STATE)
    if not path.exists():
        return project, path, {'schema': 1, 'project_root': str(project),
                               'state': 'unanswered', 'preferences': {}}
    bounded(path)
    state = read_json(path)
    if (state.get('schema') != 1 or state.get('project_root') != str(project)
            or state.get('state') not in {'requested', 'declined', 'deferred',
                                          'configured', 'unsupported', 'failed'}
            or not isinstance(state.get('preferences'), dict)):
        raise ValueError('invalid or foreign-project schedule setup state')
    return project, path, state


def status(project, context='interactive'):
    if context not in {'interactive', 'scheduled'}:
        raise ValueError('unknown invocation context')
    project, _, state = load(project)
    missing = [key for key in PREFERENCES if not state['preferences'].get(key)]
    current = state['state']
    if context == 'scheduled':
        action = 'skip_onboarding_for_scheduled_run'
    elif current == 'unanswered':
        action = 'ask_opt_in'
    elif current == 'requested':
        action = ('ask_schedule_details' if missing else
                  'verify_or_update_existing' if state.get('automation') else
                  'check_host_and_create')
    elif current == 'configured':
        action = 'verify_existing_schedule'
    else:
        action = 'continue_without_new_schedule'
    return {**state, 'context': context, 'next_action': action,
            'should_ask_opt_in': action == 'ask_opt_in',
            'missing_preferences': missing,
            'scheduler_called': False,
            'live_schedule_verified': False}


def save(path, state):
    # Repeated identical decisions/readbacks should not rewrite local state.
    previous = read_json(path) if path.exists() else None
    comparable = lambda value: {key: val for key, val in (value or {}).items()
                                if key != 'updated_at'}
    if comparable(previous) != comparable(state):
        state['updated_at'] = datetime.now(timezone.utc).isoformat()
        data = encoded(state)
        if len(data) > LIMIT:
            raise ValueError('schedule setup state exceeds 24 KiB')
        atomic(path, data)


def decide(project, choice, confirmation_reference, frequency=None, timing=None, zone=None):
    _, path, previous = load(project)
    reference = text(confirmation_reference, 'actual user confirmation reference')
    if choice not in {'enable', 'decline', 'later'}:
        raise ValueError('choice must be enable, decline, or later')
    supplied = {'frequency': frequency, 'timing': timing, 'timezone': zone}
    if choice != 'enable' and any(value is not None for value in supplied.values()):
        raise ValueError('decline/later cannot include a schedule preference')
    if choice != 'enable' and previous.get('automation'):
        raise ValueError('an existing automation is recorded; inspect/manage it through the host before marking setup declined/deferred')
    state = {'schema': 1, 'project_root': previous['project_root'],
             'state': {'enable': 'requested', 'decline': 'declined', 'later': 'deferred'}[choice],
             'confirmation_reference': reference, 'preferences': {}}
    if choice == 'enable':
        state['preferences'] = dict(previous['preferences'])
        for key, value in supplied.items():
            if value is not None:
                state['preferences'][key] = text(value, key)
        if previous.get('automation'):
            state['automation'] = previous['automation']
    save(path, state)
    return status(project)


def record(project, outcome, provider=None, automation_id=None,
           readback_reference=None, reason=None):
    _, path, state = load(project)
    if state['state'] not in {'requested', 'configured'} or not state.get('confirmation_reference'):
        raise ValueError('record an actual user opt-in before recording a scheduler result')
    if outcome in {'created', 'existing'}:
        if any(not state['preferences'].get(key) for key in PREFERENCES):
            raise ValueError('frequency, timing, and timezone must all come from the user before scheduling')
        automation = {'provider': text(provider, 'provider'),
                      'id': text(automation_id, 'automation ID'),
                      'readback_reference': text(readback_reference, 'actual host readback reference')}
        if state.get('automation') and (state['automation']['provider'], state['automation']['id']) != (automation['provider'], automation['id']):
            raise ValueError('a different automation is already recorded; do not create a duplicate')
        state['state'] = 'configured'
        state['automation'] = automation
        state.pop('reason', None)
    elif outcome in {'unsupported', 'failed'}:
        state['state'] = outcome
        state['reason'] = text(reason, 'host capability or failure reason')
    else:
        raise ValueError('unknown scheduler result')
    save(path, state)
    return status(project)


def main():
    import json
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    p = commands.add_parser('status')
    p.add_argument('--project', type=Path, required=True)
    p.add_argument('--context', choices=['interactive', 'scheduled'], default='interactive')
    p = commands.add_parser('decide')
    p.add_argument('--project', type=Path, required=True)
    p.add_argument('--choice', choices=['enable', 'decline', 'later'], required=True)
    p.add_argument('--confirmation-reference', required=True)
    p.add_argument('--frequency');p.add_argument('--timing');p.add_argument('--timezone')
    p = commands.add_parser('record')
    p.add_argument('--project', type=Path, required=True)
    p.add_argument('--outcome', choices=['created', 'existing', 'unsupported', 'failed'], required=True)
    p.add_argument('--provider');p.add_argument('--automation-id')
    p.add_argument('--readback-reference');p.add_argument('--reason')
    args = parser.parse_args()
    if args.command == 'status':result = status(args.project, args.context)
    elif args.command == 'decide':result = decide(args.project, args.choice, args.confirmation_reference, args.frequency, args.timing, args.timezone)
    else:result = record(args.project, args.outcome, args.provider, args.automation_id, args.readback_reference, args.reason)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
