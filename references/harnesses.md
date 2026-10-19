# Harness profiles and compatibility

Project RSI v0.2.0 separates the instruction target, skill directory, and review transport. A profile is a practical default, not proof that a particular client has loaded a file or that native callbacks work on that client. Verify the actual loaded entry before proposing changes.

The paths below are project-relative. `init --instructions` and `--skill-root` override the profile lists without changing the harness's own configuration. Both options can be repeated. The generic profile allows project-local `.md` and `.mdc` instruction targets. Symlinks, traversal, targets outside the declared policy, and unsupported operations are rejected by the application guard. See [the run protocol](protocol.md) for the authoritative scope and binding rules.

## Supported profiles

| Profile | Default instruction target | First skill root | Loading considerations |
|---|---|---|---|
| `codex` | `AGENTS.md` | `.agents/skills` | `AGENTS.override.md` takes priority in the same directory; configured fallback names are considered after `AGENTS.md`. |
| `claude` | `CLAUDE.md` | `.claude/skills` | `.claude/CLAUDE.md` is also an official entry. Newer clients can read `AGENTS.md`, with version, settings, and precedence constraints. |
| `gemini` | `GEMINI.md` | `.gemini/skills` | `context.fileName` can change or extend the names read by Gemini CLI; `.agents/skills` is an official skill alias. |
| `cursor` | `.cursor/rules/project-rsi.mdc` | `.cursor/skills` | Project rules require `.mdc` and rule frontmatter. `AGENTS.md` is an alternative. |
| `copilot` | `.github/copilot-instructions.md` | `.github/skills` | Other instruction formats and discovery differ between CLI, IDE, and GitHub experiences. |
| `opencode` | `AGENTS.md` | `.opencode/skills` | `CLAUDE.md` is a fallback; `opencode.json` can declare other instruction files. |
| `dsh` | `AGENTS.md` | `.dsh/skills` | Initialization reuses `CLAUDE.md` when root `AGENTS.md` is absent; `.agents/skills` is also supported. |
| `workbuddy` | `CODEBUDDY.md` | `.codebuddy/skills` | Initialization reuses `.codebuddy/CODEBUDDY.md`, then `AGENTS.md`, if the default is absent. |
| `generic` | `AGENTS.md` | `.agents/skills` | Declare your actual instruction file and a skill root supported by your client. |

`auto` selects a harness when one project signature matches, falls back to `generic` when none match, and asks for an explicit choice when several match. It is not a harness process detector. Shared `AGENTS.md` and `.agents/skills` locations alone do not reliably identify a client. An explicit choice is preferable in a repository used by several tools.

## Codex

Codex checks `AGENTS.override.md`, then `AGENTS.md`, then configured `project_doc_fallback_filenames` in each directory of the instruction chain. It loads at most one instruction file per directory. If an override is active, configure Project RSI to edit that active file rather than assuming `AGENTS.md` will be used.

```sh
python3 scripts/project_rsi.py init \
  --project /absolute/project --harness codex \
  --instructions AGENTS.override.md --transport local --install-skill
```

The current official skill discovery path is `.agents/skills`. The bundled profile also permits the `.codex/skills` compatibility location, but do not assume a client loads a legacy location without checking. Native review requires a conversation host that actually provides the widget API; Codex CLI and ordinary browser tabs do not automatically inherit it.

Official sources: [instruction discovery and fallback filenames](https://developers.openai.com/codex/guides/agents-md/), [local skill discovery](https://developers.openai.com/codex/skills/).

## Claude Code

The broadly compatible project entry is `CLAUDE.md` or `.claude/CLAUDE.md`, and project skills live in `.claude/skills/<name>/SKILL.md`. Modular rules live under `.claude/rules/`; their optional YAML `paths` field scopes loading.

Direct `AGENTS.md` support requires Claude Code v2.1.277 or later and can be disabled or affected by settings. By default, an applicable `CLAUDE.md` or `CLAUDE.local.md` takes priority over direct `AGENTS.md` discovery. An `@AGENTS.md` import in `CLAUDE.md` remains an official way to share content across clients. Project RSI does not automatically add that import or change Claude settings.

Official sources: [memory and instruction precedence](https://code.claude.com/docs/en/memory), [project skill installation](https://code.claude.com/docs/en/skills).

## Gemini CLI

Gemini CLI defaults to `GEMINI.md`. Its `settings.json` can use `context.fileName` with a different name or list of names, for example `AGENTS.md`, `CONTEXT.md`, and `GEMINI.md`. Project skills are supported in both `.gemini/skills` and the interoperable `.agents/skills` alias.

```sh
python3 scripts/project_rsi.py init \
  --project /absolute/project --harness gemini \
  --instructions CONTEXT.md --transport local --install-skill
```

This declares Project RSI's review target. Configure Gemini's `context.fileName` separately if it does not already load `CONTEXT.md`.

Official sources: [GEMINI.md and custom context filenames](https://geminicli.com/docs/cli/gemini-md/), [skills and discovery aliases](https://geminicli.com/docs/cli/skills/).

## Cursor

Cursor project rules live in `.cursor/rules/**/*.mdc`. A plain `.md` file in that directory is ignored by the rules system. Frontmatter controls applicability through `description`, `globs`, and `alwaysApply`:

```md
---
description: "Lessons explicitly approved through Project RSI"
alwaysApply: true
---

<!-- PROJECT_RSI_LESSONS_BEGIN -->
<!-- Approved lesson additions go here. -->
<!-- PROJECT_RSI_LESSONS_END -->
```

With `alwaysApply: true`, Cursor always includes the rule. With `alwaysApply: false`, `globs` can attach it to matching files, a description can let the agent select it, or neither field can leave it for manual invocation. Project RSI preserves an existing file's frontmatter; it should not silently broaden a scoped rule to apply everywhere. The default profile uses a dedicated lesson rule rather than converting unrelated project rules.

Project skills live in `.cursor/skills/<name>/SKILL.md`. Cursor also documents `.agents/skills`, Claude, and Codex compatibility paths. Prefer the native directory for a single-tool installation and avoid installing duplicate copies without a reason.

Official sources: [rule format and applicability](https://cursor.com/docs/rules), [skill locations](https://cursor.com/help/customization/skills).

## GitHub Copilot

`.github/copilot-instructions.md` is the repository-wide entry. Modular `.github/instructions/**/*.instructions.md` files can use `applyTo` frontmatter. Copilot CLI also documents `AGENTS.md`, `CLAUDE.md`, `.claude/CLAUDE.md`, and `GEMINI.md`; other Copilot experiences may support a different subset.

Project skills are documented in `.github/skills`, `.claude/skills`, and `.agents/skills`. The profile selects `.github/skills` first. Confirm support in the exact CLI or IDE being used; compatibility with one Copilot experience does not establish all others.

Official sources: [Copilot CLI custom instructions](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/add-custom-instructions), [agent skill installation](https://docs.github.com/en/copilot/how-tos/copilot-on-github/customize-copilot/customize-cloud-agent/add-skills).

## OpenCode

OpenCode reads project `AGENTS.md` and supports `CLAUDE.md` as a fallback when no applicable `AGENTS.md` exists. `opencode.json` has an `instructions` list for additional filenames and patterns; Project RSI does not change it automatically.

The native project skill directory is `.opencode/skills/<name>/SKILL.md`. OpenCode also documents `.claude/skills` and `.agents/skills`. A skill needs YAML `name` and `description`; the name must match its directory.

Official sources: [rules and custom instruction files](https://docs.opencode.ai/docs/rules/), [skill discovery and frontmatter](https://opencode.ai/docs/skills/).

## DSH

The DSH profile uses project `AGENTS.md` and `.dsh/skills/<name>/SKILL.md`, with `.agents/skills` as a supported alternative. Upstream ranks `.dsh/skills` before `.agents/skills`; its skill provider finds the nearest `.git` ancestor, or uses the current directory when none exists. Provider settings can change the enabled roots.

DSH's instruction provider defaults to both `AGENTS.md` and `CLAUDE.md`, with additive `AGENTS.local.md` and `CLAUDE.local.md` overlays. It exposes `instructionFileCandidates` and `localInstructionFileCandidates` for custom names. Project RSI initialization selects an existing `CLAUDE.md` when root `AGENTS.md` is absent; this target choice does not replace DSH's full loading policy. Check actual loaded instructions, overlays, and project binding before preparing a proposal.

This is a local project-file integration. It does not register or launch a DSH session, create a timer, change project routing, or use a running DSH instance's API. Review delivery uses the portable local server; native same-conversation wakeup is not claimed.

Official sources: [DSH instruction provider](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/context/agent-instructions/README.md), [filesystem skill discovery](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/skill/skill-filesystem/README.md).

## WorkBuddy

WorkBuddy's official code-project configuration uses `.codebuddy/rules` and `.codebuddy/skills/<name>/SKILL.md`. It documents compatibility with root `CODEBUDDY.md`, `.codebuddy/CODEBUDDY.md`, and `AGENTS.md`. The Project RSI profile defaults to `CODEBUDDY.md`; initialization reuses the latter two existing entries, in that order, when the root default is absent.

Use **`.codebuddy/skills`**, not `.workbuddy/skills`. This profile covers local code-project files. WorkBuddy's cloud-managed project skills and client-specific personal skill libraries have separate availability rules; installing files locally does not establish cloud synchronization or native HTML wakeup. A local skill installation also does not constitute acceptance into WorkBuddy's skill marketplace.

Official source: [WorkBuddy project and code-development configuration](https://www.codebuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/Project).

## Review delivery is a separate capability

The release implements two transports:

| Transport | What it does | What it does not prove |
|---|---|---|
| `native` | Uses the host's `window.openai.sendFollowUpMessage` API to submit the bound review to the conversation. | Availability in every Codex client or another vendor's interface; receipt and adoption still require actual processing. |
| `local` | A loopback review server receives a real browser submission, validates and consumes it, returns an HTML receipt, and with `--once` returns the result to the waiting command. | Authentication of an arbitrary IDE conversation or automatic wakeup of an unrelated existing chat. |

The local correlation session ID is explicitly supplied. It binds the plan, submission, and receipt, rather than pretending to be a verified IDE thread ID. Let the agent run and wait for the single review command when immediate continuation in that agent's work is desired. A server launched in a separate terminal can complete adoption, but cannot guarantee that a chat wakes up.

Some harnesses offer official extension points that could support a future dedicated bridge:

- **Claude Channels:** pushes external MCP events into a running local session, subject to research-preview availability, authentication, per-session opt-in, allowed plugins, and organization policy. See [Channels](https://code.claude.com/docs/en/channels).
- **OpenCode Server:** `POST /session/:id/prompt_async` submits a message asynchronously to a selected session. Its `204` response is not a processing receipt. See [the server API](https://opencode.ai/docs/server/).
- **Cursor SDK:** `Agent.resume(id)` and `agent.send()` can continue an SDK agent. That does not establish access to any currently visible IDE conversation. See [the TypeScript SDK](https://cursor.com/docs/sdk/typescript).
- **DSH Session Controller:** authenticated API Gateway operations can address a session, and prompt `requestId` retries retain their original acceptance. A dedicated bridge would still need authorization, session/project binding, and a completion receipt. HTML attachments do not supply that bridge. See [Session Controller](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/api/session-controller/README.md).
- **WorkBuddy Local Assistant API:** the documented message endpoint accepts `content` and `msg_type`. It does not document a current project/thread selector in that request, so it is insufficient to claim precise current-conversation wakeup. See [Open API Reference](https://open.workbuddy.cn/en/docs/openapi).

These dedicated bridges are not implemented in this release. Gemini CLI's lifecycle [Hooks](https://geminicli.com/docs/hooks/) alone do not establish external HTML wakeup, and no universal callback is claimed across Copilot interfaces.

Read [the callback contract](callback.md) before reporting delivery success. Offline profile tests, a browser save, an HTTP acknowledgement, an agent's receipt of a payload, and a completed user-facing adoption receipt are different levels of evidence. Record which ones were actually exercised. Installation does not enable a timer; recurring review requires a scheduler the user has authorized.
