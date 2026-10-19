# Submission transports and acceptance

## Native conversation transport

The supported native host API is `window.openai.sendFollowUpMessage({prompt,title})`. Use it only where the host supplies that documented capability. The host selects the current conversation; the form cannot choose another recipient. Widget state is optional draft storage and does not start a turn. The actual message includes every decision and note.

The receiver verifies the current conversation, project, manifest, candidates, and comments; saves the exact payload; consumes it or uses the project's mandatory guard; reads back files; and immediately returns a human-readable change receipt. A resolved send request does not prove application succeeded. Do not defer a submission to a nightly schedule.

If the API is missing, submission stays disabled and the draft remains. Ordinary browser files do not gain that native API. Do not launch a competing CLI writer, probe private sockets, silently poll, or resubmit automatically. A documented API for a different product surface does not prove the current IDE chat supports it.

## Portable local transport

Build with `transport: "local"` and an explicit local session ID. Run:

```sh
python3 scripts/review_server.py --run /absolute/run --once
```

Open the printed `review_url`. The server binds only IPv4 loopback and one frozen review, with a random token and port. It checks Host, Origin, Fetch-Site, UTF-8 JSON, size, frozen form/manifest, exact submission ID, and every decision. It provides no arbitrary file browser or command execution. Keep that URL private; stop the process when finished.

An explicit browser POST saves the immutable submission, invokes the bounded consumer, renders the receipt in the page, and records `acknowledgement.json`. With `--once`, the process then exits. The calling harness can wait for that command to finish and read the stdout receipt path, without a nightly task or polling automation. Requests to revise or explain remain unapproved; the waiting assistant must handle them and present a new proposal when needed.

This mode immediately processes the approved patch and returns the browser receipt. It does not push into every idle CLI/IDE conversation. The event and acknowledgement explicitly record `conversation_wakeup: false`. A host that cannot wait for a command can still use the page, but must later read its receipt; do not promise unsupported push. A project-specific application guard prevents starting this generic server.

Native widget draft storage and local sessionStorage are best effort. Do not use either as approval. A user-initiated retry retains the submission ID. The engine never treats selecting approve, opening a card, a saved draft, a timer, or silence as submission.

## Real UI acceptance

Use a newly created demo project. In the real rendered page, approve one item, reject another, and request a revision using a long multiline note. Verify actual target hashes, untouched rejected/deferred candidates, exact retained notes, and idempotence. Keep screenshots and local IDs private.

For **native**, also verify a genuinely received current-conversation message, automatic consumption in that turn, and a result returned to the user. For **local**, verify the actual browser POST, visible receipt, command exit, and the waiting harness reading and explaining it. Record these as separate results. Mocked APIs, file saves, HTTP startup, direct tool calls bypassing HTML, and an assistant's own assertion are smaller checks.

Some clients forbid Computer Use controlling the harness app itself. Respect that refusal. Use an expressly supported browser surface; if none exists, prepare the full fixture and let the human trigger the final displayed test button. Do not bypass a protected app with aliases or scripts.

For clients supporting native visualization references, render the fragment through the documented content reference. A file link or source-editor tab alone does not guarantee the widget API. A test-mode shortcut can select a clearly labeled synthetic scenario and submit it; it never approves a real project change.
