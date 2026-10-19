---
name: project-rsi
description: Review project execution mistakes, propose and probe small instruction or skill improvements across coding harnesses, collect readable HTML approval, and apply confirmed changes with a clear receipt. Use for project retrospectives and recurring improvement requests.
metadata:
  version: "0.2.2"
---

# Project RSI

Turn verified execution mistakes into small, reviewable project improvements. Borrow the propose–probe–compose idea from [Harness²](https://github.com/google-research/harness2), with human approval before adoption. RSI here improves project instructions and skills; adoption does not change model weights or grant execution permissions.

## Select the harness and active rules

Read [harness compatibility](references/harnesses.md) when installing or selecting a rules target. Use `scripts/project_rsi.py init` to declare the harness, project-local instruction files, and skill roots. Profiles cover Codex, Claude Code, Gemini CLI, Cursor, Copilot, OpenCode, DSH, and WorkBuddy. Defaults include `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `CODEBUDDY.md`, Cursor `.mdc`, and Copilot instructions. Custom Markdown filenames and nested paths are supported. Inspect what the harness actually loads, including overrides and custom settings; filename detection alone does not prove loading. Select one appropriate target for a lesson rather than updating every tool's rules.

Initialization can install this skill when explicitly requested; it does not add lessons or alter project instructions. Installation does not create a schedule. Keep credentials, global harness settings, and production runtimes outside the adaptation scope.

## Review and propose

Identify the project, time window, available logs, and existing rules. Read bounded evidence and preserve source pointers, failed first results, unknowns, and coverage gaps. Distinguish an agent mistake from an expected negative test, environmental failure, or suspicion. Check why an existing rule failed before adding another one.

Propose the smallest useful change. Prefer an on-demand learned skill; keep instruction entries short and scoped. Do not change task contracts, production data, credentials, global settings, unrelated instructions, or frozen files. A review does not authorize re-running paid or controlled operations. Probe candidates with permitted synthetic examples and counterexamples; label static scenarios honestly. A text check does not prove future behavioral improvement.

Store evidence, candidates, probes, plan, and review outside active skill paths until approved. Read [the run format](references/protocol.md) when preparing a run. The bundled engine supports scoped Markdown changes and immutable plan/candidate/probe bindings.

For concrete examples of turning a mistake into a bounded lesson, see [capacity and complete-delivery examples](references/lesson-examples.md); read them only when useful to the current review.

## Present readable decisions

Use short HTML decision cards as the primary review. Evidence, before/after comparison, complete proposed text, checks, risks, and applicability are expandable. Markdown can remain as the audit source; do not require the user to read a long report to decide.

Each item offers approve, reject, request changes with a required comment, and request an explanation. Do not preselect approval. Show progress and prevent incomplete submission. Notes use a label on its own line and a full-width multiline field. Support long Chinese or English remarks, preserve drafts, and prevent horizontal overflow.

Choose the supported transport. **Native** uses in-conversation HTML and the host's `window.openai.sendFollowUpMessage({prompt,title})` API. Render the built fragment using that client's documented visualization instructions. A submitted native message carries the version binding, choices, and notes to the same conversation and starts a follow-up immediately.

**Local** serves the frozen HTML via `scripts/review_server.py --run /absolute/run --once`. The user's browser submission invokes the bounded consumer immediately and displays the receipt, including deferrals and full notes. Have the calling harness wait for the command to finish and then read its receipt. This mode works without a proprietary widget API; automatic push into an arbitrary idle IDE conversation is a separate capability. Read [the callback contract](references/callback.md) for both modes. Submission processing must not wait for a nightly schedule.

Check capability at runtime. If the chosen host API is absent, disable submission and preserve drafts; build a new local-transport review when appropriate. Ordinary browsers require the local server. Do not substitute a second CLI writer, undocumented sockets, automatic resubmission, or polling automation. A process launch, file save, page navigation, or widget-state save does not prove a conversation received a submission.

## Receive, apply, and report

A real native submission, a token-bound local HTML submission, or the current user's explicit confirmation authorizes the exact reviewed decisions. Opening a card, partial clicks, timers, old blanket permission, another agent's opinion, or silence do not. Bind the actual confirmation reference, plan, review, candidates, and probes. Verify the project and transport's session identity. Local session IDs correlate a review; they do not attest an IDE conversation.

Apply independently approved items only. Reject leaves that item unchanged; request-changes produces a revised proposal for another confirmation; explanation answers the question without adoption. Read every note. Approval with notes is held for interpretation. Version conflicts block affected items while independent approved work continues. Preserve concurrent changes and existing frontmatter; the engine appends approved instruction lessons only if that lesson section is unchanged. Creating a new Cursor rule includes its previewed `.mdc` frontmatter.

Journal planned writes, backups, and hashes before changing targets, then read back. Keep duplicate submissions idempotent. Preserve partial outcomes; do not automatically roll back without authorization.

**After processing, always return a plain-language receipt:** each item's approved/rejected/deferred status; whether it changed a named project instructions file, a skill, or another explicitly authorized artifact; exact paths; what changed and why; checks and remaining limits. The local page renders this receipt immediately; the waiting assistant should also explain it in the conversation. A `receipt.json` file alone is insufficient. Mark adopted instructions `ADOPTED_STATIC_ONLY`; assess future benefit using later comparable evidence.

## Scheduling, validation, and sharing

Create or update a recurring schedule only when requested, using the host scheduler and project timezone. Preserve cadence and notification preferences. Scheduled reviews propose changes; they never approve them. Submission handling uses the immediate native callback, independently of review time.

Use `demo` to create a new isolated project before a real UI test. Synthetic plans require a fixture identity marker; never use a test click as approval for real changes. Verify approve, reject, and multiline note-to-revise paths and read back the exact target hashes. For native delivery, also verify a message really arrives in the current conversation. For local delivery, verify browser receipt and command exit, then have the waiting assistant report the result. Record each transport's coverage separately; see [callback acceptance](references/callback.md).

For sharing, export portable sources and synthetic examples only. Exclude project logs, real runs, private paths, thread IDs, credentials, customer documents, and local state. This original implementation copies no Google source code. Publishing to a remote repository requires the user's chosen destination and publication authorization.
