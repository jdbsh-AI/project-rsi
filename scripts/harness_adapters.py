"""Project-local harness profiles. No external dependencies or shell commands."""
import json
import re
from pathlib import Path

ASSETS = Path(__file__).resolve().parent.parent / 'assets'
CONFIG = '.project-rsi/config.json'


def profiles():
    return json.loads((ASSETS / 'harnesses.json').read_text(encoding='utf-8'))


def relative(value):
    # Backslashes are rejected on every OS so a plan means the same thing everywhere.
    if not isinstance(value, str) or not value or '\\' in value:
        raise ValueError('use a nonempty project-relative POSIX path')
    path = Path(value)
    if path.is_absolute() or '..' in path.parts or ':' in value or '.git' in path.parts:
        raise ValueError('project-relative path outside .git required')
    return path.as_posix()


def policy_for(name, instruction_files=None, skill_roots=None):
    table = profiles()
    if name not in table:
        raise ValueError('unknown harness: ' + str(name))
    policy = dict(table[name])
    policy['harness'] = name
    if instruction_files is not None:
        policy['instruction_files'] = instruction_files
    if skill_roots is not None:
        policy['skill_roots'] = skill_roots
    for key in ['instruction_files', 'skill_roots']:
        if not isinstance(policy[key], list) or not policy[key]:
            raise ValueError(key + ' must be a nonempty list')
        policy[key] = [relative(v) for v in policy[key]]
    if any(not p.endswith(('.md', '.mdc')) for p in policy['instruction_files']):
        raise ValueError('instruction targets must use .md or .mdc')
    if any(not p.endswith('/skills') or p in {'.git/skills'} for p in policy['skill_roots']):
        raise ValueError('skill roots must end in /skills')
    return policy


def target_kind(path, operation, policy=None):
    policy = policy or policy_for('codex')
    path = relative(path)
    if path in policy['instruction_files'] and operation == 'append_lesson':
        return 'AGENTS.md' if path == 'AGENTS.md' else 'instructions'
    if operation == 'write' and path.endswith('.md'):
        for root in policy['skill_roots']:
            prefix = root + '/'
            if path.startswith(prefix):
                suffix = path[len(prefix):]
                if re.fullmatch(r'[a-z0-9][a-z0-9-]*/(?:[a-zA-Z0-9_-]+/)*[a-zA-Z0-9_.-]+\.md', suffix):
                    return 'skill'
    raise ValueError('target outside declared instruction/skill Markdown scope')


def skill_name(path, policy):
    for root in policy['skill_roots']:
        prefix = root + '/'
        if path.startswith(prefix):
            return path[len(prefix):].split('/')[0]
    raise ValueError('skill target outside declared roots')


def detect(root):
    # Shared AGENTS/skill locations cannot identify a harness reliably.
    signatures = {'claude': ['CLAUDE.md', '.claude'], 'gemini': ['GEMINI.md', '.gemini'],
                  'cursor': ['.cursor'], 'copilot': ['.github/copilot-instructions.md'],
                  'opencode': ['opencode.json', 'opencode.jsonc', '.opencode'], 'codex': ['.codex'],
                  'dsh': ['.dsh'], 'workbuddy': ['CODEBUDDY.md', '.codebuddy']}
    found = [name for name, paths in signatures.items() if any((root / p).exists() for p in paths)]
    if len(found) > 1:
        raise ValueError('multiple harnesses detected; choose --harness explicitly: ' + ', '.join(found))
    return found[0] if found else 'generic'
