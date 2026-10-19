# Portable run format

Python 3.9+; the runtime uses only the standard library. Keep run files private and outside active skill paths. Paths inside a project or run must be relative, contained, and free of symlinks. Select the project explicitly; a conversation title is not project identity.

## Harness configuration

`init --project /absolute/project --harness claude --install-skill` records `.project-rsi/config.json` and installs this skill under the selected profile. It writes no project instruction lesson and creates no schedule. Existing skill destinations are not overwritten. Without `--install-skill`, only the configuration is created.

```json
{
  "schema": 1,
  "harness": "claude",
  "instruction_files": ["CLAUDE.md"],
  "skill_roots": [".claude/skills"],
  "transport": "local"
}
```

`--instructions docs/PROJECT_RULES.md` and `--skill-root tools/custom/skills` override defaults; each flag may be repeated. Targets must be project-local `.md` or `.mdc` files; skill roots must end in `/skills`. A declared path is an allowlist for proposals, not approval to write it. Confirm that the harness actually loads custom rules before relying on them. Ambiguous automatic harness detection requires an explicit profile.

## Plan

A UTF-8 plan contains `schema: 1`, `form_id`, `project_root`, `thread_id`, `review_file`, and `items`. Optional `harness`, `transport`, `instruction_files`, and `skill_roots` override project configuration for that frozen run. Without either configuration or explicit profile, legacy runs use the Codex profile.

Native mode requires `thread_id` to equal the current `CODEX_THREAD_ID`. Local mode requires an explicit review session ID through `--session-id` or `PROJECT_RSI_SESSION_ID`. That local ID binds a review, not an arbitrary IDE conversation. Never invent proof that an IDE is listening.

Each item has `id`, `title`, `summary`, `impact`, `evidence` (source pointers), and `changes`. An item can group one learned skill and its short instruction entry; unrelated improvements stay independent. Each change contains:

- `path`: project-relative path from the frozen target policy.
- `operation`: `write` for Markdown inside a declared skill root; `append_lesson` for a declared instruction file. Whole instruction-file replacement is unsupported.
- `candidate`: run-relative Markdown containing the exact new skill or exact lesson addition.
- `probe`: run-relative JSON with `level` (`STATIC`, `STATIC_SCENARIO`, or `OFFLINE_SYNTHETIC`) and nonempty `checks`. Each check needs `name`, `passed: true`, and an evidence pointer.
- `marker` for lessons: ASCII identifier, normally `PROJECT_RSI_LESSONS`. An absent section is proposed as a new marked section. Existing section preimages are frozen.

```json
{
  "schema": 1,
  "form_id": "review-example-01",
  "project_root": "/absolute/project",
  "thread_id": "explicit-local-review-session",
  "harness": "claude",
  "transport": "local",
  "review_file": "review.md",
  "items": [{
    "id": "P1",
    "title": "Check the complete command result",
    "summary": "A prior task reported success before the command exited.",
    "impact": "Adds a scoped check to the project instructions.",
    "evidence": ["private-log:exact-event-pointer"],
    "changes": [{"path": "CLAUDE.md", "operation": "append_lesson", "candidate": "lesson.md", "probe": "probe.json"}]
  }]
}
```

Distinct items cannot write the same ordinary file. Approved instruction additions can share one section and are composed together. Existing frontmatter stays byte-for-byte intact. A new Cursor `.mdc` receives the frontmatter shown in the review preview (`description` and `alwaysApply: true`). Custom `.instructions.md` files should already have their intended `applyTo` frontmatter; the engine does not invent glob scope.

```sh
python3 scripts/project_rsi.py build --plan /absolute/run/plan.json --output /absolute/run/form.html --session-id explicit-local-review-session
python3 scripts/review_server.py --run /absolute/run --once
```

Build creates `manifest.json` containing project/session identity, transport, target policy, configuration hash, plan/review hashes, candidate/probe hashes, target preimages, and managed-section preimages. It writes no active target. It creates `form-binding.json` and a fragment. Use the matching host or local server to render it; opening a raw file is insufficient.

## Submission and receipt

The payload includes `schema: 1`, `form_id`, `run`, `manifest_sha256`, `submission_id`, and `answers`: one `{id, value, comment}` row for each item. Values are `approve`, `reject`, `change`, or `explain`. Changes and explanations require a note. Approval with a note is deferred for interpretation. Reject never writes its candidate. Notes are retained including newlines.

For native or explicitly confirmed manual ingestion:

```sh
python3 scripts/project_rsi.py consume --run /absolute/run --submission /absolute/run/submission.json --confirmation-reference 'actual user message reference' --session-id explicit-local-review-session
```

For local HTML, the token-bound server saves the actual POST and calls the same consumer immediately. It does not execute instructions from a note. Hashes bind reviewed versions; they do not authenticate a person outside the chosen transport.

The receipt journals intended writes and backups, records before/after hashes and diffs, and verifies read-back. A per-run lock prevents simultaneous consumers. After a crash, inspect the journal before explicitly removing a stale `.consume.lock`; never silently replay a partial transaction. Identical completed duplicates return the prior receipt without target rewrites. Reused IDs with changed content are rejected. Partial outcomes preserve earlier writes and their journal.

For local reviews, `--once` returns after the first processed submission. Have the harness wait for that command and then report the receipt, notes, and pending revisions in the conversation. For native mode, the submitted message starts that processing turn. The HTML choice state alone is never proof of receipt.

## Existing guards and tests

If a project has a required approval/application guard, set `application_adapter: {"plan":"existing-guard-plan.json"}`. Build freezes its hash. Generic consume and the local server refuse to bypass that guard. The receiving assistant must validate the bound plan and use the project's existing guarded workflow. Adapter metadata is a pointer, not executable code.

`demo --directory /absolute/new-demo --harness cursor` creates a synthetic project, fixture identity marker, candidates, probes, review, and local form. It refuses an existing directory. Test-mode plans require that fixture marker and freeze its hash; test clicks only authorize the isolated sample. A real project should not be marked as synthetic to bypass review.

Bounds are 24 KiB per candidate/target and 16 KiB per payload, with 2,000 characters per local HTML note. These bounds do not replace project budgets. Missing evidence is not success. The engine does not launch model runs, send messages externally, create schedules, or publish files.
