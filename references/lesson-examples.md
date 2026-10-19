# Two synthetic learning examples

These examples illustrate the method; they are not permanent rules for every project.

## Capacity across the whole task

Observed mistake: a 60 KiB working directory passes a 100 KiB limit, but copying it for validation makes both 60 KiB copies coexist and exceeds the limit. A small final archive does not erase that peak.

Proposed improvement: for tasks with explicit hard limits, list objects that coexist during preparation, execution, copying, compression, independent read-back, packaging, and cleanup. Check total, role, and stage limits separately. Keep physical bytes separate from an application's internal counters; unknown sizes stay unknown. Reuse the existing contract and never grant extra capacity.

Probe: the 60 KiB initial state passes, its 120 KiB coexistence peak fails, and a 40+40 KiB alternative fits. Include a case where the total pool fits but a role sublimit fails. The probe proves these calculations, not a future reduction in mistakes.

Adoption: propose a learned-skill Markdown file and a short AGENTS entry. After approval, return both exact paths and explain: “Previously we checked only the start; now we also check what must coexist while finishing.”

## A printed result versus complete delivery

Observed mistake: a child prints a success prefix but stays alive with an open listener. The collector has not received end-of-stream or a complete packet.

Proposed improvement: for the relevant command/collector path, distinguish internal result, direct process exit, both output streams ending, complete handover material, and owned resource cleanup. A wrapper's zero exit or a chat becoming idle does not prove these facts. Use only checks allowed by the task; do not spend a controlled real attempt to see if a repair works.

Probe: a minimal local child that prints then sleeps must remain incomplete; a completed child with a full packet can pass; an internally failed command with a successful wrapper must remain failed. Missing evidence remains unknown. Synthetic tests do not establish production runtime or business quality.

Adoption: after item-specific approval, return the changed skill path and AGENTS entry, with a plain explanation: “Seeing some output is an intermediate state; completion also requires the program and the handover to finish.”
