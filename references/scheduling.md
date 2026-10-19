# Optional scheduled reviews

Scheduling is an opt-in host capability. Project RSI supplies an interactive setup workflow and a private state helper; it does not include a scheduler or create a job through its Python scripts. Installing the skill does not authorize a timer or automatic adoption of instruction or skill changes.

The harness profiles define instruction targets, skill paths, and review transports. They do not establish that all eight harnesses provide native scheduling. Check the capabilities exposed by the actual current host rather than inferring support from its profile name.

## Installation and the first actual skill load

`project_rsi.py init` reports `schedule_onboarding` status and a `next_step`. It cannot launch every harness, refresh every client, or make an agent load the skill. After installation, the user starts or refreshes their chosen harness and invokes Project RSI. The agent that first actually loads `SKILL.md` in an interactive conversation is responsible for the setup offer.

Before asking or performing a scheduling action, run the helper from the skill source or installed skill directory, using the actual project root:

```sh
python3 scripts/schedule_setup.py status \
  --project /absolute/path/to/project \
  --context interactive
```

`status` is read-only. For a project without a prior choice, its `next_action` is `ask_opt_in`. Read the current conversation as well: a complete user request already supplied there takes precedence over an unnecessary first-use question. Do not discard or replace an existing saved choice simply because the skill was updated or reinstalled.

Ask whether the user wants scheduled reviews before collecting scheduling details. If they agree, collect only the missing frequency, execution time or interval start, and timezone. Daily, weekdays, weekly, and custom cadences are possibilities, not defaults. Do not infer the timezone from the machine, a project path, the language used, or a previous example. Do not invent an execution time or interval start.

Record a refusal or a choice to defer, and do not repeat the offer on every invocation. Deferral has no automatic follow-up date unless the user actually supplies one through an authorized host workflow. The user can explicitly reopen setup or change a previous choice later.

For a scheduled background invocation, use:

```sh
python3 scripts/schedule_setup.py status \
  --project /absolute/path/to/project \
  --context scheduled
```

Do not start first-use questions during a scheduled run, including when its state file is missing. Perform only the review already authorized by that schedule. Missing or ambiguous project authority is not permission to create a replacement timer.

## Record the user's actual choice

The private state lives at `<project>/.project-rsi/schedule-setup.json`. Keep that directory out of public repositories and shared exports. It stores user scheduling preferences and host outcome references, not credentials or project evidence. The helper never creates, updates, deletes, or runs a host job.

The commands below are templates. Replace every capitalized placeholder with an actual user preference or evidence reference. A confirmation reference must identify the real human answer; a generated example, installation receipt, assistant suggestion, or silence is not confirmation. Keep real message and automation identifiers private.

For an agreement that still lacks details:

```sh
python3 scripts/schedule_setup.py decide \
  --project /absolute/path/to/project \
  --choice enable \
  --confirmation-reference 'ACTUAL_USER_MESSAGE_REFERENCE'
```

Missing preferences remain missing; the helper returns `next_action: ask_schedule_details`. Ask only for those missing details. Record the complete preference after the user's answer:

```sh
python3 scripts/schedule_setup.py decide \
  --project /absolute/path/to/project \
  --choice enable \
  --confirmation-reference 'ACTUAL_USER_MESSAGE_REFERENCE' \
  --frequency 'USER_SELECTED_FREQUENCY' \
  --timing 'USER_SELECTED_TIME_OR_INTERVAL_START' \
  --timezone 'USER_SELECTED_TIMEZONE'
```

For a refusal or deferral, use the same `decide` command with `--choice decline` or `--choice later` and the real confirmation reference. Do not add schedule preferences that the user did not give. A later explicit request can reopen setup; existing preferences need not be asked again unless the requested change or ambiguity requires it.

## Check host capability and existing schedules

1. Inspect the current host's supported scheduling tools or documented API. Determine whether it can query existing schedules, create or update the requested cadence, bind the correct project, and read the result back. Do not install an operating-system scheduler, a plugin, `cron`, or `launchd` as a substitute without separate user authorization.
2. Read any saved provider or automation reference, then query the host's current state. Search for an existing Project RSI schedule for this exact project even if there is no local receipt. Verify its identity, project, cadence, timing or start, timezone, enabled status, review instructions, and relevant notification preferences. Similar names alone do not prove a match.
3. Reuse a matching schedule. If the user has explicitly asked to change it, update within that requested scope and read it back. Do not create a duplicate because the local file is absent, a receipt is old, or a prior lookup failed. Conflicting schedules or unclear project ownership require reconciliation; do not silently delete or replace them.
4. Create a schedule only after the actual user's agreement covers this project and the complete preference. Use the host's supported mechanism and honor any host-required confirmation. Installation, skill loading, and a request for one manual review do not supply scheduling consent.
5. Read the resulting schedule back from the host before recording success. Report its actual cadence, time or start, timezone, project, and status. Preserve operation IDs and uncertain outcomes. If creation may have succeeded but the response was lost, inspect the original operation or host schedule before any retry; do not submit a second create request speculatively.

When setup is already configured, the helper returns `next_action: verify_existing_schedule`. This means verify and reuse the host schedule, not create a new one. Saved state is a past receipt, not evidence of current live host status. If the host cannot currently be queried, report that verification is unavailable and continue permitted manual work without claiming the timer is active.

If the host has no supported scheduler, explain that automatic scheduling is unavailable in the current environment and continue with manual reviews. Do not guess a time, claim a timer exists, or silently install a workaround. If a tool fails, preserve the failure and report what is unresolved; a local record cannot turn that failure into host success.

## Record the host outcome

Only after a real host read-back, record a newly created schedule:

```sh
python3 scripts/schedule_setup.py record \
  --project /absolute/path/to/project \
  --outcome created \
  --provider 'ACTUAL_HOST_PROVIDER' \
  --automation-id 'ACTUAL_HOST_AUTOMATION_ID' \
  --readback-reference 'ACTUAL_HOST_READBACK_REFERENCE'
```

Use `--outcome existing` for a schedule found and verified through the host, including an existing schedule updated within the user's requested scope. Both `created` and `existing` require the complete user preference already recorded and a real host receipt. These are state-recording commands; they do not create or validate a host schedule themselves. Do not supply fabricated provider names, IDs, or read-back references to pass the helper's checks.

For an unavailable capability or a failed attempt, record the actual reason:

```sh
python3 scripts/schedule_setup.py record \
  --project /absolute/path/to/project \
  --outcome unsupported \
  --reason 'ACTUAL_REASON_THIS_HOST_CANNOT_SCHEDULE'
```

Use `--outcome failed` with `--reason` for an actual failure; retain provider and operation references when available. Recording either outcome does not authorize a different scheduling mechanism. Return a readable result to the user and keep the review workflow usable manually. Keep a saved refusal or deferral effective rather than replacing it with a capability outcome just to continue setup.

## What a scheduled review may do

Bind the schedule to the user's exact project and requested cadence. Its review instructions should collect bounded evidence since the previous review, preserve failures and unknowns, prepare focused candidates and permitted checks in a private run, and present an HTML review with plain-language explanations. Honor the project's existing authority and runtime limits; a timer does not authorize new paid, controlled, or production operations.

Scheduled reviews propose changes. Installation and consent to a timer do not authorize adopting changes to active instructions or skills; each adoption still requires approval of the specific frozen proposal under [the run protocol](protocol.md). Preserve the user's notification preference. Unless routine status reports were requested, stay quiet when the monitored state is unchanged or there is no new actionable finding.

Process a submitted review when its supported transport delivers it, independently of the review cadence. A timer does not provide native conversation delivery or replace a processing receipt. See [submission and receipt delivery](callback.md) for those separate capabilities and checks.
