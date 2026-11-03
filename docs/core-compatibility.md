# FineSub core compatibility

Yanami Sub 0.2.1.post1 and 0.2.2 RC1.1 target the exact upstream
[FineSub `v0.6.0`](https://github.com/caca2331/finesub/tree/5caf422cbad36f0402c98eb565e4c29aee4ac197)
source snapshot in `desktop/resources/core-source.json`.
The desktop repository owns presentation, Windows integration,
resource installation, and update delivery; FineSub core remains the only owner
of subtitle processing, scheduling, model routing, knowledge semantics, and
storage migration.

The staged 0.6.0 migration is tracked in
[core-060-migration.md](core-060-migration.md). The build dependency and workflows
use that verified snapshot. Read the documented acceptance limits and
[0.2.1 upgrade notes](release-notes-v0.2.1.md) before upgrading an installation.

## Coverage

| Core capability | Desktop support | Boundary |
| --- | --- | --- |
| Local audio/video and URL inputs | Supported | URL jobs request `yt-dlp` only when needed. |
| Every production pipeline stage | Supported | Vocal, aligned, stable, raw SRT, translated SRT, and final SRT are selectable. |
| ASR and separation tuning | Supported | Model, language, device/GPU tier, separation/rate, VAD assist, Qwen verification, language re-decode, context, decode batch, gap, stabilization, word timestamps, and split scale are forwarded to core. |
| Optional speaker labels/judging/exports | Supported, opt-in | Acoustic and experimental text/audio judging, backend and optional speaker cap use core defaults and loaders. Normal SRT stays unchanged; separate SRT/ASS and timeline/judge records are retained. Missing optional output is reported, not marked as success. |
| Per-task routing presets | Supported | One shared form for single tasks and batches; explicit follow-preset defaults use core resolution. Historical explicit settings remain unchanged. Knowledge feedback inherits the saved selection. |
| LLM correction/translation tuning | Supported | Unified media, retrieval, difficulty, continuity, parallel windows, output scale, per-task model routes, retry budgets, extra context/style, named styles, and resume are forwarded to core. Removed planning/media and old fast-mode arguments are not sent to 0.6.0. |
| Knowledge collection/update and refined-SRT feedback | Supported | The task form and Knowledge Center use the core knowledge implementation in an isolated worker. |
| Multiple files/URLs | Supported | The batch page uses the core scheduler, worker limits, queue back-pressure, priorities, retries, failure isolation, durable progress, cancel, resume, and core-compatible static JSONL manifest import/export. |
| API-key pools and custom providers | Supported | Free/paid Gemini pools, Exa, Tavily, and provider keys from the core catalog use the same encrypted `.env`; plaintext export is available through a native Save dialog. |
| Model routing and local-Agent routes | Supported | Core presets, policies, providers, targets, per-task overrides, and non-spending local CLI readiness checks are exposed. |
| Knowledge maintenance and sharing | Supported | Browse revisions, edit/create/retire entries, verify/repair/refresh, ingest, candidates, rollback/restore, refined feedback, remote registration, mark/push/pull, status, and conflict review are available. |
| Runtime setup and health (`setup`, `doctor`) | Supported | The Resources page performs request-specific setup and returns structured diagnostics. |
| Resource mirrors and reuse | Supported | Core manifests/hash checks remain authoritative; downloads can run concurrently, scan local disks first, and use the TUNA PyPI route in mainland China with official fallback. |
| Key export (`keys --out`) | Supported | Export includes readable built-in and catalog-provided keys; the encrypted source file is never overwritten. |
| Big-data relocation (`relocate`) | Supported | A native folder picker calls core's locked, crash-safe relocation and refreshes future single/batch workers without a restart. |
| Rebuildable-data cleanup (`uninstall --purge-big-data`) | Supported | Removes runtime, models, downloads, and Agent capsules only. Finished tasks, subtitles, API keys, preferences, and other personal data are preserved. |

The desktop deliberately publishes finished subtitle files beside a local input
and keeps intermediate task state under the managed task store. This is a
desktop product policy, not a second pipeline implementation.

## Deliberate CLI-only or partial surfaces

These boundaries remain intentional:

- Agent cooperation exposes owned waiting assignments and explicit join instructions
  in tasks, batches and settings. Core registration, JSON controls, validators and
  lease fences remain authoritative. Instructions pin this installation's managed
  interpreter and a source-pinning helper; Desktop does not inject into, launch,
  claim for or message the user's Agent. Windows instructions use PowerShell.
  The upstream conversational protocol is frozen and remains experimental/text-only.
- `agent-ping` spends quota. Desktop currently performs the safe, non-spending
  readiness probe instead of issuing model calls without a task.
- Running batches accept additional files/URLs with the batch's saved settings.
  Native storage persists the request before appending complete UTF-8 control rows;
  core `control_intake` admits them and commits its durable cursor after publication.
  A tail arriving after the scheduler's final poll remains explicitly resumable.
  Desktop never edits the live scheduler queue view. Reprioritization/withdrawal
  still use CLI controls; the current desktop intake adds new items only.
- Manual knowledge section split/move previews freeze core-translated operations
  and apply them as user revisions with revision checks. Migration restore points
  are checksum-verified and prepared/migrated in an isolated copy, then activated
  under activity/write barriers with a rollback snapshot and interrupted-swap guard.
  Config/keys are not restored; old proposal receipts are quarantined, not reused.
- Arbitrary `--output`, `--knowledge-root`, `--task-artifact-dir`, and
  `--task-id` are managed by the desktop task store so a web renderer cannot
  escape app-owned paths. `--extra-info-file` is represented by the equivalent
  text field.
- `--test-profile` is a developer/test switch. `--log-level` is replaced by
  the desktop reporter: concise live output plus durable full logs.
- Installing/removing the application itself belongs to the Windows installer.
  The in-app cleanup action removes only core-rebuildable data.

## Core interfaces currently consumed

Desktop adapters call or project these upstream surfaces instead of copying
their business logic:

- `finesub.stages.run_pipeline` and shared validation/constants for one task;
- `finesub.scheduler.run_batch` plus batch state/control files for queues;
- `finesub_bootstrap.ResourceManager`, `RuntimeEnvironment`, resource manifests,
  download routing, locks, paths, and `Shell` storage maintenance;
- the public model-route catalog, execution settings, API-key pool parser, and
  local-Agent driver probes;
- knowledge entry/node/update/share command entry points, invoked only through
  an allowlisted isolated worker.

## Interfaces to request from core next

1. A versioned public Agent service contract for status/bootstrap and optional
   quota probes. Existing structured task controls already exist and are reused;
   no terminal-output parser or duplicate runtime is needed.
2. A structured, versioned knowledge administration service. The current
   worker isolation is safe, but still adapts command-style entry points.
3. A versioned intake/control service for additional remote frontends. Current
   desktop append already uses the typed `IntakePoll`/commit API and owned JSONL
   control channel; do not add a second scheduler or rewrite queue.jsonl.
4. A small compatibility descriptor (core API level plus supported fields), so
   a future Desktop build can reject an incompatible core update with a precise
   message before launching a task.

## Upgrade rule

Do not float an installed Desktop to an untested FineSub branch. For every core
upgrade: pin an exact tag/commit, regenerate the packaged snapshot, run backend
contract tests against that source tree, run frontend type/tests and the static
build, then exercise one local-file task, one URL task, one batch resume, and
one knowledge update before publishing.
